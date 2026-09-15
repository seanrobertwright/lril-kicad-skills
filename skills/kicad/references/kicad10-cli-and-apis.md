# KiCad 10.0.6 programmatic surface — verified facts

Research date: 2026-09-14. Host: Windows 11, KiCad 10.0.6 release build at
`C:\Program Files\KiCad\10.0` (`KICAD_IPC_API=ON`, OCC 7.9.2, ngspice 46,
bundled CPython 3.11.5). Everything marked **verified** was executed on this
machine; everything marked **docs/source** came from docs.kicad.org,
dev-docs.kicad.org, or the `10.0` branch of gitlab.com/kicad/code/kicad.

Scratch artefacts (help dumps, JSON outputs, jobsets, the SWIG script) live under
`<scratch>\cli\`
(`help-all.txt`, `ecc83\`, `interf_u\`, `swig_board\`, `swig_make_board.py`, `upgrade\`).

---

## 1. kicad-cli command tree (verified, `--help` on every leaf)

```
kicad-cli {fp,jobset,pcb,sch,sym,version}
  version [--format plain|commit|about]
  sch   {erc, export {bom,dxf,hpgl,netlist,pdf,ps,python-bom,svg}, upgrade}
  pcb   {drc, export {3dpdf,brep,drill,dxf,gencad,gerbers,glb,hpgl*,ipc2581,ipcd356,
                      odb,pdf,ply,pos,ps,stats,step,stl,stpz,svg,u3d,vrml,xao},
         import, render, upgrade}
  fp    {export svg, upgrade}
  sym   {export svg, upgrade}
  jobset {run}
```
`*` `pcb export hpgl` prints "No longer supported as of KiCad 10.0." There is **no**
`api-server` subcommand in 10.0.6 (verified) — headless IPC is KiCad 11.

Global conventions seen on most commands:
- `-o/--output` — a *file* for single-output commands, a *directory* for multi-file
  ones (gerbers, drill, pcb pdf/svg/dxf/ps multi mode, sch svg/dxf/ps). Trailing
  slash on directories is safe.
- `-D/--define-var KEY=VALUE` (repeatable) overrides project text variables.
- `--variant NAME` (repeatable) on most sch/pcb exports; use `${VARIANT}` in the
  output path when passing several. No `--variant` → default variant.
- `--layers` / `--common-layers` take comma-separated *untranslated* names
  (`F.Cu,B.Cu,Edge.Cuts`). Docs: user-renamed layer names are matched first, then
  canonical names.
- Layer-renamed boards produce Gerber file names from the user names (ecc83 demo
  emits `ecc83-pp_v2-Dessus.gtl` / `-Dessous.gbl`, verified).

### `sch erc` (verified)
```
sch erc [-o OUTPUT_FILE] [-D KEY=VALUE]... [--format report|json] [--units in|mm|mils]
        [--severity-all] [--severity-error] [--severity-warning] [--severity-exclusions]
        [--exit-code-violations] INPUT_FILE
```
Defaults: `--format report`, `--units mm`, severities error+warning.
`--exit-code-violations` → exit **5** when violations exist (docs + verified on
interf_u: "Found 1 violations", exit 5). Exit 0 otherwise.

### `pcb drc` (verified)
```
pcb drc [-o OUTPUT_FILE] [-D KEY=VALUE]... [--format report|json] [--all-track-errors]
        [--schematic-parity] [--units in|mm|mils] [--severity-all] [--severity-error]
        [--severity-warning] [--severity-exclusions] [--exit-code-violations]
        [--refill-zones] [--save-board] INPUT_FILE
