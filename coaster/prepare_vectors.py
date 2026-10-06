"""Trace the supplied monochrome logo into closed SVG and DXF contours.

Coordinates use inches, a 4 x 4 inch document, and a centered 3 inch logo.
These are design vectors, not cutting instructions or G-code.
"""

from pathlib import Path
from collections import defaultdict
import json
import os
import sys
import numpy as np
from PIL import Image, ImageDraw

# The DXF writer is installed in a task-specific temporary tools directory.
DXF_TOOLS = Path(os.environ['TEMP']) / 'codex-vcarve-dxf-tools'
if DXF_TOOLS.is_dir():
    sys.path.insert(0, str(DXF_TOOLS))
import ezdxf


ROOT = Path(__file__).resolve().parent
SOURCE = Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'source-logo.jpg'
if not SOURCE.is_file():
    raise SystemExit('Supply the original monochrome logo image path as the first argument.')
gray = np.asarray(Image.open(SOURCE).convert("L"), dtype=float)
black = gray < 127.5


def trace_contours():
    """Marching squares with interpolated grayscale edge crossings."""
    coordinates = {}
    adjacency = defaultdict(list)
    yy, xx = np.nonzero(black[:, :-1] != black[:, 1:])
    for y, x in zip(yy, xx):
        fraction = (127.5 - gray[y, x]) / (gray[y, x + 1] - gray[y, x])
        coordinates[("h", int(x), int(y))] = (float(x + fraction), float(y))
    yy, xx = np.nonzero(black[:-1, :] != black[1:, :])
    for y, x in zip(yy, xx):
        fraction = (127.5 - gray[y, x]) / (gray[y + 1, x] - gray[y, x])
        coordinates[("v", int(x), int(y))] = (float(x), float(y + fraction))
    cells = black[:-1, :-1].astype(int) + black[:-1, 1:].astype(int)
    cells += black[1:, :-1].astype(int) + black[1:, 1:].astype(int)
    yy, xx = np.nonzero((cells > 0) & (cells < 4))
    for y0, x0 in zip(yy, xx):
        x, y = int(x0), int(y0)
        edges = [("h", x, y), ("v", x + 1, y), ("h", x, y + 1), ("v", x, y)]
        active = [e for e in edges if e in coordinates]
        if len(active) == 2:
            pairs = [active]
        else:
            center_black = gray[y:y + 2, x:x + 2].mean() < 127.5
            pairs = [(edges[0], edges[1]), (edges[2], edges[3])] if black[y, x] == center_black else [(edges[0], edges[3]), (edges[1], edges[2])]
        for a, b in pairs:
            adjacency[a].append(b)
            adjacency[b].append(a)
    assert all(len(neighbors) == 2 for neighbors in adjacency.values()), "Open or ambiguous contour"
    visited = set()
    contours = []
    for first in adjacency:
        if first in visited:
            continue
        loop, previous, current = [], None, first
        while current not in visited:
            visited.add(current)
            loop.append(coordinates[current])
            following = next(n for n in adjacency[current] if n != previous)
            previous, current = current, following
        assert current == first, "Contour failed to close"
        points = np.array(loop)
        area = abs(signed_area(points))
        if area >= 2:
            contours.append(points)
    return sorted(contours, key=lambda p: abs(signed_area(p)), reverse=True)


def signed_area(points):
    return float(np.sum(points[:, 0] * np.roll(points[:, 1], -1) - points[:, 1] * np.roll(points[:, 0], -1)) / 2)


def rdp(points, tolerance):
    if len(points) <= 2:
        return points
    delta = points[-1] - points[0]
    length = np.linalg.norm(delta)
    if length == 0:
        distances = np.linalg.norm(points - points[0], axis=1)
    else:
        distances = np.abs(delta[0] * (points[:, 1] - points[0, 1]) - delta[1] * (points[:, 0] - points[0, 0])) / length
    split = int(np.argmax(distances))
    if distances[split] <= tolerance:
        return points[[0, -1]]
    return np.concatenate((rdp(points[:split + 1], tolerance)[:-1], rdp(points[split:], tolerance)))


def simplify_closed(points):
    # Split at opposite points to avoid the coincident endpoints of a closed loop.
    start = int(np.argmin(points[:, 0]))
    points = np.roll(points, -start, axis=0)
    split = int(np.argmax(np.linalg.norm(points - points[0], axis=1)))
    tolerance = 0.20 if np.ptp(points[:, 0]) < 100 else 0.35
    a = rdp(points[:split + 1], tolerance)
    b = rdp(np.concatenate((points[split:], points[:1])), tolerance)
    return np.concatenate((a[:-1], b[:-1]))


all_contours = trace_contours()
registered_contours = [p for p in all_contours if p[:, 0].min() > 800 and p[:, 1].min() > 1000]
original = [p for p in all_contours if not (p[:, 0].min() > 800 and p[:, 1].min() > 1000)]
reference_black = black.copy()
for p in registered_contours:
    x0, y0 = np.floor(p.min(axis=0)).astype(int)
    x1, y1 = np.ceil(p.max(axis=0)).astype(int)
    reference_black[y0:y1 + 1, x0:x1 + 1] = False
contours = [simplify_closed(p) for p in original]
all_points = np.concatenate(contours)
minimum, maximum = all_points.min(axis=0), all_points.max(axis=0)
scale = 3.0 / (maximum[0] - minimum[0])
center = (minimum + maximum) / 2
positioned = [(p - center) * scale + 2 for p in contours]


