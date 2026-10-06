# Amana Hardwood tool reference

## Source and extraction

The source is the user-provided `Amana-Tool-Vectric-12-5-2025.vtdb`, linked from [Amana's Vectric library](https://www.amanatool.com/view-amana-tool-vectric-library). The downloaded source database and older PDF list are local inputs excluded from Git; extracted data and generated workbooks preserve the project work.

- [Database download](https://www.amanatool.com/pub/media/vectriclibrary/Amana-Tool-Vectric-12-5-2025.vtdb)
- [Older linked catalog list](https://www.amanatool.com/pub/media/vectriclibrary/Amana-Tool-Vectric-Tool-File-4-2020.pdf)

The database contains 889 geometry definitions, representing 863 distinct catalog codes, and 1,348 cutting-preset records. Some catalog codes have multiple definitions. The older PDF lists 650 distinct codes, including 33 without definitions in the supplied database. Early complete workbooks included those 33 as blank-setting entries, for 922 rows.

`tool_geometry.name_format` contains the original definition name. The catalog code, such as `45771-K`, is extracted from that name. Database `id` is an internal identifier and is not the catalog code. Numeric codes such as `201003` are real catalog numbers for boring bits, not sequential row IDs.

## Current workbook selection

The current workbook includes 638 router-bit definitions with catalog codes and explicit Hardwood presets. Boring/drill tools and In-Sand CNC sanders are excluded. Cutting settings come from the source's Hardwood records, not blanket overrides.

All lengths and rates are normalized to inches and inches/minute. Metric values are divided by 25.4. True zero values remain zero; missing or inapplicable settings remain blank.

## Final columns and formatting

| Column | Field |
|---|---|
| A | Cutting Type |
| B | Shank Diameter (in) |
| C | Tool ID |
| D | Cutting Diameter (D) (in) |
| E | Spindle Speed (RPM) |
| F | Feed Rate (inches/min) |
| G | Plunge Rate (inches/min) |
| H | Number of Flutes |
| I | Pass Depth (in) |
| J | Stepover (in) |
| K | Clearance Pass (in) |
| L | Original Definition Name |

Cutting Type uses title-case labels based on the source library groups, not a newly inferred exact cutter profile. The source's `Countersink Bits` item 56129 is named a point-cutting roundover and is labeled Roundover. Endmill-group variants retain their Endmill category.

Sort order: Endmill, V-Bit, Flattening, Engraving, Bowl, Roundover, then remaining types alphabetically. Within each type: shank diameter ascending, cutting diameter ascending. Tool ID is not a sort key. Missing shank sizes sort last within their type.

Shank diameter comes from the source shank group, with definition-name fallback when absent. `RCK-420` has no shank size in those source fields, so its value remains blank. Cutting diameter uses the database's actual Diameter (D) geometry field; it is not inferred from shank size.

Columns A–D and the first seven rows are frozen. Data cells are centered except the original definition name, which is left-aligned. Widths fit the contents; RPM uses thousands separators. Header filters are enabled.

## 45771-K example

The source's Hardwood preset provides 18,000 RPM, feed 50 IPM, plunge 25 IPM, one flute, pass depth 0.0031 inches, stepover 0.002 inches, clearance pass 0.002 inches, cutting diameter 0.25 inches and shank diameter 0.25 inches. Its included angle is 30°; the Engraving side angle is 15°. Earlier example settings in the conversation were not applied as source overrides.

## Rebuild

Place the source database and older linked PDF under `Amana-Database/sources/`. Run `python Amana-Database/extract_database.py`, then `node Amana-Database/build_workbook.mjs` with `@oai/artifact-tool` available. The builder writes the latest 12-column workbook under `artifacts/` and inspection/previews under `Amana-Database/`.

The scripts and workbook have been checked for row counts, source IDs, sort order, numeric conversions, frozen panes, Excel error cells, and ZIP integrity. The spreadsheet is a source reference; it does not certify tool stress limits or safe settings for other brands.
