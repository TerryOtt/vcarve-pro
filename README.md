# VCarve Pro wood inlays

Design files, experimental CAM code, and an Amana Hardwood tool reference developed for a Digital Wood Carver 2440 using VCarve Pro 12.5.11 and PlanetCNC 2023.05.04. Tool changes are manual.

## Project notes

- [Coaster design and VCarve workflow](docs/coaster-workflow.md)
- [Experimental direct-generated PlanetCNC programs](docs/planetcnc-programs.md)
- [Amana database and spreadsheet](docs/amana-tool-reference.md)
- [Project history and remaining work](docs/project-history.md)

## Latest spreadsheet

[Amana Hardwood router bits](artifacts/Amana-Hardwood-Router-Bits.xlsx): 638 tool definitions with Hardwood presets. The full library and earlier workbook revisions are retained under `outputs/`.

Columns: Cutting Type, Shank Diameter, Tool ID, Cutting Diameter (D), Spindle Speed, Feed Rate, Plunge Rate, Number of Flutes, Pass Depth, Stepover, Clearance Pass, Original Definition Name.

## Files and status

- `coaster/`: five closed logo contours, SVG/DXF import files, tracing and CAM source, geometry checks, previews.
- `PlanetCNC/`: six experimental `.tap` programs, swept-tool simulation images, numerical report, and detailed operating assumptions.
- `Amana-Database/`: extraction/build scripts, extracted source data, and spreadsheet checks.
- `artifacts/`: current workbook with a stable filename.
- `outputs/`: historical spreadsheet iterations.

The CNC programs have been checked geometrically but **have not been run on the DWC or physically test fitted**. Their settings are generic trial settings, not verified limits for the actual cutters. See the detailed [program status](docs/planetcnc-programs.md) before using them.

## Reproducing the work

Python scripts need NumPy, Pillow, ezdxf, Shapely, SciPy, and pypdf; see `requirements.txt`. Vector tracing accepts the source image path as its first argument. The original user-supplied image is not included; existing vectors are included.

The spreadsheet builder uses `@oai/artifact-tool` from the Codex bundled runtime. That environment-specific dependency is not bundled here. Download the Amana source database and linked PDF into `Amana-Database/sources/`, run `extract_database.py`, then `build_workbook.mjs` in an environment providing that package. See the tool-reference notes for source links.

Downloaded Vectric SDK files, dependency installations, temporary inspection dumps, and SQLite sidecars are excluded. Generated artwork is based on a user-supplied Purdue logo; Purdue marks remain the property of their owner. Inclusion here does not grant trademark or third-party database rights.
