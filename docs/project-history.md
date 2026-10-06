# Project history and remaining work

## Earlier cutting-board exploration

The initial design was a 14 × 18-inch, 1.5-inch-thick walnut cutting board with maple script lettering about 10 × 12 inches and a rounded juice groove. Available V-bits included 30°, 60°, and 90° tools. The Amana 45771-K engraving definition was visible in the general Tool Database but its compatibility with the automatic inlay selector prompted exploration of the manual V-Carve/Engraving method.

The conversation explored start/flat depths, plug staging, clearance tool order, manual bit changes, XY/Z references, and long engraving estimates. A 0.002-inch stepover and initially very small pass depth produced lengthy finishing paths. Smaller clearing tools can only clear regions their geometry can reach; adding them cannot eliminate every fine V-bit pass. Increasing feeds or pass depths without actual cutter/load verification was not established as a safe solution.

No final native cutting-board project, lettering vectors, or juice-groove machining file was produced. Earlier manual plug discussions, including a proposed 0.195-inch figure, are superseded for the coaster and should not be treated as executable settings.

## Coaster and direct CAM

The scope changed to a 4-inch-square maple coaster with walnut Purdue logo inlay. The registered mark was removed and the logo was given half-inch lateral margins. The original malformed DXF was corrected with an R12-compatible export. The user previewed their VCarve results, then requested six independently generated PlanetCNC programs. Those programs and simulation reports are retained as experimental work.

The final 60° bit was identified by a photo as a generic three-flute V-groove tool, not Amana 45624-K. Final blanks were confirmed as 4 × 4 × 0.5 inches each. Existing older input instructions still retain the earlier one-inch walnut proposal; the current Markdown workflow resolves the discrepancy.

## Spreadsheet evolution

The full Amana library was extracted, initially exposing all VCarve geometry/cutting fields and presets. The user then narrowed the fields, requested catalog IDs, excluded boring/drill tools, added cutting categories and diameters, refined layout and alignment, and specified the final custom type/shank/cutting-diameter sort. Historical workbooks remain in `outputs/`; the stable current workbook is in `artifacts/`.

## Unfinished or unverified

- Physical trial of the paired inlay and the six independent CAM programs.
- Verified limits and feed/RPM recommendations for the actual non-Amana cutters.
- Confirmation of usable sharp-tip 60° cutting geometry and cutting height.
- Inspection of the user's actual DWC postprocessor and controller setup.
- Native `.crv` project creation/export in the user's VCarve installation.
- Backing removal, perimeter profiling, and cutting-board juice-groove toolpaths.

## Public repository contents

This repository includes project-generated scripts, vectors, program files, previews, reports, extracted catalog data, spreadsheets, and these Markdown notes. Installed dependencies, local raw download inputs, third-party Vectric SDK distribution, SQLite sidecars, and temporary inspection dumps remain local and are ignored. No credentials or local account configuration are intended to be published.