```
`--save-board` requires `--refill-zones`. `--schematic-parity` needs the sibling
`.kicad_sch`/`.kicad_pro` next to the board and a fully annotated schematic
("Failed to fetch schematic netlist for parity tests" otherwise). Exit 5 with
`--exit-code-violations` when violations exist (verified, interf_u: 3 violations).

### `sch export netlist` (verified)
```
export netlist [-o OUTPUT_FILE] [--variant VAR]... [--format FORMAT] INPUT_FILE
--format: kicadsexpr (default), kicadxml, cadstar, orcadpcb2, spice, spicemodel, pads, allegro
```

### `sch export bom` (verified)
```
export bom [-o OUTPUT_FILE] [--variant VAR]... [--preset PRESET] [--format-preset FMT_PRESET]
  [--fields FIELDS] [--labels LABELS] [--group-by GROUP_BY] [--sort-field SORT_BY]
  [--sort-asc true|false] [--filter FILTER] [--exclude-dnp] [--include-excluded-from-bom (deprecated, no-op)]
  [--field-delimiter ,] [--string-delimiter "] [--ref-delimiter ,] [--ref-range-delimiter -]
  [--keep-tabs] [--keep-line-breaks] INPUT_FILE
```
- `--fields` default `Reference,Value,Footprint,QUANTITY,DNP`; generated fields
  `QUANTITY, ITEM_NUMBER, DNP, EXCLUDE_FROM_BOM, EXCLUDE_FROM_BOARD, EXCLUDE_FROM_SIM`
  accepted with or without `${}`.
- `--labels` default `Refs,Value,Footprint,Qty,DNP`.
- `--preset` / `--format-preset` name presets stored in the `.kicad_pro`
  (`schematic.bom_presets`, `schematic.bom_fmt_presets`, plus
  `bom_settings`, `bom_fmt_settings`, `bom_export_filename` keys — verified in
  ecc83's project file).
- Verified command and output:
  ```
  kicad-cli sch export bom --fields 'Reference,Value,Footprint,${QUANTITY},${DNP},${ITEM_NUMBER}' \
      --labels 'Refs,Value,Footprint,Qty,DNP,Item' --group-by 'Value,Footprint' --exclude-dnp \
      -o bom2.csv ecc83-pp_v2.kicad_sch
  "Refs","Value","Footprint","Qty","DNP","Item"
  "C1","10uF","Capacitor_THT:CP_Radial_D12.5mm_P7.50mm","1","","1"
  "R1,R2","1.5K","Resistor_THT:R_Axial_DIN0207_...","2","",""    <- grouped rows
  ```
  PowerShell gotcha: quote `${...}` with single quotes, otherwise PowerShell
  expands it to nothing.

### `sch export pdf|svg|dxf|ps|hpgl` (verified help)
Common flags: `-o`, `--drawing-sheet SHEET_PATH`, `-D`, `--variant`, `-t/--theme`,
`-b/--black-and-white`, `-e/--exclude-drawing-sheet`, `--default-font`,
`--draw-hop-over`, `--pages 1,2,3`. PDF only: `-o` is a *file*,
`--exclude-pdf-property-popups`, `--exclude-pdf-hierarchical-links`,
`--exclude-pdf-metadata`, `-n/--no-background-color`. svg/dxf/ps/hpgl: `-o` is a
*directory*; output name is `<sheetname>.svg` etc. `python-bom` has only `-o`
(legacy XML for BOM scripts). hpgl `--pen-size`/`--origin` are deprecated no-ops.

### `pcb export gerbers` (verified)
```
export gerbers [-o OUTPUT_DIR] [-l LAYER_LIST] [--cl COMMON_LAYER_LIST] [--drawing-sheet PATH] [-D ..]
  [--erd/--exclude-refdes] [--ev/--exclude-value] [--ibt/--include-border-title]
  [--sp/--sketch-pads-on-fab-layers] [--hdnp ...] [--sdnp ...] [--cdnp ...]
  [--no-x2] [--no-netlist] [--subtract-soldermask] [--disable-aperture-macros]
  [--use-drill-file-origin] [--precision 5|6 (default 6)] [--no-protel-ext] [--check-zones]
  [--variant ..]... [--board-plot-params] INPUT_FILE
```
Output: one file per layer plus `<board>-job.gbrjob`. With no `--layers` and no
`--board-plot-params` it plotted only the layers enabled in the board's stored
plot settings (4 files for ecc83). `--board-plot-params` uses the board file's
saved Gerber settings.

### `pcb export drill` (verified)
```
export drill [-o OUTPUT_DIR] [--format excellon|gerber] [--drill-origin absolute|plot]
  [--excellon-zeros-format decimal|suppressleading|suppresstrailing|keep]
  [--excellon-oval-format route|alternate] [-u/--excellon-units in|mm (default mm)]
  [--excellon-mirror-y] [--excellon-min-header] [--excellon-separate-th]
  [--generate-map] [--generate-report] [--report-path FILE] [--generate-tenting]
  [--map-format pdf|gerberx2|ps|dxf|svg] [--gerber-precision 5|6] INPUT_FILE
```
Verified output with `--excellon-separate-th --generate-map --map-format gerberx2`:
`<board>-PTH.drl`, `<board>-NPTH.drl`, `<board>-PTH-drl_map.gbr`, `<board>-NPTH-drl_map.gbr`.

### `pcb export pos` (verified)
```
export pos [-o OUTPUT_FILE] [--side front|back|both] [--format ascii|csv|gerber]
  [--units in|mm (default in!)] [--bottom-negate-x] [--use-drill-file-origin] [--smd-only]
  [--exclude-fp-th] [--exclude-dnp] [--gerber-board-edge] [--variant ..]... INPUT_FILE
```
CSV header: `Ref,Val,Package,PosX,PosY,Rot,Side`. **Y is negated** (KiCad's
positive-down board Y is flipped to positive-up), e.g. `"C1","10uF",...,133.1,-102.9,90,top`.
Default units are inches — pass `--units mm` explicitly.

### `pcb export step|glb|brep|xao|ply|stl|u3d|stpz|3dpdf` (verified help; step/glb run)
Shared flags: `-o FILE`, `-f/--force` (overwrite), `--no-unspecified`, `--no-dnp`,
`--variant`, `--grid-origin`, `--drill-origin`, `--user-origin 25.4x25.4mm`,
`--subst-models`, `--board-only`, `--no-board-body`, `--no-components`,
`--component-filter R*,C1`, `--net-filter`, `--include-tracks`, `--include-pads`,
`--include-zones`, `--include-inner-copper`, `--include-silkscreen`,
`--include-soldermask`, `--fuse-shapes`, `--fill-all-vias`, `--cut-vias-in-body`,
`--no-extra-pad-thickness`, `--min-distance 0.01mm`; step/stpz add
`--no-optimize-step`. `vrml` differs: `--units mm|m|in|tenths`, `--models-dir`,
`--models-relative`.
**Exit-code gotcha:** STEP export of ecc83 wrote a valid file but returned **exit 2**
because footprints referenced missing `${KICAD6_3DMODEL_DIR}/...wrl` models
("Could not add 3D model for C1 ... Cannot use VRML models when exporting to
non-mesh formats"). A board with no models (SWIG board) returned 0. GLB with the
same missing models returned 0. Treat exit 2 from step as "file written, models
missing" — check that the file exists before failing.

### `pcb export svg|pdf|dxf|ps` (verified help; svg/pdf run)
Common: `-l/--layers`, `--cl/--common-layers`, `--drawing-sheet`, `-D`, `-m/--mirror`,
`--erd`, `--ev`, `--ibt`, `--subtract-soldermask`, `--sp/--hdnp/--sdnp/--cdnp`,
`-n/--negative`, `--black-and-white`, `-t/--theme`, `--drill-shape-opt 0|1|2`,
`--scale` (0 = auto), `--check-zones`, `--variant`.
- svg: `--page-size-mode 0|1|2` (0 frame+title, 1 current page, 2 board area only),
  `--fit-page-to-board`, `--exclude-drawing-sheet`, `--mode-single` (`-o` is a file
  path, `--common-layers` ignored) or `--mode-multi` (`-o` is a directory).
- pdf: `--mode-single`, `--mode-separate` (one PDF per layer), `--mode-multipage`,
  `--bg-color #rrggbb|rgba(...)`, `--no-property-popups`.
- dxf: `--uc/--use-contours`, `--udo/--use-drill-origin`, `--ou/--output-units mm|in (default in)`,
  `--mode-single|--mode-multi`.
- ps: adds `-C/--track-width-correction`, `-X/-Y` scale factors, `-A/--force-a4`.

### `pcb export stats` (verified)
```
export stats [-o OUTPUT_FILE] [--format report|json] [--units in|mm]
  [--exclude-footprints-without-pads] [--subtract-holes-from-board] [--subtract-holes-from-copper] INPUT_FILE
```

### `pcb export ipc2581 | odb | ipcd356 | gencad` (verified help; ipc2581/odb/ipcd356 run OK)
- ipc2581: `-o FILE`, `--drawing-sheet`, `-D`, `--precision 6`, `--compress`,
  `--version B|C`, `--units mm|in`, `--bom-col-int-id|--bom-col-mfg-pn|--bom-col-mfg|--bom-col-dist-pn|--bom-col-dist FIELD`, `--bom-rev`, `--variant`.
- odb: `-o FILE`, `--drawing-sheet`, `-D`, `--precision 2`, `--compression zip|none|tgz`, `--units mm|in`, `--check-zones`, `--variant`.
- ipcd356: `-o FILE` only. gencad: `-o DIR`, `-f/--flip-bottom-pads`, `--unique-pins`, `--unique-footprints`, `--use-drill-origin`, `--store-origin-coord`.

### `pcb render` (verified, PNG produced in ~0.5 s at basic quality)
```
pcb render [-o OUTPUT_FILE] [-D ..] [--variant ..] [-w/--width 1600] [-h/--height 900]
  [--side top|bottom|left|right|front|back] [--background default|transparent|opaque]
  [--quality basic|high|user|job_settings] [--preset follow_pcb_editor|follow_plot_settings|<name>]
  [--use-board-stackup-colors] [--floor] [--perspective] [--zoom 1] [--pan X,Y,Z]
  [--pivot X,Y,Z (cm from board centre)] [--rotate X,Y,Z ('-45,0,45' = isometric)]
  [--light-top|--light-bottom|--light-side|--light-camera R,G,B|n (0-1)] [--light-side-elevation 60] INPUT_FILE
```
Output type is by extension (`.png` or `.jpg`). Note `-h` is *height* here, use
`--help` for help. Prints ~80 progress lines to stdout.

### `pcb import` (new in 10; verified help)
`pcb import [-o OUTPUT_FILE] [--format auto|pads|altium|eagle|cadstar|fabmaster|pcad|solidworks] [--report-format none|json|text] [--report-file FILE] INPUT_FILE`

### `sch upgrade`, `pcb upgrade` (`--force`), `sym upgrade` / `fp upgrade` (`-o`, `--force`) — verified
In-place resave to the current format (the way to normalise a file or learn the
current version number). `fp upgrade` takes a `.pretty` directory.

### `fp export svg` / `sym export svg` (verified)
- `fp export svg -o DIR [-l LAYERS] [-t THEME] [--fp/--footprint NAME] [--sp/--hdnp/--sdnp/--cdnp] [--black-and-white] LIB.pretty`
  → `NAME.svg`.
- `sym export svg -o DIR [-t THEME] [-s/--symbol NAME] [--black-and-white] [--include-hidden-pins] [--include-hidden-fields] LIB.kicad_sym`
  → `NAME_unit1.svg`.

### `jobset run` (verified)
`jobset run [--stop-on-error] [-f/--file JOB_FILE] [--output OUTPUT] INPUT_FILE`
where INPUT_FILE is the `.kicad_pro` (a bare `.kicad_pcb` also worked for a
pcb-only jobset) and `--output` selects one destination by its **description or id**
(docs: description must be unique). See section 5 for the JSON format.

---

## 2. ERC / DRC / netlist / stats outputs (verified on demos)

Commands run (project copied to scratchpad first):
```
kicad-cli sch erc --format json --severity-all --units mm -o erc.json ecc83-pp_v2.kicad_sch
kicad-cli pcb drc --format json --severity-all --schematic-parity --all-track-errors -o drc.json ecc83-pp_v2.kicad_pcb
kicad-cli sch export netlist --format kicadsexpr -o ecc83.net ecc83-pp_v2.kicad_sch
kicad-cli pcb export stats --format json -o stats.json ecc83-pp_v2.kicad_pcb
```
Exit codes: 0 with no `--exit-code-violations`; 5 when violations exist and the
flag is given (interf_u ERC/DRC). Stdout always prints `Found N violations`
(DRC also `Found N unconnected items` and, with parity, `Found N schematic parity issues`)
plus `Saved ... Report to <path>`.

### ERC JSON (`$schema: https://schemas.kicad.org/erc.v1.json`)
```json
{
  "$schema": "https://schemas.kicad.org/erc.v1.json",
  "coordinate_units": "mm",
  "date": "2026-09-14T18:51:44",
  "ignored_checks": [ { "description": "Global label only appears once in the schematic", "key": "single_global_label" }, ... ],
  "included_severities": [ "error", "warning", "exclusion" ],
  "kicad_version": "10.0.6",
  "sheets": [
    { "path": "/", "uuid_path": "/e63e39d7-...", "violations": [ <violation>... ] }
  ],
  "source": "ecc83-pp_v2.kicad_sch"
}
```
Violations are **nested per sheet** (`sheets[].violations[]`). Real example (interf_u):
```json
{ "description": "Footprint 'DSUB-25_...' not found in library 'Connector_Dsub'",
  "items": [ { "description": "Symbol P1 [DB25_Female]", "pos": { "x": 3.8227, "y": 1.8288 }, "uuid": "00000000-0000-0000-0000-00003256759c" } ],
  "severity": "warning", "type": "footprint_link_issues" }
```

### DRC JSON (`$schema: https://schemas.kicad.org/drc.v1.json`)
Top-level keys: `$schema, coordinate_units, date, ignored_checks, included_severities,
kicad_version, schematic_parity, source, unconnected_items, violations`.
Three parallel arrays of the same violation shape:
```json
{ "description": "Board edge clearance violation (board setup constraints edge clearance 0.5000 mm; actual 0.0000 mm)",
  "items": [
    { "description": "Segment on Edge.Cuts", "pos": { "x": 172.085, "y": 133.35 }, "uuid": "3e0555e0-..." },
    { "description": "Zone [GND] on bottom_copper, priority 0", "pos": { "x": 193.675, "y": 133.35 }, "uuid": "..." } ],
  "severity": "error", "type": "copper_edge_clearance" }
```
- `pos` is in `coordinate_units` (default mm; `--units in|mils` changes both the
  numbers and the `coordinate_units` string). Absolute sheet/board coordinates.
- `severity` ∈ `error | warning | exclusion` (exclusions only with
  `--severity-exclusions`/`--severity-all`); `type` is the DRC/ERC rule key
  (e.g. `copper_edge_clearance`, `starved_thermal`, `shorting_items`,
  `solder_mask_bridge`, `via_dangling`, `isolated_copper`, `unconnected_items`,
  `footprint_symbol_mismatch`, `footprint_link_issues`). Layer names in
  descriptions use the *user* layer names (`bottom_copper` for a renamed B.Cu).
- `items` has 1–2 entries; `uuid` is the object's KIID (legacy imports show
  `00000000-0000-0000-0000-0000xxxxxxxx`).
