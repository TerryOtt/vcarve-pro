from pathlib import Path
import sqlite3,json,re,collections,base64
from pypdf import PdfReader

root=Path(__file__).resolve().parent
source=root/'sources'/'Amana-Tool-Vectric-12-5-2025.vtdb'
db=sqlite3.connect(f'file:{source.as_posix()}?mode=ro',uri=True)
db.row_factory=sqlite3.Row
geometry=[dict(r) for r in db.execute('select * from tool_geometry')]
tree={r['id']:dict(r) for r in db.execute('select * from tool_tree_entry')}
entries={v['tool_geometry_id']:v for v in tree.values() if v['tool_geometry_id']}
types={0:'Ball nose',1:'End mill',2:'Radiused end mill',3:'V-bit',4:'Engraving',5:'Tapered ball nose',6:'Drill',8:'Form tool'}

def sku_of(name):
    match=re.search(r'#\s*([A-Za-z0-9][A-Za-z0-9_-]*)',name or '')
    if not match:
        match=re.match(r'\s*([0-9]{5,6}[A-Z]*(?:-[A-Z0-9]+)*)\b',name or '')
    return match.group(1) if match else ''

def ancestry(entry):
    result=[]
    current=tree.get(entry['parent_group_id'])
    seen=set()
    while current:
        assert current['id'] not in seen
        seen.add(current['id'])
        result.append(current['name'] or '')
        current=tree.get(current['parent_group_id'])
    return list(reversed(result))

listed=collections.defaultdict(set)
reader=PdfReader(root/'sources'/'Amana-Tool-Vectric-Tool-File-4-2020.pdf')
for page_number,page in enumerate(reader.pages,1):
    def visit(text,cm,tm,font,size):
        for token in text.split():
            token=token.strip()
            if re.fullmatch(r'(?:[0-9]{5,6}[A-Z]*(?:-[A-Z0-9]+)*|[A-Z]{2,5}-[A-Z0-9]+(?:-[A-Z0-9]+)*)',token):
                # The PDF's alphabetical and numerical columns are independent
                # lists, not paired SKU aliases.
                listed[token].add(page_number)
    page.extract_text(visitor_text=visit)

geometries={g['id']:g for g in geometry}
geometry.sort(key=lambda g:(sku_of(g['name_format']),g['id']))
tools=[];notes=[];geometry_row={}
for row,g in enumerate(geometry,8):
    parts=ancestry(entries[g['id']])
    sku=sku_of(g['name_format'])
    assert sku, f"No part number parsed: {g['name_format']}"
    shank=next((v for v in reversed(parts) if re.search('shank',v,re.I)),None)
    category=parts[1] if len(parts)>1 else None
    preset_count=db.execute('select count(*) from tool_entity where tool_geometry_id=?',(g['id'],)).fetchone()[0]
    tools.append([sku,category,types.get(g['tool_type'],f"Type {g['tool_type']}"),
                  'in' if g['units']==1 else 'mm',g['diameter'],None,
                  g['included_angle'],None,g['flat_diameter'],None,
                  g['tip_radius'],None,g['num_flutes'],g['flute_length'],None,
                  shank,' / '.join(parts),g['name_format'],
                  'Yes' if g['outline'] is not None else 'No',
                  'Yes' if preset_count else 'No',
                  'Yes' if sku in listed else 'No',g['id']])
    geometry_row[g['id']]=row
    if g['notes']:
        notes.append([sku,g['name_format'],g['notes'].replace('\r\n','\n'),g['id']])

presets=[];preset_geometry_rows=[]
query='''select e.*,c.rate_units,c.feed_rate,c.plunge_rate,c.spindle_speed,
 c.spindle_dir,c.stepdown,c.stepover,c.clear_stepover,c.length_units,c.tool_number,
 c.thread_depth,c.thread_step_in,c.laser_power,c.laser_passes,c.laser_burn_rate,
 c.line_width,c.laser_kerf,
 m.name material_name,ma.name machine_name,c.notes cutting_notes
 from tool_entity e join tool_cutting_data c on c.id=e.tool_cutting_data_id
 left join material m on m.id=e.material_id left join machine ma on ma.id=e.machine_id'''
source_presets=[dict(r) for r in db.execute(query)]
source_presets.sort(key=lambda c:(sku_of(geometries[c['tool_geometry_id']]['name_format']),c['material_name'] or '',c['id']))
for c in source_presets:
    g=geometries[c['tool_geometry_id']]
    assert c['rate_units'] in [1,4]
    assert c['length_units'] in [0,1]
    presets.append([sku_of(g['name_format']),c['material_name'] or 'Unspecified',
                    c['machine_name'], 'in/min' if c['rate_units']==4 else 'mm/min',
                    c['feed_rate'],None,c['plunge_rate'],None,c['spindle_speed'],None,None,
                    'in' if c['length_units']==1 else 'mm',c['stepdown'],None,
                    c['stepover'],None,c['clear_stepover'],None,c['tool_number'],
                    c['spindle_dir'],g['id'],c['tool_cutting_data_id']])
    preset_geometry_rows.append(geometry_row[g['id']])

sku_counts=collections.Counter(row[0] for row in tools)
listing=[[sku,', '.join(map(str,sorted(pages))),sku_counts.get(sku,0),
          'Present in database' if sku in sku_counts else 'Listed only; no definition in supplied database']
         for sku,pages in sorted(listed.items())]
missing=[sku for sku in listed if sku not in sku_counts]
all_geometry={}
for g in geometry:
    row=dict(g)
    row['outline_base64']=base64.b64encode(row.pop('outline')).decode('ascii') if g['outline'] is not None else None
    all_geometry[g['id']]=row
out={'tools':tools,'presets':presets,'preset_geometry_rows':preset_geometry_rows,
     'all_geometry':all_geometry,'all_cutting_records':source_presets,
     'notes':notes,'listing':listing,
     'metadata':{'geometry_count':len(tools),'preset_count':len(presets),
                 'unique_database_part_numbers':len(sku_counts),'linked_pdf_part_numbers':len(listing),
                 'linked_pdf_missing_from_database':missing,'units':dict(collections.Counter(row[3] for row in tools)),
                 'source_url':'https://www.amanatool.com/view-amana-tool-vectric-library',
                 'database_url':'https://www.amanatool.com/pub/media/vectriclibrary/Amana-Tool-Vectric-12-5-2025.vtdb',
                 'list_url':'https://www.amanatool.com/pub/media/vectriclibrary/Amana-Tool-Vectric-Tool-File-4-2020.pdf'}}
assert len(tools)==db.execute('select count(*) from tool_geometry').fetchone()[0]
assert len(presets)==db.execute('select count(*) from tool_entity').fetchone()[0]
assert all(row[0] for row in tools)
assert len({r[-1] for r in tools})==len(tools)
(root/'database.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(out['metadata'],indent=2))