def svg_path(points):
    return "M " + " L ".join(f"{x:.8f},{y:.8f}" for x, y in points) + " Z"


def write_svg():
    main, registered = [], []
    for original_points, points in zip(contours, positioned):
        (registered if original_points[:, 0].min() > 800 and original_points[:, 1].min() > 1000 else main).append(svg_path(points))
    content = ['<?xml version="1.0" encoding="UTF-8"?>', '<svg xmlns="http://www.w3.org/2000/svg" width="4in" height="4in" viewBox="0 0 4 4">', '<title>3 inch walnut logo in a 4 inch maple coaster</title>', '<desc>Closed traced contours, registered mark removed. Black is walnut; negative space is maple. No stock outline and no toolpaths. Original orientation; the inlay toolpath generates the mirrored plug.</desc>']
    for label, paths in [("WALNUT_LOGO", main), ("WALNUT_REGISTERED", registered)]:
        if paths:
            content.append(f'<g id="{label}"><path fill="#000000" fill-rule="evenodd" d="{" ".join(paths)}"/></g>')
    content.append('</svg>')
    (ROOT / 'purdue-coaster-logo-3in.svg').write_text('\n'.join(content) + '\n', encoding='utf-8')


def write_dxf():
    # Use a standard writer instead of hand-assembling DXF tables. R12's
    # classic closed 2D polylines avoid newer subclass and ownership metadata.
    # R12 coordinates are in inches; choose inches if the importer asks.
    document = ezdxf.new('R12')
    document.layers.new('WALNUT_LOGO', dxfattribs={'color': 7})
    document.header['$INSBASE'] = (0, 0, 0)
    document.header['$LUNITS'] = 2
    document.header['$LUPREC'] = 8
    modelspace = document.modelspace()
    for points in positioned:
        modelspace.add_polyline2d([(float(x), float(4-y)) for x, y in points],
                                 close=True, dxfattribs={'layer': 'WALNUT_LOGO'})
    filename = ROOT / 'purdue-coaster-logo-3in.dxf'
    document.saveas(filename)
    reread = ezdxf.readfile(filename)
    audit = reread.audit()
    assert not audit.errors and not audit.fixes, 'DXF needs structural repairs'
    entities = list(reread.modelspace())
    assert len(entities) == len(positioned) == 5
    for entity, expected in zip(entities, positioned):
        assert entity.dxftype() == 'POLYLINE' and entity.is_closed and entity.is_2d_polyline
        actual = np.array([(v.dxf.location.x, 4-v.dxf.location.y) for v in entity.vertices])
        assert np.allclose(actual, expected, rtol=0, atol=1e-10)
    print('DXF verified: R12, five closed 2D polylines, no audit errors or repairs.')


def check_geometry():
    # Scan at source pixel centers; integer-rounded polygon drawing would bias
    # the comparison outward by one pixel along every edge and hole.
    reconstructed = np.zeros(black.shape, dtype=bool)
    for points in contours:
        other = np.roll(points, -1, axis=0)
        for y in range(max(0, int(np.ceil(points[:, 1].min()))), min(1500, int(np.floor(points[:, 1].max())) + 1)):
            crosses = (points[:, 1] > y) != (other[:, 1] > y)
            a, b = points[crosses], other[crosses]
            intersections = np.sort(a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1]))
            assert len(intersections) % 2 == 0
            for left, right in intersections.reshape(-1, 2):
                reconstructed[y, max(0, int(np.ceil(left))):min(1500, int(np.ceil(right)))] ^= True
    intersection = np.count_nonzero(reconstructed & reference_black)
    union = np.count_nonzero(reconstructed | reference_black)
    ratio = intersection / union
    assert ratio > 0.99, f'Trace differs too much from source: {ratio}'
    assert len(contours) == len(original)
    assert all(len(p) >= 3 for p in contours)
    geometry = {
        'coaster_width_in': 4, 'coaster_height_in': 4,
        'logo_width_in': 3, 'logo_height_in': float((maximum[1] - minimum[1]) * scale),
        'logo_center_in': [2, 2], 'horizontal_margin_in': 0.5,
        'maple_coaster_thickness_in': 0.5, 'walnut_plug_stock_thickness_in': 1,
        'registered_mark_removed': True,
        'closed_contours': len(contours), 'vertices_per_contour': [len(p) for p in contours],
        'trace_source_pixel_iou': ratio, 'maximum_simplification_tolerance_in': 0.35 * scale,
        'svg_and_dxf_have_stock_boundary': False, 'gcode_created': False,
    }
    (ROOT / 'geometry-check.json').write_text(json.dumps(geometry, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(geometry, indent=2))


def preview():
    size = 1200
    parity = np.zeros((size, size), dtype=bool)
    for points in positioned:
        layer = Image.new('1', (size, size))
        ImageDraw.Draw(layer).polygon([tuple(p * size / 4) for p in points], fill=1)
        parity ^= np.asarray(layer)
    image = Image.new('RGB', (size, size), '#eed7aa')
    image.paste('#593622', mask=Image.fromarray((parity * 255).astype(np.uint8)))
    draw = ImageDraw.Draw(image)
    draw.rectangle((1, 1, size - 2, size - 2), outline='#987849', width=3)
    image.save(ROOT / 'vector-layout-preview.png')


write_svg()
write_dxf()
check_geometry()
preview()