- `schematic_parity` entries have `type: footprint_symbol_mismatch` etc.
- The text `--format report` is a human report: header line
  `ERC report (2026-..., Encoding UTF8)`, `** ERC messages: N Errors N Warnings N`, sheet sections, ignored checks.

### Netlist (kicadsexpr, `(export (version "E") ...)`)
Top-level children: `version`, `design` (source, date, tool "Eeschema 10.0.6",
`sheet` with `title_block`), `components` (`comp` with `ref, value, footprint,
fields, libsource(lib part description), property* (Sheetname, Sheetfile,
ki_keywords, ki_fp_filters …), sheetpath(names tstamps), tstamps, units`), `groups`,
`variants` (new in 10), `libparts` (`libpart` with `footprints (fp …)`, `fields`,
`pins (pin num name type)`), `libraries`, `nets` (`net (code "1") (name "GND")
(class "Default") (node (ref "C1") (pin "2") (pintype "passive") [pinfunction])`).
All values are quoted strings, including numbers. `kicadxml` is the same tree as
XML (`<export version="E">`); `python-bom` emits the same XML. `spice` produces
`.title KiCad schematic` + element lines (`R3 Net-_P2-P1_ GND 100k`).

### Stats JSON (no `$schema`)
```json
{ "metadata": { "date", "generator": "KiCad 10.0.6", "project", "board_name" },
  "board": { "has_outline": true, "width": "48.2600 mm", "height": "41.9100 mm", "area": "2022.577 mm²",
             "front_component_density": "48.28", "front_copper_area": "210.936 mm²", "min_track_clearance": "1.0414 mm",
             "min_track_width": "0.8636 mm", "min_drill_diameter": "0.8000 mm", "board_thickness": "1.6000 mm", ... },
  "pads": { "through_hole": 34, "smd": 0, "connector": 0, "npth": 0, "castellated": 0, "press_fit": 0 },
  "vias": { "through": 0, "blind": 0, "buried": 0, "micro": 0 },
  "components": { "tht": {"front","back","total"}, "smd": {...}, "unspecified": {...}, "total": {...} },
  "drill_holes": [ { "count": 10, "shape": "Round", "x_size": "0.8000 mm", "y_size": "0.8000 mm", "plated": true, "source": "Pad", "start_layer": "Dessus", "stop_layer": "Dessous" } ] }
```
Gotcha: dimensional values are **strings with units** ("48.2600 mm"), counts are ints.

