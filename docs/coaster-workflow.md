# Coaster design and VCarve workflow

## Final agreed design

| Setting | Value |
|---|---|
| Maple pocket blank | 4 × 4 × 0.5 inches |
| Walnut plug blank | 4 × 4 × 0.5 inches |
| Logo | Purdue P, registered mark removed |
| Logo width | 3 inches |
| Logo height | Approximately 1.60565 inches |
| Logo center | X = 2, Y = 2 inches |
| Maple regions | White regions, including outside the P |
| Walnut regions | Black regions |
| Maximum pocket depth | 0.125 inches |
| Glue gap | 0.005 inches |
| Surface gap | 0.050 inches |
| Nominal insertion at full depth | 0.120 inches |
| Nominal plug background depth | 0.170 inches |

Earlier notes described one-inch walnut. That was superseded by the final confirmation that both blanks are half an inch thick. `START-HERE.txt` and `vcarve-setup.json` are retained historical inputs, not the current stock specification.

## Vectors

Use `coaster/purdue-coaster-logo-3in.dxf` or the corresponding SVG. Import one, not both. Five closed contours describe the outer boundaries and maple channels/holes. The vector files contain geometry, not machining instructions. `Purdue-Coaster-Fixed.dxf` is the corrected R12 root-level export; the original root-level `Purdue-Coaster.dxf` was superseded after VCarve reported a line/offset 50 import error.

## VCarve setup

1. File → New: single-sided, inches, 4 × 4 × 0.5 inches, Z zero at original stock top, XY datum lower-left.
2. File → Import → Import Vectors/Bitmaps: load one logo vector file.
3. Select the complete logo, confirm 3-inch width and center at X/Y = 2/2. Keep the contours together.
4. Add a Walnut Plug sheet with the final 4 × 4 × 0.5-inch stock settings.
5. Define the actual pointed 60° included-angle V-bit and the 1/4- and 1/8-inch endmills in Tool Database. Cutter shank size alone does not identify cutting diameter or cutting length.
6. Use VCarve Inlay Toolpath for the automatic matched tapered pocket/plug. Select the complete unmirrored logo; the automatic workflow generates the mirrored plug. Do not also mirror it manually.
7. Enter pocket depth 0.125, glue gap 0.005, surface gap 0.050 inches. Enable clearance tools, larger endmill first. Confirm the plug boundary and workholding clearance in preview.
8. Preview both sheets and save the native `.crv` project. A native `.crv` file is not present in this repository.
9. Save separate toolpaths for each cutter and stock using the user's selected `Digital Wood Carver (inch) (*.tap)` postprocessor. `Imported` is the machine-profile label. The postprocessor contents have not been independently reviewed.

VCarve's straight-sided Inlay Toolpath and tapered VCarve Inlay Toolpath are different workflows. The older manual V-Carve/Engraving method requires its own plug depth treatment; its settings must not be mixed with the automatic inlay workflow or the independent CAM programs here. Narrow features may be shallower than the maximum pocket depth.

## Physical references and tool changes

The physical XY zero must match the selected job datum. A lower-left job datum is the corner of the defined stock/job area, not an arbitrary visible edge of the logo. If the blank is larger than the job, establish the job corner deliberately.

For manual bit changes on unmoved stock, retain XY and establish the new cutter's Z against the original top plane or the correct tool-measuring routine. A cleared pocket floor is not the original top. Remounting the walnut is a new setup with its own XY and Z references.

## Tools discussed

- Quarter-inch Eanosic E218-Up Cut endmill.
- Eighth-inch Eyryfui EF27 three-flute spiral, quarter-inch shank.
- Generic 60° three-flute V-groove bit, package code CXZ20260121, quarter-inch shank, 2.5-inch overall length. It was initially misidentified as Amana and later corrected.
- Amana 45771-K: 30° included-angle engraving cutter with a nominal 0.005-inch tip. VCarve's Engraving definition displays a 15° side angle. This is a different tool from the generic 60° cutter.

The tool database describes geometry and programmed cutting settings; it does not certify a bit's physical stress limit. No universal 18,000-RPM recommendation was verified for the three non-Amana tools.

## References

- [VCarve 12.5 file menu](https://docs.vectric.com/docs/V12.5/VCarvePro/ENU/Help/form/file-menu/index.html)
- [VCarve Inlay Toolpath](https://docs.vectric.com/docs/V12.5/VCarvePro/ENU/Help/form/VCarve%20Inlay%20Toolpath/)
- [Saving toolpaths](https://docs.vectric.com/docs/V12.5/VCarvePro/ENU/Help/form/Save%20Toolpaths/index.html)