---

## 3. SWIG `pcbnew` from the bundled Python (verified headless)

```
& "C:\Program Files\KiCad\10.0\bin\python.exe" -c "import pcbnew; print(pcbnew.GetBuildVersion())"   -> 10.0.6
pcbnew.__file__ -> C:\Program Files\KiCad\10.0\bin\Lib\site-packages\pcbnew.py ; Python 3.11.5
```
The requested probe printed: `['FOOTPRINT', 'FOOTPRINTS', 'FOOTPRINT_COURTYARD_CACHE_DATA',
'FOOTPRINT_GEOMETRY_CACHE_DATA', 'FOOTPRINT_STACKUP_CUSTOM_LAYERS',
'FOOTPRINT_STACKUP_EXPAND_INNER_LAYERS', 'FOOTPRINT_VARIANT', 'GetDefaultPlotExtension',
'LoadBoard', 'PlotDrawingSheet', 'SaveBoard']`.

Script `scratchpad\cli\swig_make_board.py` ran to completion (exit 0) and did all of:
`BOARD()`, four `PCB_SHAPE` `SHAPE_T_SEGMENT` on `Edge_Cuts` (+ a `SHAPE_T_RECT`),
`NETINFO_ITEM(board,"VCC")` + `board.Add(net)`,
`pcbnew.FootprintLoad("C:/Program Files/KiCad/10.0/share/kicad/footprints/Resistor_SMD.pretty","R_0603_1608Metric")`,
`fp.SetReference/SetValue/SetPosition/SetOrientationDegrees`, `pad.SetNet(net)`,
`PCB_TRACK`, `PCB_VIA` (`SetDrill/SetWidth`), `ZONE` + `Outline().NewOutline()/Append()`,
`ZONE_FILLER(board).Fill(board.Zones())` (works headless), `PCB_TEXT`,
`SaveBoard(path, board)` → True, `LoadBoard(path)` round-trip, `GetBoardEdgesBoundingBox()`.
Then `kicad-cli pcb drc --format json --severity-all --exit-code-violations` on the
saved file ran the real DRC engine: 6 violations (shorting_items,
copper_edge_clearance ×2, solder_mask_bridge, via_dangling, isolated_copper) +
2 unconnected_items, exit 5 — i.e. the SWIG-authored board is a first-class
`.kicad_pcb` (`(version 20260206) (generator "pcbnew") (generator_version "10.0")`).

Availability confirmed: `NewBoard`, `LoadBoard`, `SaveBoard`, `FootprintLoad`,
`FootprintSave`, `FootprintEnumerate`, `GetBoard`, `PLOT_CONTROLLER`,
`PLOT_FORMAT_GERBER`, `EXCELLON_WRITER`, `WriteDRCReport` all exist.

Gotchas (verified):
- Internal units are **nanometres**: `FromMM(1.0) == 1000000`, `ToMM`, `FromMils(100) == 2540000`.
  Positions are `VECTOR2I(x, y)`; helper `VECTOR2I_MM(10, 20)` exists; legacy
  `wxPoint`/`wxPointMM` still present but avoid.
- `FootprintLoad` by *path* returns a footprint whose FPID has **no library nickname**
  (`GetFPIDAsString() == "R_0603_1608Metric"`, saved as `(footprint "R_0603_1608Metric"`).
  Call `fp.SetFPID(pcbnew.LIB_ID("Resistor_SMD", "R_0603_1608Metric"))` so the
  file records `Resistor_SMD:R_0603_1608Metric`; otherwise schematic-parity DRC and
  library re-linking will complain. Loading by nickname (fp-lib-table) is not
  available headless without a project.
- Use forward slashes or raw strings for Windows paths passed to SWIG.
- `board.Zones()` returns a Python **tuple** (no `.size()`); `GetFootprints()`,
  `GetTracks()`, `GetDrawings()` are iterable/len-able.
- `GetDesignSettings()` has no `GetDefaultNetClass()`; `m_TrackMinWidth` etc. are
  attributes (0.2 mm default).
- The bundled python has no `._pth` and `sys.flags.ignore_environment == 0`, yet
  `PYTHONPATH` set in the same PowerShell command was not honoured for a
  `--target` dir; `sys.path.insert(0, target)` in the script works reliably.
- `pip` is bundled (26.2.1). Use `-m pip install --target <dir>` to avoid touching
  `Program Files`.
- Deprecation (dev-docs): "The SWIG-based Python bindings in KiCad are deprecated
  as of KiCad 9.0 … The current plan is to remove the SWIG bindings in KiCad 11.0."

**Schematic SWIG: none.** `import eeschema` → `No module named 'eeschema'`;
`import kicad` → `No module named 'kicad'`; the only "SCHEMATIC" symbols in pcbnew
are layer-colour enums. dev-docs: "Python bindings are provided for the PCB editor
only at this time." Schematic generation must be done by writing `.kicad_sch`
s-expressions directly (then validate with `kicad-cli sch erc`/`sch upgrade`).

---

## 4. kicad-python (`kipy`) / IPC API

Docs/source facts:
- Package `kicad-python` (PyPI), import name `kipy`. Latest **0.8.0** (tag
  2026-08-30, "Release 0.8.0"); `kipy/kicad_api_version.py` →
  `KICAD_API_VERSION = "10.0.6-0-gcaf7377e9c"`. Earlier: 0.6.0 ↔ KiCad 9.0.8,
  0.4.0 ↔ 9.0.3, 0.2.0 ↔ 9.0.0. Requires Python ≥3.9, `protobuf>=5.29,<6`,
  `pynng>=0.9,<0.10`, `jsonschema>=4.23,<5`.
- Install (verified, into scratchpad, KiCad install untouched):
  `& "C:\Program Files\KiCad\10.0\bin\python.exe" -m pip install --target <dir> kicad-python`
  → `Successfully installed ... kicad-python-0.8.0 protobuf-5.29.6 pynng-0.9.0 ...`
- Transport: protobuf messages over nng; KiCad is the server. Windows socket:
  `ipc://%TEMP%\kicad\api.sock` (kipy `_default_socket_path`; Linux `ipc:///tmp/kicad/api.sock`).
  Env vars `KICAD_API_SOCKET` and `KICAD_API_TOKEN` are set by KiCad when it launches a
  plugin; `KiCad(socket_path=None, client_name=None, kicad_token=None, timeout_ms=2000)`
  reads them or falls back to the default path.
- Enable in the GUI: Preferences → Plugins → "Enable KiCad API" (PyPI README:
  "requires that KiCad be running with the API server enabled in Preferences > Plugins").
  Persisted in `%APPDATA%\kicad\10.0\kicad_common.json` as
  `"api": { "enable_server": false, "interpreter_path": "C:\\Program Files\\KiCad\\10.0\\bin\\pythonw.exe" }`
  (verified; on this machine the running KiCad GUI had it **off**, no `api.sock`,
  and `KiCad()` raised `kipy.errors.ConnectionError: Failed to connect to KiCad: Connection refused`).
- Plugins: `plugin.json` (schema shipped at
  `share\kicad\schemas\api.v1.schema.json`: `identifier`, `name`, `description`,
  `runtime {type: python|exec}`, `actions[]`) in
  `${KICAD_DOCUMENTS_HOME}/10.0/plugins`; KiCad creates a venv and installs declared
  requirements. API is synchronous; do not open multiple connections.
- **Headless**: dev-docs: "The IPC API in KiCad 9 and 10 only supports communication
  with a running instance of the KiCad GUI. Support for running in headless mode
  through 'kicad-cli' was added for KiCad 11." Verified: kicad-cli 10.0.6 has no
  `api-server` subcommand and kipy 0.8.0's `KiCad.__init__` has no `headless`
  parameter (the `kicad-python-main` docs showing `headless=True`, `open_document`,
  `get_schematic()` are for KiCad 11 / unreleased main).

What kipy 0.8.0 can do against a running KiCad 10 (verified module surface):
`KiCad`: `get_board, get_open_documents, get_project, run_action, get_version,
get_api_version, check_version, ping, get_kicad_binary_path, get_plugin_settings_path,
get_text_as_shapes, get_text_extents`.
`Board`: `get_footprints, get_pads, get_tracks, get_vias, get_zones, get_nets,
get_shapes, get_text, get_groups, get_dimensions, get_items(_by_id|_by_net|_by_netclass),
create_items, update_items, remove_items, begin_commit/push_commit/drop_commit,
get_selection/add_to_selection/clear_selection, hit_test, interactive_move,
flip_items, get_stackup, get_enabled_layers/set_enabled_layers, get_active_layer,
get_layer_name, get_netclass_for_nets, get_pad_shapes_as_polygons, get_item_bounding_box,
get_title_block_info/set_title_block_info, get_origin/set_origin, refill_zones,
save, save_as, revert, get_as_string, expand_text_variables, get_barcodes,
check_padstack_presence_on_layers`. `board_types` covers Footprint/Pad/PadStack/
Track/ArcTrack/Via/Zone/Net/BoardText/BoardShape/Dimension*/Group/Barcode/…
`project.Project`, `board_types`, `geometry`, `server`, `packaging` import cleanly.

**Broken in the 0.8.0 wheel (verified):** `kipy.schematic`, `kipy.board_jobs`,
`kipy.board_rules`, `kipy.wizards` fail to import
(`ImportError: cannot import name 'PageSettings' from 'kipy.common_types'`,
`couldn't resolve name '.kiapi.common.types.Units'`,
`cannot import name 'CustomRuleConstraintType'`, `no attribute 'WizardMetaInfo'`).
The wheel ships KiCad-11-era Python wrappers over KiCad-10-era generated `*_pb2`
protos; the `0.8.0` tag's `common_types.py` on GitLab indeed has no `PageSettings`.
KiCad 10 itself exposes no schematic IPC service, so for KiCad 10 treat kipy as
**board-only, GUI-only**: no schematic, no DRC/ERC, no plotting/export jobs
(those proto job messages exist but the module that wraps them does not load).
Cannot: run without the GUI, read/write files directly, plot. Use kicad-cli for all of that.

---

## 5. File formats and KiCad 10 additions

Current format versions written by 10.0.6 (verified via `kicad-cli … upgrade --force`
and cross-checked with `10.0` branch headers):

| File | version token | Source |
|---|---|---|
| `.kicad_sch` | `20260306` | `SEXPR_SCHEMATIC_FILE_VERSION 20260306 // Variant in_bom semantics corrected` |
| `.kicad_pcb` | `20260206` | `SEXPR_BOARD_FILE_VERSION 20260206 // Fix barcode and variant attribute serialization` |
| `.kicad_sym` | `20251024` | `SEXPR_SYMBOL_LIB_FILE_VERSION 20251024 // Updated properties formatting (do_not_autoplace, show_name)` |
| `.kicad_mod` | `20260206` | same header as board |
| `.kicad_pro` | JSON `meta.version: 1`; top keys `board, boards, libraries, meta, net_settings, pcbnew, sheets, text_variables` (template) |
| `.kicad_jobset` | JSON, `jobsFileSchemaVersion = 1` (no version key written) |
| `design-block-lib-table` | `(design_block_lib_table (version 7) (lib (name ..)(type "Table"|"KiCad")(uri ..)))` |

Header written: `(kicad_sch (version 20260306) (generator "eeschema") (generator_version "10.0") (uuid ..) (paper "A4") (title_block ..) (lib_symbols ..) …)`
and `(kicad_pcb (version 20260206) (generator "pcbnew") (generator_version "10.0") (general (thickness 1.6) (legacy_teardrops no)) (paper "A4") (layers …) (setup …) …)`.
Symbol-instance properties now carry `(show_name no) (do_not_autoplace no)` and
symbols carry `(exclude_from_sim no) (in_bom yes) (on_board yes) (in_pos_files yes) (dnp no)`.
Older versions still load (demos span sch 20230819–20260101, pcb 20241030–20260206);
KiCad rewrites on save, so generated files may target any version ≥ 20250114 and be
upgraded with `kicad-cli sch|pcb upgrade`.

Recent version history from the source headers (what a generator may need to emit/parse):
- Board: 20250324 jumper pads; 20250401 time-domain length tuning; 20250513 groups
  with design-block `lib_id`; 20250811 press-fit pads; 20250818 custom footprint
  layer counts; 20250829 rounded rectangles; 20250901 PCB points; 20250914
  `PCB_BARCODE`; 20250926 via types split blind/buried/through; 20251028 netcodes no
  longer written; 20251101 backdrill; 20260101 PCB variants with per-footprint
  overrides; 20260206 barcode/variant fix. The upgraded board also gained an
  `embedded_fonts` top-level token.
- Schematic: 20250827 custom body styles; 20250829 rounded rects; 20250901 stacked
  pin notation; 20250922 schematic variants; 20251012 flat hierarchy; 20251028
  property formatting; 20260101 PCB variants; 20260306 variant `in_bom` semantics.
- Symbol lib: 20250324 jumper pin groups; 20250925 bus alias in project file; 20251024 properties formatting.

KiCad 10.0 feature list (release post, 2026-03): design **variants** (shared schematic,
per-variant property/DNP changes; exposed everywhere as `--variant`), **jumpers**
(symbol pins / footprint pads treated as internally connected), **design blocks
extended to the PCB editor** (`.kicad_blocks` library folder containing `.kicad_block`
folders with a `.kicad_sch`, a `.kicad_pcb` and a `.json`), time-domain tuning +
**tuning profiles**, inner-layer objects in footprints, barcodes, hatched fills,
3D PDF export, native rounded rectangles, schematic groups, pin/gate swap, importers
for Allegro/PADS/gEDA, `kicad-cli pcb import`, hpgl PCB plotting removed.
The dev-docs `file-formats/` pages (sexpr-schematic, sexpr-pcb) are still the
KiCad-6-era token reference and do **not** document the version numbers or the
10.x tokens above; use the source headers and `upgrade --force` output as truth.

### Jobset JSON (`.kicad_jobset`) — verified by running
Not documented on docs.kicad.org beyond "jobset run runs a predefined jobset";
structure from `common/jobs/jobset.cpp` and confirmed executable:
```json
{
  "jobs": [
    { "id": "<uuid or any unique string>", "type": "pcb_drc", "description": "DRC",
      "settings": { "output_filename": "checks/drc.json", "format": "json", "severity": 48, "units": "mm",
                    "parity": false, "report_all_track_errors": false, "refill_zones": false, "save_board": false,
                    "fail_on_error": false } },
    { "id": "…", "type": "sch_erc", "description": "ERC",
      "settings": { "output_filename": "checks/erc.json", "format": "json", "severity": 52, "fail_on_error": false } },
    { "id": "…", "type": "pcb_export_gerbers", "description": "Gerbers",
      "settings": { "output_dir": "gerbers/", "layers": ["F.Cu","B.Cu","F.Mask","B.Mask","F.SilkS","Edge.Cuts"],
                    "layers_to_include_on_all_layers": ["Edge.Cuts"], "use_x2_format": true,
                    "include_netlist_attributes": true, "use_protel_file_extension": true, "precision": 6,
                    "subtract_solder_mask_from_silk": true, "create_gerber_job_file": true } },
    { "id": "…", "type": "pcb_export_drill", "description": "Drill",
      "settings": { "output_dir": "gerbers/", "format": "excellon", "units": "mm", "generate_map": true,
                    "map_format": "gerberx2", "excellon.combine_pth_npth": false } },
    { "id": "…", "type": "pcb_export_pos", "settings": { "output_filename": "assembly/${PROJECTNAME}-pos.csv", "format": "csv", "units": "mm", "side": "both", "single_file": true } },
    { "id": "…", "type": "sch_export_plot_pdf", "settings": { "output_filename": "docs/${PROJECTNAME}-schematic.pdf", "format": "pdf" } },
    { "id": "…", "type": "sch_export_bom", "settings": { "output_filename": "assembly/bom.csv", "fields_ordered": ["Reference","Value","Footprint","${QUANTITY}"], "fields_labels": ["Refs","Value","Footprint","Qty"], "fields_group_by": ["Value","Footprint"], "exclude_dnp": true } },
    { "id": "…", "type": "pcb_export_3d", "settings": { "output_filename": "3d/board.step", "format": "step", "overwrite": true } },
    { "id": "…", "type": "sch_export_netlist", "settings": { "output_filename": "netlist/${PROJECTNAME}.net", "format": "kicad" } },
    { "id": "…", "type": "pcb_export_stats", "settings": { "output_filename": "checks/stats.json", "format": "json" } },
    { "id": "…", "type": "pcb_render", "settings": { "output_filename": "docs/render.png", "format": "png", "width": 640, "height": 360, "quality": "basic", "side": "top", "rotation_x": -45, "rotation_z": 45 } }
  ],
  "outputs": [
    { "id": "…", "type": "folder",  "only": [], "description": "fab-folder", "settings": { "output_path": "C:/abs/path/out/folder" } },
    { "id": "…", "type": "archive", "only": ["<gerber job id>","<drill job id>"], "description": "gerber-zip",
      "settings": { "output_path": "C:/abs/path/out/${PROJECTNAME}-gerbers.zip", "format": "zip" } }
  ]
}
```
Job type identifiers (from `REGISTER_JOB` in `common/jobs/*.cpp`; all of the
following were run successfully unless noted): `pcb_drc`, `sch_erc`,
`pcb_export_gerbers`, `pcb_export_drill`, `pcb_export_pos`, `pcb_export_3d`
(`format`: step|stpz|brep|glb|vrml|xao|ply|stl|u3d|pdf), `pcb_export_svg`,
`pcb_export_pdf`, `pcb_export_dxf`, `pcb_export_ipc2581`, `pcb_export_odb`,
`pcb_export_stats`, `pcb_render`, `sch_export_bom`, `sch_export_netlist`
(`format`: kicad|xml|cadstar|orcadpcb2|spice|spicemodel|pads|allegro — note
`kicad`/`xml` here, not `kicadsexpr`/`kicadxml`), `sch_export_plot_pdf|svg|dxf|ps`
(`hpgl` deprecated), `special_execute` (`command`, `ignore_exit_code`,
`record_output` → writes `<jobid>.log`), `special_copyfiles` (`source`, `dest`,
`overwrite`, `zero_copies_error`). Not exercised but registered: `pcb_export_gencad`,
`pcb_export_ipcd356`, `pcb_export_ps`, `sch_export_pythonbom`, `fp_export_svg`,
`sym_export_svg`, `pcb_upgrade`, `sch_upgrade`, `fp_upgrade`, `sym_upgrade`, `pcb_import`.

Setting keys per job (source, `JOB_PARAM` names):
- base (`job.cpp`): `description`, and `output_filename` (file jobs) **or** `output_dir` (directory jobs: gerbers, drill, multi-file plots, sch svg/dxf/ps).
- rc jobs (`job_rc.cpp`): `units` in|mm|mils, `severity` int bitmask (`RPT_SEVERITY_WARNING 0x10`, `RPT_SEVERITY_ERROR 0x20`, `RPT_SEVERITY_EXCLUSION 0x04`; default 0x30=48; 52 adds exclusions — verified `included_severities`), `format` report|json, `fail_on_error` (default **true**: a DRC job with violations → "Job failed", `jobset run` exit **6**, verified).
- plot base (`job_export_pcb_plot.cpp`): `layers`, `layers_to_include_on_all_layers`, `mirror`, `black_and_white`, `negative`, `plot_footprint_values`, `plot_ref_des`, `hide_dnp_footprints_on_fab_layers`, `sketch_dnp_footprints_on_fab_layers`, `crossout_dnp_footprints_on_fab_layers`, `sketch_pads_on_fab_layers`, `plot_pad_numbers`, `plot_drawing_sheet`, `subtract_solder_mask_from_silk`, `use_drill_origin`, `drill_shape`, `drawing_sheet`, `check_zones`, `variant`.
- gerbers: + `include_netlist_attributes`, `use_x2_format`, `disable_aperture_macros`, `use_protel_file_extension`, `precision`, `create_gerber_job_file`.
- drill: `format` excellon|gerber, `drill_origin` abs|plot, `units` in|mm (default **in**), `zero_format` decimal|suppress_leading|suppress_trailing|keep_zeros, `excellon.mirror_y`, `excellon.minimal_header`, `excellon.combine_pth_npth` (default true), `excellon.oval_drill_route`, `generate_map`, `map_format` dxf|gerberx2|pdf|postscript|svg, `gerber_precision`, `generate_report`, `report_filename`, `generate_tenting`.
- pos: `format` ascii|csv|gerber, `units` in|mm, `side` front|back|both, `use_drill_place_file_origin` (default true), `smd_only`, `exclude_footprints_with_th`, `exclude_dnp`, `exclude_bom`, `negate_bottom_x`, `single_file`, `gerber_board_edge`, `variant`. With `single_file: true` the file is named `<output stem>-all-pos.csv` (verified `ecc83-pp_v2-pos-all-pos.csv`).
- 3d: `format`, `overwrite`, `use_grid_origin`, `use_drill_origin`, `use_defined_origin`, `use_pcb_center_origin`, `has_user_origin`, `user_origin.x/.y` (mm), `board_only`, `include_unspecified`, `include_dnp`, `subst_models`, `optimize_step`, `cut_vias_in_body`, `export_board_body`, `export_components`, `export_tracks`, `export_pads`, `export_zones`, `export_inner_copper`, `export_silkscreen`, `export_soldermask`, `fuse_shapes`, `fill_all_vias`, `extra_pad_thickness`, `net_filter`, `component_filter`, `board_outlines_chaining_epsilon`, `vrml_units|vrml_model_dir|vrml_relative_paths`, `variant`.
- svg: `scale`, `color_theme`, `fit_page_to_board`, `precision`, `gen_mode` single|multi. pdf: `scale`, `color_theme`, `pdf_metadata`, `single_document`, `front_fp_property_popups`, `back_fp_property_popups`, `pdf_gen_mode` all-layers-one-file|all-layers-separate-files|one-page-per-layer-one-file, `background_color`. dxf: `scale`, `plot_graphic_items_using_contours`, `units` in|mm, `polygon_mode`, `gen_mode`.
- ipc2581: `drawing_sheet`, `units`, `version` B|C, `precision`, `compress`, `field_bom_map.internal_id|mfg_pn|mfg|dist_pn|dist`, `bom_rev`, `variant`. odb: `drawing_sheet`, `units`, `precision`, `compression` none|zip|tgz, `variant`, `check_zones`. stats: `format` report|json, `units`, `exclude_footprints_without_pads`, `subtract_holes_from_board`, `subtract_holes_from_copper`.
- render: `format` png|jpeg, `quality` basic|high|user, `bg_style` default|opaque|transparent, `side`, `preset`, `use_board_stackup_colors`, `zoom`, `perspective`, `floor`, `anti_alias`, `post_process`, `procedural_textures`, `width`, `height`, `pivot_x/y/z`, `pan_x/y/z`, `rotation_x/y/z`, `light_*_intensity`, `light_side_elevation`, `variant`.
- sch bom: `fields_ordered`, `fields_labels`, `fields_group_by`, `sort_field`, `sort_asc`, `filter_string`, `exclude_dnp`, `group_symbols`, `bom_preset_name`, `bom_format_preset_name`, `field_delimiter`, `string_delimiter`, `ref_delimiter`, `ref_range_delimiter`, `keep_tabs`, `keep_line_breaks`, `variant_names`.
- sch netlist: `format`, `spice.save_all_voltages|currents|events|dissipations`, `variant_names`. sch plot: `format`, `drawing_sheet`, `plot_all`, `plot_drawing_sheet`, `black_and_white`, `show_hop_over`, `page_size`, `use_background_color`, `min_pen_width`, `pdf_property_popups`, `pdf_hierarchical_links`, `pdf_metadata`, `color_theme`, `variant_name`, `variant_names`.
- destinations: `folder` → `settings.output_path`; `archive` → `settings.output_path` (zip file) + `"format": "zip"`. `only: []` = all jobs, else list of job ids. `${PROJECTNAME}`, `${CURRENT_DATE}`, `${JOBSET_OUTPUT_WORK_PATH}` and env vars expand; job outputs are written to a temp work dir then copied to the destination.

Jobset gotchas (all verified):
1. A destination `output_path` that is relative resolves against the **shell's
   current working directory**, not the project (it wrote `jobset_out\` into
   `D:\projects\kicad-skills`). Always use absolute paths or `${JOBSET_OUTPUT_WORK_PATH}`-style variables.
2. `special_execute` also runs with the shell's cwd (`exec_out.txt` landed in the project root).
3. Any **unknown settings key** (e.g. `output_format` on `pcb_export_stats`) makes
   KiCad drop the *entire* job list silently: output is
   `0 jobs succeeded, 0 job failed` with **exit 0**. Always assert the expected
   job count in the log.
4. An **unknown job `type`** crashes kicad-cli (exit `-1073741819` = 0xC0000005), no message.
5. `jobset run` exit codes: 0 all jobs ok; **6** when a job failed (missing 3D models
   failed the STEP job; `pcb_drc` with `fail_on_error: true` and violations).
   `--stop-on-error` stops at the first failure.
6. `sch_erc`/`pcb_drc` default `fail_on_error: true` — set false if you only want the report.
7. Output filenames from CLI/jobset are `.json` only if you name them so; `format` decides content.

Shipped example jobsets: none under `share\kicad` (verified search).

---

## 6. Misc verified facts useful for skills

- Stock libraries: `C:\Program Files\KiCad\10.0\share\kicad\{symbols,footprints,3dmodels,template,demos,schemas}`;
  user config `%APPDATA%\kicad\10.0\{kicad_common.json,kicad.json,eeschema.json,pcbnew.json,fp-lib-table,sym-lib-table,design-block-lib-table}`.
- JSON schemas shipped: `api.v1.schema.json` (plugin manifest), `pcm.v1|v2.schema.json`,
  `kicad-remote-*.schema.json`. ERC/DRC schemas are referenced by URL
  (`https://schemas.kicad.org/erc.v1.json`, `drc.v1.json`) and not shipped.
- `kicad-cli version --format about` gives build info; `--format commit` gives the hash.
- Legacy demo boards may reference `${KICAD6_3DMODEL_DIR}` — 3D exports warn per
  footprint and STEP returns exit 2.
- ERC `pos` for the interf_u symbol was `(3.8227, 1.8288)` mm on a 20250114
  schematic — do not assume positions land on the 1.27 mm grid for legacy imports.
- The PowerShell tool sandbox blocks `Remove-Item` when the same command text
  contains `"C:\Program Files"`; keep KiCad paths in `$env:ProgramFiles` or separate
  commands.
