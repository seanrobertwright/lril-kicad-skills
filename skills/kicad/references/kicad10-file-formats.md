# KiCad 10.0.6 file formats — ground truth from the local install

Source: `C:\Program Files\KiCad\10.0` (`kicad-cli version` = `10.0.6`), inspected 2026-09-14.
Working copies and hand-built test files live in
`<scratch>\fmt\`
(`ecc83/`, `complex_hierarchy/`, `subsheets/`, `pic_programmer/`, `tiny_tapeout/`, `cm5/`, `libs/`, `gen/`).
All snippets below are copied from files KiCad 10.0.6 wrote itself (via `kicad-cli ... upgrade --force`) unless
marked "hand-written".

## 1. Version headers (the numbers that matter)

| File type | Token | Version written by 10.0.6 | generator | generator_version |
|---|---|---|---|---|
| `.kicad_sch` | `kicad_sch` | **20260306** | `"eeschema"` | `"10.0"` |
| `.kicad_pcb` | `kicad_pcb` | **20260206** | `"pcbnew"` | `"10.0"` |
| `.kicad_sym` | `kicad_symbol_lib` | **20251024** | `"kicad_symbol_editor"` | `"10.0"` |
| `.kicad_mod` | `footprint` | **20260206** | `"pcbnew"` (shipped libs say `"kicad-footprint-generator"`) | `"10.0"` (absent in shipped libs) |
| `.kicad_pro` | JSON | `meta.version` **3** | — | — |
| `sym-lib-table` / `fp-lib-table` | `(version 7)` | — | — | — |
| netlist (`sch export netlist --format kicadsexpr`) | `(export (version "E") ...)` | — | `(tool "Eeschema 10.0.6")` | — |

Exact headers as written:

```
(kicad_sch
	(version 20260306)
	(generator "eeschema")
	(generator_version "10.0")
	(uuid "28f865a0-4433-4a53-bbd7-b62f276848e4")
	(paper "A4")
```

```
(kicad_pcb
	(version 20260206)
	(generator "pcbnew")
	(generator_version "10.0")
	(general
		(thickness 1.6)
		(legacy_teardrops no)
	)
	(paper "A4")
```

```
(kicad_symbol_lib (version 20251024) (generator "kicad_symbol_editor") (generator_version "10.0") (symbol "Ammeter_AC" ...
```

```
(footprint "R_0603_1608Metric"
	(version 20260206)
	(generator "pcbnew")
	(generator_version "10.0")
	(layer "F.Cu")
```

Demo state before upgrade: almost every shipped demo is still KiCad 9 format (`sch 20250114`, `pcb 20241229`,
`generator_version "9.0"`). Exceptions: `demos/pic_programmer` is native v10 (`sch 20260101`, `pcb 20260206`,
`"10.0"`); `cm5_minima` and `stickhub` are `9.99` nightlies (`sch 20250610`/`20250901`, `pcb 20250513`/`20250907`).
Note that 10.0.6 re-saves `pic_programmer.kicad_sch` from `20260101` to `20260306`: the schematic format was bumped
once more after 10.0.0 shipped. Use **20260306** for schematics.

### kicad-cli upgrade commands

```
kicad-cli sch upgrade [--force] INPUT_FILE
kicad-cli pcb upgrade [--force] INPUT_FILE
kicad-cli sym upgrade [-o OUTPUT_FILE_OR_DIR] [--force] INPUT_FILE_OR_DIR
kicad-cli fp  upgrade [-o OUTPUT_DIR] [--force] INPUT_FILE_OR_DIR      (input is a .pretty dir)
```

`--force` = "resave regardless of versioning". `sch`/`pcb upgrade` rewrite in place (no `-o`). Success messages:
`Successfully saved schematic file using the latest format`, `Successfully saved board file using the latest format`,
`Saving symbol library in updated format`. The upgrade does not touch `.kicad_pro`.

### kicad-cli as a validation gate (tested)

- `kicad-cli sch erc [-o rpt] [--format json|report] [--severity-all] [--exit-code-violations] FILE`
- `kicad-cli pcb drc [-o rpt] [--format json|report] [--severity-all] [--schematic-parity] [--exit-code-violations] [--refill-zones --save-board] FILE`
- `kicad-cli sch export netlist --format kicadsexpr -o out.net FILE`

Exit codes observed: `0` = loaded and ran; `3` = `Failed to load schematic` / `Failed to load board: <parser message>`;
`5` = violations present with `--exit-code-violations`. An unknown top-level token (`(bogus_token 1)`) makes the loader
fail outright, so the parser is strict about unknown tokens. `pcb upgrade` on a board that fails to load prints the
error and then segfaults — do not rely on it for validation; use `pcb drc`.

## 2. `.kicad_sch` anatomy (v 20260306)

### Top-level section order as written by KiCad

`version, generator, generator_version, uuid, paper, [title_block], lib_symbols, [text...], [junction...],
[no_connect...], [bus_entry...], [wire...], [bus...], [polyline...], [label...], [global_label...],
[hierarchical_label...], [symbol...], [sheet...], [sheet_instances]`

Observed depth-1 token sequences:

- `ecc83-pp.kicad_sch` (root, flat): `version generator generator_version uuid paper title_block lib_symbols junction(8) no_connect(4) wire(37) symbol(26) sheet_instances`
- `complex_hierarchy.kicad_sch` (root with 2 sub-sheets): `... lib_symbols junction no_connect wire label symbol(27) sheet(2) sheet_instances`
- `ampli_ht.kicad_sch` (a sub-sheet): `... lib_symbols text junction wire label symbol` — **no `sheet_instances`** in sub-sheets.
- `subsheet1.kicad_sch`: `... lib_symbols junction wire hierarchical_label(2) symbol(4)`
- native v10 `pic_programmer.kicad_sch` (20260101) ended with `(sheet_instances ...) (embedded_fonts no)`; after re-save to
  20260306 the `embedded_fonts` line is **gone from the schematic root** (it remains inside each `lib_symbols` entry and in
  `.kicad_pcb`). `symbol_instances` no longer exists at all (per-symbol `instances` replaced it).

There is no `(net ...)` list in a schematic; connectivity is derived from geometry + labels.

### title_block

```
(title_block
	(title "ECC Push-Pull")
	(date "Sat 21 Mar 2015")
	(rev "0.1")
)
```
(`company`, `comment N "..."` are the other allowed children.)

### lib_symbols — every placed symbol needs a full copy of its library symbol here

Name is `"LibNickname:SymbolName"` and must equal the placed symbol's `lib_id`. Copied verbatim from an upgraded file:

```
(lib_symbols
	(symbol "ecc83-pp:R"
		(pin_numbers (hide yes))
		(pin_names (offset 0))
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(in_pos_files yes)
		(duplicate_pin_numbers_are_jumpers no)
		(property "Reference" "R"
			(at 2.032 0 90)
			(show_name no)
			(do_not_autoplace no)
			(effects (font (size 1.27 1.27)))
		)
		(property "Value" "R" (at 0 0 90) (show_name no) (do_not_autoplace no) (effects (font (size 1.27 1.27))))
		(property "Footprint" "" (at -1.778 0 90) (show_name no) (do_not_autoplace no) (effects (font (size 0.762 0.762))))
		(property "Datasheet" "" (at 0 0 0) (show_name no) (do_not_autoplace no) (effects (font (size 0.762 0.762))))
		(property "Description" "" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "ki_fp_filters" "R_* Resistor_*" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(symbol "R_0_1"
			(rectangle
				(start -1.016 -2.54)
				(end 1.016 2.54)
				(stroke (width 0.254) (type default))
				(fill (type none))
			)
		)
		(symbol "R_1_1"
			(pin passive line
				(at 0 3.81 270)
				(length 1.27)
				(name "" (effects (font (size 1.524 1.524))))
				(number "1" (effects (font (size 1.524 1.524))))
			)
			(pin passive line
				(at 0 -3.81 90)
				(length 1.27)
				(name "" (effects (font (size 1.524 1.524))))
				(number "2" (effects (font (size 1.524 1.524))))
			)
		)
		(embedded_fonts no)
	)
```

Sub-unit naming: `"<Name>_<unit>_<bodystyle>"`; `_0_1` = graphics common to all units, `_1_1` = unit 1 body style 1.
Pin electrical types seen: `passive`, `power_in`, `input`, `output`, etc.; graphic style `line`. Pin `(at x y rot)` is the
pin's **connection point** in library coordinates (mm, **Y up**), `rot` is the direction the pin body points from that
point *toward* the symbol body (270 = pin points down from the top, 90 = up from the bottom, 0 = points right, 180 = left).

Power symbol (hidden `power_in` pin of length 0, `(power global)` — v10 token replaces the old `(power)`):

```
	(symbol "ecc83-pp:GND"
		(power global)
		(pin_names (offset 0))
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(in_pos_files yes)
		(duplicate_pin_numbers_are_jumpers no)
		(property "Reference" "#PWR" (at 0 -6.35 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Value" "GND" (at 0 -3.81 0) (show_name no) (do_not_autoplace no) (effects (font (size 1.27 1.27))))
		...
		(symbol "GND_0_1"
			(polyline
				(pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27))
				(stroke (width 0) (type default))
				(fill (type none))
			)
		)
		(symbol "GND_1_1"
			(pin power_in line
				(at 0 0 270)
				(length 0)
				(hide yes)
				(name "GND" (effects (font (size 1.27 1.27))))
				(number "1" (effects (font (size 1.27 1.27))))
			)
		)
		(embedded_fonts no)
	)
```

### Placed symbol instance

```
(symbol
	(lib_id "ecc83-pp:R")
	(at 157.48 85.09 180)
	(unit 1)
	(body_style 1)
	(exclude_from_sim no)
	(in_bom yes)
	(on_board yes)
	(in_pos_files yes)
	(dnp no)
	(uuid "00000000-0000-0000-0000-00004549f38a")
	(property "Reference" "R1"
		(at 154.94 85.09 0)
		(show_name no)
		(do_not_autoplace no)
		(effects (font (size 1.27 1.27)))
	)
	(property "Value" "1.5K"
		(at 157.48 85.09 90)
		(show_name no)
		(do_not_autoplace no)
		(effects (font (size 1.27 1.27)))
	)
	(property "Footprint" "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"
		(at 159.512 85.0392 90)
		(show_name no)
		(do_not_autoplace no)
		(effects (font (size 0.254 0.254)))
	)
	(property "Datasheet" ""
		(at 157.48 85.09 0)
		(hide yes)
		(show_name no)
		(do_not_autoplace no)
		(effects (font (size 1.524 1.524)))
	)
	(property "Description" ""
		(at 157.48 85.09 0)
		(hide yes)
		(show_name no)
		(do_not_autoplace no)
		(effects (font (size 1.27 1.27)))
	)
	(pin "1" (uuid "490a35ba-1ba2-44c5-adce-e27a045257ab"))
	(pin "2" (uuid "51355c82-d1cf-445b-b079-21c660dd8989"))
	(instances
		(project "ecc83-pp"
			(path "/28f865a0-4433-4a53-bbd7-b62f276848e4" (reference "R1") (unit 1))
		)
	)
)
```

Facts:
- Property `(at x y rot)` is in **absolute sheet coordinates**, not relative to the symbol.
- Property order KiCad writes: Reference, Value, Footprint, Datasheet, Description, then user fields.
- `(pin "N" (uuid ...))` one per library pin; the uuid must be unique.
- `instances / project "<project name>" / path "/<root sheet uuid>[/<sheet uuid>...]"`: the path is the root schematic's
  `uuid` for a root-sheet symbol, extended by each `(sheet ...)` uuid for nested sheets. `project` is the
  `.kicad_pro` basename; when no project file exists KiCad rewrites it as `(project "" ...)`.
- Optional tokens: `(mirror x)` / `(mirror y)` after `at`; `(fields_autoplaced yes)`.
- Power symbols: reference `#PWRnn`, Reference property hidden.

**Tested optional tokens (hand-written file `gen/gen.kicad_sch`)**: a schematic that omits `body_style`, `in_pos_files`,
`show_name`, `do_not_autoplace`, `duplicate_pin_numbers_are_jumpers`, `embedded_fonts`, `sheet_instances`, and even the
whole `instances` block still loads, passes ERC and exports a correct netlist (refs come from the Reference property).
KiCad adds the missing tokens on re-save. The `lib_symbol_mismatch` ERC *warning* fires if the `lib_symbols` copy
differs from the library on disk (e.g. trimmed `ki_keywords`) — copy the library entry verbatim to avoid it.

### junction, no_connect, wire, bus, bus_entry, polyline, text

```
(junction
	(at 76.2 50.8)
	(diameter 1.016)
	(color 0 0 0 0)
	(uuid "10ef5c17-5272-4e7f-89a5-ecf737e33e26")
)
(no_connect (at 154.94 177.8) (uuid "07e6e92c-c8a8-42b9-a8a3-099796ec9615"))
(wire
	(pts (xy 185.42 76.2) (xy 198.12 76.2))
	(stroke (width 0) (type solid))
	(uuid "06655b90-3a73-4865-8781-04208e869f47")
)
(bus
	(pts (xy 22.86 58.42) (xy 22.86 60.96))
	(stroke (width 0) (type default))
	(uuid "3e84d1d0-2471-403f-8490-c70d755192ca")
)
(bus_entry
	(at 22.86 45.72)
	(size 2.54 2.54)
	(stroke (width 0) (type default))
	(uuid "24f7115a-8983-4547-a6e1-98a76fb6e3e1")
)
(polyline
	(pts (xy 172.72 196.85) (xy 148.59 196.85))
	(stroke (width 0) (type dash))
	(uuid "088f800b-89af-4049-b7bd-bc3ee6bc7fd7")
)
(text "Filter:\nFc =1000Hz"
	(exclude_from_sim no)
	(at 66.04 74.93 0)
	(effects
		(font (size 2.032 2.032) (thickness 0.4064) (bold yes) (italic yes))
		(justify left bottom)
	)
	(uuid "4fee597b-5b3d-4d5f-9246-cb5aaa802827")
)
```
`(diameter 0)` on a junction = default size. Stroke `(width 0)` = default width; `(type default)` or `solid`.

### label / global_label / hierarchical_label

```
(label "12Vext"
	(at 54.61 63.5 0)
	(effects (font (size 1.524 1.524)) (justify left bottom))
	(uuid "6d5fce79-cffa-4bf2-a989-42ca9ce0dd4e")
)
(global_label "out6"
	(shape input)
	(at 226.695 151.13 180)
	(fields_autoplaced yes)
	(effects (font (size 1.27 1.27)) (justify right))
	(uuid "0062fe1f-cf41-406e-b703-2262a1b26c41")
	(property "Intersheetrefs" "${INTERSHEET_REFS}"
		(at 219.4766 151.13 0)
		(hide yes)
		(show_name no)
		(do_not_autoplace no)
		(effects (font (size 1.27 1.27)) (justify right))
	)
)
(hierarchical_label "in"
	(shape input)
	(at 148.59 87.63 180)
	(effects (font (size 1.27 1.27)) (justify right))
	(uuid "804c72e7-40fe-4feb-96db-807d74dd32e5")
)
```
Shapes: `input`, `output`, `bidirectional`, `tri_state`, `passive`. The `Intersheetrefs` property on a global_label is
optional on input (KiCad adds it on save). Label rotation 0/90/180/270; justify follows the rotation
(0 -> `left bottom`, 180 -> `right`, etc.).

### sheet (hierarchical sheet) and sheet_instances

```
(sheet
	(at 157.48 95.25)
	(size 13.97 13.97)
	(exclude_from_sim no)
	(in_bom yes)
	(on_board yes)
	(dnp no)
	(fields_autoplaced yes)
	(stroke (width 0.1524) (type solid))
	(fill (color 0 0 0 0))
	(uuid "51ab3a6c-36b1-4056-a2d2-39c83ee99c02")
	(property "Sheetname" "subsheet1"
		(at 157.48 94.5384 0)
		(show_name no)
		(do_not_autoplace no)
		(effects (font (size 1.27 1.27)) (justify left bottom))
	)
	(property "Sheetfile" "subsheet1.kicad_sch"
		(at 157.48 109.8046 0)
		(show_name no)
		(do_not_autoplace no)
		(effects (font (size 1.27 1.27)) (justify left top))
	)
	(pin "in" input
		(at 157.48 101.6 180)
		(uuid "7d34bd80-1948-4689-9586-e63e4b177b8e")
		(effects (font (size 1.27 1.27)) (justify left))
	)
	(pin "out" output
		(at 171.45 101.6 0)
		(uuid "e983f7d1-388b-4bf0-ab6f-23264e0b4fbe")
		(effects (font (size 1.27 1.27)) (justify right))
	)
	(instances (project "mainsheet" (path "/e63e39d7-6ac0-4ffd-8aa3-1841a4541b55" (page "2"))))
)
```
- Sheet pins sit on the sheet border; each must match a `hierarchical_label` of the same name inside the child file.
- Root file: `(sheet_instances (path "/" (page "1")))`. Sub-sheet files have no `sheet_instances`.
- The `sheet ... instances ... path` is the *parent* path (root uuid for a first-level sheet). Symbols inside the child
  use `path "/<root uuid>/<sheet uuid>"`.

### Coordinate system, grid, pin placement (verified numerically)

- Units: mm. Sheet origin top-left, **Y down**. Default grid 50 mil = **1.27 mm**; every wire end, pin and label in the
  demos sits on a 1.27 multiple (e.g. 157.48 = 124 x 1.27). Library symbols are drawn on 2.54 mm / 1.27 mm grids around
  origin (0,0) with **Y up**.
- Placed-symbol pin position: for a library pin at `(px, py)` and a symbol at `(ox, oy, rot)`:
  `x' = px, y' = -py` (flip Y), then if `(mirror y)`: `x' = -x'`; if `(mirror x)`: `y' = -y'`; then rotate by `rot`:
  `X = x'*cos(rot) + y'*sin(rot)`, `Y = -x'*sin(rot) + y'*cos(rot)`; sheet position = `(ox + X, oy + Y)`.
  Checked against 16 pins of 8 symbols (rot 0/180/270, mirror y) in `ecc83-pp.kicad_sch`: every computed pin position
  coincides with a wire endpoint. Example: `R` pin 1 lib `(0, 3.81)` with symbol `(at 157.48 85.09 180)` ->
  sheet `(157.48, 88.9)`; with rot 0 -> `(157.48, 81.28)`. `C` at rot 270: pin 1 `(0,3.81)` -> `(ox+3.81, oy)`.
- Pin `length` is drawn from the connection point toward the body; wires must end exactly at the connection point.

## 3. `.kicad_pcb` anatomy (v 20260206)

### Top-level order as written

`version generator generator_version general paper [title_block] layers setup [property...] footprint... gr_line/gr_rect/gr_arc/gr_poly/gr_circle/gr_text/dimension... segment... via... zone... [group...] embedded_fonts`

Observed: `ecc83-pp.kicad_pcb`: `version generator generator_version general paper layers setup footprint(15) gr_line(4) segment(59) zone(1) embedded_fonts`.
`pic_programmer.kicad_pcb`: `... title_block layers setup footprint(63) gr_line(5) gr_text(19) segment via ... zone embedded_fonts`.

**There is no top-level `(net N "name")` table in v10 boards.** Pads, segments, vias and zones reference nets by
name: `(net "GND")`. The v9 file had `(net 0 "") (net 1 "GND") ...` and pads used `(net 1 "GND")`; the upgrade deleted
the table. Tested: a `version 20260206` board containing `(net 1 "GND")` + `(net 1)` fails to load with
`Failed to load board: Expecting net name. Got ')'`. Net names are strings; unconnected pads use
`(net "unconnected-(P5-Pad1)")`; hierarchical nets look like `(net "/CLOCK-RB6")`.

### general / paper / title_block

```
(general (thickness 1.6) (legacy_teardrops no))
(paper "A4")
(title_block (title "SERIAL PIC PROGRAMMER"))
```

### layers — standard 2-layer list exactly as written (order matters: it is the order KiCad writes)

```
(layers
	(0 "F.Cu" signal)
	(2 "B.Cu" signal)
	(9 "F.Adhes" user "F.Adhesive")
	(11 "B.Adhes" user "B.Adhesive")
	(13 "F.Paste" user)
	(15 "B.Paste" user)
	(5 "F.SilkS" user "F.Silkscreen")
	(7 "B.SilkS" user "B.Silkscreen")
	(1 "F.Mask" user)
	(3 "B.Mask" user)
	(17 "Dwgs.User" user "User.Drawings")
	(19 "Cmts.User" user "User.Comments")
	(21 "Eco1.User" user "User.Eco1")
	(23 "Eco2.User" user "User.Eco2")
	(25 "Edge.Cuts" user)
	(27 "Margin" user)
	(31 "F.CrtYd" user "F.Courtyard")
	(29 "B.CrtYd" user "B.Courtyard")
	(35 "F.Fab" user)
	(33 "B.Fab" user)
)
```
The ecc83 upgrade also wrote `(0 "F.Cu" signal "top_cu")` / `(2 "B.Cu" signal "bottom_cu")` (user layer names from the
v9 file); the optional 4th atom is a user-facing alias. Inner copper layers: `(4 "In1.Cu" signal) (6 "In2.Cu" signal)`
placed between F.Cu and B.Cu. Extra user layers: `(39 "User.1" user) (41 "User.2" user) ... (55 "User.9" user)`.
A minimal `(layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))` board loads.

### setup

```
(setup
	(stackup
		(layer "F.SilkS" (type "Top Silk Screen") (color "White"))
		(layer "F.Paste" (type "Top Solder Paste"))
		(layer "F.Mask" (type "Top Solder Mask") (color "Green") (thickness 0.01))
		(layer "F.Cu" (type "copper") (thickness 0.035))
		(layer "dielectric 1"
			(type "core")
			(thickness 1.51)
			(material "FR4")
			(epsilon_r 4.5)
			(loss_tangent 0.02)
		)
		(layer "B.Cu" (type "copper") (thickness 0.035))
		(layer "B.Mask" (type "Bottom Solder Mask") (color "Green") (thickness 0.01))
		(layer "B.Paste" (type "Bottom Solder Paste"))
		(layer "B.SilkS" (type "Bottom Silk Screen") (color "White"))
		(copper_finish "None")
		(dielectric_constraints no)
	)
	(pad_to_mask_clearance 0)
	(allow_soldermask_bridges_in_footprints no)
	(tenting (front yes) (back yes))
	(covering (front no) (back no))
	(plugging (front no) (back no))
	(capping no)
	(filling no)
	[(aux_axis_origin x y)]  [(grid_origin x y)]
	(pcbplotparams
		(layerselection 0x00000000_00000000_00000000_000000af)
		(plot_on_all_layers_selection 0x00000000_00000000_00000000_00000000)
		(disableapertmacros no)
		(usegerberextensions no)
		(usegerberattributes yes)
		(usegerberadvancedattributes yes)
		(creategerberjobfile yes)
		(dashed_line_dash_ratio 12)
		(dashed_line_gap_ratio 3)
		(svgprecision 6)
		(plotframeref no)
		(mode 1)
		(useauxorigin no)
		(pdf_front_fp_property_popups yes)
		(pdf_back_fp_property_popups yes)
		(pdf_metadata yes)
		(pdf_single_document no)
		(dxfpolygonmode yes)
		(dxfimperialunits yes)
		(dxfusepcbnewfont yes)
		(psnegative no)
		(psa4output no)
		(plot_black_and_white yes)
		(sketchpadsonfab no)
		(plotpadnumbers no)
		(hidednponfab no)
		(sketchdnponfab yes)
		(crossoutdnponfab yes)
		(subtractmaskfromsilk no)
		(outputformat 1)
		(mirror no)
		(drillshape 0)
		(scaleselection 1)
		(outputdirectory "")
	)
)
```
`stackup` is optional (a board with only `(setup (pad_to_mask_clearance 0))` loads). v10 changed the via-protection
tokens: v9 `(tenting front back)` became `(tenting (front yes) (back yes))` plus new `covering`, `plugging`, `capping`,
`filling`. Removed from `pcbplotparams`: `hpglpennumber`, `hpglpenspeed`, `hpglpendiameter`, `plotinvisibletext`.

### footprint block (as written in a board)

```
(footprint "Capacitor_SMD:C_0603_1608Metric"
	(layer "F.Cu")
	(uuid "01085533-bb36-4c92-a765-6fd26d7dde65")
	(at 150.5 60 180)
	(descr "Capacitor SMD 0603 (1608 Metric) ...")
	(tags "capacitor")
	(property "Reference" "C21"
		(at 0 -1.16 0)
		(layer "F.SilkS")
		(uuid "54c04a27-50e2-4b11-8eb3-7ed485223b49")
		(effects (font (size 0.8 0.8) (thickness 0.15)))
	)
	(property "Value" "10uF"
		(at 0 1.43 0)
		(layer "F.Fab")
		(uuid "a1cef8c7-1126-43e7-b32f-3ab66560aef3")
		(effects (font (size 1 1) (thickness 0.15)))
	)
	(property "Datasheet" ""
		(at 0 0 180)
		(unlocked yes)
		(layer "F.Fab")
		(hide yes)
		(uuid "ca2a23e5-24f9-4e05-876f-6ca5aa5e29f5")
		(effects (font (size 1.27 1.27) (thickness 0.15)))
	)
	(property "Description" "" ... same shape ...)
	(property "MPN" "CL10A106MP8NNNC" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "...") (effects (font (size 1 1) (thickness 0.15))))
	(path "/c659cf7b-bd21-45d2-8bb3-672831c9088a")
	(sheetname "Root")
	(sheetfile "tinytapeout-demo.kicad_sch")
	(attr smd)
	(duplicate_pad_numbers_are_jumpers no)
	(fp_line
		(start -0.14058 0.51)
		(end 0.14058 0.51)
		(stroke (width 0.12) (type solid))
		(layer "F.SilkS")
		(uuid "f580708f-a9d3-41db-80b2-a819c52a9493")
	)
	(fp_rect (start -1.48 -0.73) (end 1.48 0.73) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "..."))
	(fp_text user "${REFERENCE}"
		(at 0 0 0)
		(layer "F.Fab")
		(uuid "2c91f4e3-1e5d-46a2-a634-97df67eccd28")
		(effects (font (size 0.4 0.4) (thickness 0.06)))
	)
	(pad "1" smd roundrect
		(at -0.775 0 180)
		(size 0.9 0.95)
		(layers "F.Cu" "F.Mask" "F.Paste")
		(roundrect_rratio 0.25)
		(net "GND")
		(pintype "passive")
		(uuid "fd4e0dad-cc31-4ace-be6c-f9d32d3e0003")
	)
	(pad "2" smd roundrect (at 0.775 0 180) (size 0.9 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.25) (net "+1V8") (pintype "passive") (uuid "..."))
	(embedded_fonts no)
	(model "${KICAD10_3DMODEL_DIR}/Capacitor_SMD.3dshapes/C_0603_1608Metric.step"
		(offset (xyz 0 0 0))
		(scale (xyz 1 1 1))
		(rotate (xyz 0 0 0))
	)
)
```

Facts:
- Footprint `(at x y [rot])` is board-absolute; everything inside (`property at`, `fp_*`, `pad at`) is **relative to the
  footprint origin and unrotated** — KiCad rotates them at load. Note pads carry the footprint rotation in their own `at`
  (`(at -0.775 0 180)` for a footprint at rot 180): this is how KiCad writes it, and it is required for the pad to land
  where the library says.
- Reference/Value/Datasheet/Description are `property` blocks (v8+); `fp_text` is only used for `user` text such as
  `${REFERENCE}` on F.Fab. `fp_text reference/value` is gone.
- `path` = `"/<root sch uuid>/<symbol uuid>"` (root-sheet symbol) — links the footprint to the schematic symbol.
  `sheetname`/`sheetfile` are informational.
- `attr` atoms: `smd`, `through_hole`, `exclude_from_pos_files`, `exclude_from_bom`, `allow_soldermask_bridges`,
  `board_only`, `dnp`. Combinations seen: `(attr through_hole exclude_from_pos_files exclude_from_bom)`,
  `(attr exclude_from_bom allow_soldermask_bridges)`.
- Through-hole pad: `(pad "1" thru_hole circle (at 0 0) (size 5.6 5.6) (drill 3.2) (layers "*.Cu" "*.Mask") (remove_unused_layers no) (net "...") (pinfunction "1") (pintype "passive+no_connect") (uuid "..."))`.
  Pad shapes: `circle`, `rect`, `oval`, `roundrect` (+`roundrect_rratio`), `trapezoid`, `custom` (+`options`, `primitives`).
  Other pad children seen: `thermal_bridge_angle`, `zone_connect`, `teardrops (...)`.
- Footprint children union across demos: `at attr clearance descr duplicate_pad_numbers_are_jumpers embedded_fonts fp_arc fp_circle fp_line fp_poly fp_rect fp_text layer model pad path point property sheetfile sheetname tags units uuid zone_connect`.
- New v10 footprint tokens: `(duplicate_pad_numbers_are_jumpers no)`; `(units (unit (name "A") (pins "1" "2")))`
  (symbol-unit to pad mapping written for multi-unit parts); `(point (at x y) (size 1.27) (layer "F.Fab") (uuid ...))`
  (a marker/reference-point primitive); `(embedded_fonts no)` inside every footprint (written **before** `model`).
- 3D model path variable in v10 libraries is `${KICAD10_3DMODEL_DIR}` (older demos still carry `${KICAD6_3DMODEL_DIR}`,
  which still resolves). Corresponding library vars: `${KICAD10_SYMBOL_DIR}`, `${KICAD10_FOOTPRINT_DIR}`, and
  `${KIPRJMOD}` for project-relative paths.

### Board graphics (Edge.Cuts etc.)

```
(gr_line
	(start 121.285 90.17)
	(end 121.285 136.525)
	(stroke (width 0.127) (type solid))
	(layer "Edge.Cuts")
	(uuid "00000000-0000-0000-0000-00005d88943e")
)
(gr_rect
	(start 62.205 65.8)
	(end 63.505 68.2)
	(stroke (width 0.15) (type solid))
	(fill yes)
	(layer "B.SilkS")
	(uuid "3aae2f0d-8f7e-48e6-afa0-051dfc2c4aae")
)
(gr_arc
	(start 86.35 73.49)
	(mid 87.764214 74.075786)
	(end 88.35 75.49)
	(stroke (width 0.15) (type default))
	(layer "F.SilkS")
	(uuid "d172c430-ae33-4cb6-89c7-78936801ec04")
)
(gr_poly
	(pts (xy ...) (xy ...) ...)
	(stroke (width 0.15) (type solid))
	(fill yes)
	(layer "F.SilkS")
	(uuid "5883b106-f157-4aef-a5ae-d610fd70f8ad")
)
(gr_text "+8/12V"
	(at 81.5 55.5 0)
	(layer "F.Cu")
	(uuid "14a6c3ac-e639-40b6-838b-1677460b7b74")
	(effects (font (size 2.032 1.524) (thickness 0.3048)))
)
```
Fill is `(fill yes|no)` in v10 (a `gr_rect` on Edge.Cuts with `(fill no)` and `(stroke (width 0.1) (type solid))` was
accepted as the board outline in the hand-written test). DRC error `[invalid_outline]: Board has malformed outline (no
edges found on Edge.Cuts layer)` if the outline is missing.

### segment / via / zone / group / dimension

```
(segment
	(start 139.573 99.695)
	(end 141.605 99.695)
	(width 0.8)
	(layer "B.Cu")
	(net "Net-(P3-P1)")
	(uuid "1d6285fd-2d49-4956-932f-458079ff628a")
)
(via
	(at 189.865 110.49)
	(size 1.6)
	(drill 0.6)
	(layers "F.Cu" "B.Cu")
	(capping no)
	(covering (front no) (back no))
	(plugging (front no) (back no))
	(filling no)
	(net "/CLOCK-RB6")
	(uuid "00c62925-76e5-4da4-9776-805e7e214afd")
)
(zone
	(net "GND")
	(layer "B.Cu")
	(uuid "00000000-0000-0000-0000-00004eed97a2")
	(hatch edge 0.508)
	(connect_pads (clearance 0.635))
	(min_thickness 0.381)
	(fill yes (thermal_gap 0.254) (thermal_bridge_width 0.50038) (island_removal_mode 0))
	(polygon
		(pts (xy 172.085 91.313) (xy 172.085 135.89) ... )
	)
	(filled_polygon
		(layer "B.Cu")
		(pts (xy 166.963652 91.344896) (xy 167.029723 91.397309) ... )
	)
)
(group ""
	(uuid "330a6ee8-4f82-4a7a-937e-cfd0b87e65b9")
	(members "64fedca5-dae2-485f-b7db-1e559cf35c17" "ce597d91-a78f-48c7-aec6-ddca1db1e698")
)
(dimension
	(type aligned)
	(layer "User.2")
	(uuid "12e7f53c-3ecc-4d32-b518-0ba4f0397502")
	(pts (xy 161 56.5) (xy 56.5 56.5))
	(height 10.65)
	(format (prefix "") (suffix "") (units 3) (units_format 1) (precision 4))
	(style (thickness 0.15) (arrow_length 1.27) (text_position_mode 0) (arrow_direction outward) (extension_height 0.58642) (extension_offset 0.5) (keep_text_aligned yes))
	(gr_text "104.5000 mm" (at 108.75 44.7 0) (layer "User.2") (uuid "...") (effects (font (size 1 1) (thickness 0.15))))
)
```
- Via `capping/covering/plugging/filling` are optional (a via without them loaded); `(locked yes)` optional on
  segment/via.
- Zone: `filled_polygon` is optional on input (`pcb drc --refill-zones --save-board` regenerates it); other zone
  children seen: `name`, `priority`, `layers` (multi-layer zone), `keepout`. `filled_areas_thickness` was **removed** in
  v10 output but is still accepted on input. `island_removal_mode` is new in v10 output.
- Per-pad teardrop block (written when teardrops are enabled):
  `(teardrops (best_length_ratio 0.5) (max_length 1) (best_width_ratio 1) (max_width 2) (curved_edges no) (filter_ratio 0.9) (enabled yes) (allow_two_segments yes) (prefer_zone_connections yes))`.
- Tokens searched for and **not** present in any v10 demo board: `jumper(s)`, `tuning`, `generated`, `target`,
  `table`, `net_tie`, `rule_area`, `padstack`, `component_class`. (Tuning profiles and component classes live in the
  `.kicad_pro` JSON instead — see below.)
- Board ends with `(embedded_fonts no)` as the last top-level token.

### v9 -> v10 token diff (ecc83 and tiny_tapeout, board)

Added: `back capping covering duplicate_pad_numbers_are_jumpers filling front island_removal_mode plugging`.
Removed: `filled_areas_thickness hpglpendiameter hpglpennumber hpglpenspeed net_name plotinvisibletext` (and the
numeric net table).

### v9 -> v10 token diff (schematic)

Added: `body_style do_not_autoplace duplicate_pin_numbers_are_jumpers in_pos_files show_name`. Removed: none.

## 4. Library files

### `.kicad_sym` (`share/kicad/symbols/Device.kicad_sym`, 536 symbols)

```
(kicad_symbol_lib
	(version 20251024)
	(generator "kicad_symbol_editor")
	(generator_version "10.0")
	(symbol "R"
		(pin_numbers (hide yes))
		(pin_names (offset 0))
		(exclude_from_sim no)
		(in_bom yes)
		(on_board yes)
		(in_pos_files yes)
		(duplicate_pin_numbers_are_jumpers no)
		(property "Reference" "R" (at 2.032 0 90) (show_name no) (do_not_autoplace no) (effects (font (size 1.27 1.27))))
		(property "Value" "R" (at 0 0 90) (show_name no) (do_not_autoplace no) (effects (font (size 1.27 1.27))))
		(property "Footprint" "" (at -1.778 0 90) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Datasheet" "" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "Description" "Resistor" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "ki_keywords" "R res resistor" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(property "ki_fp_filters" "R_*" (at 0 0 0) (show_name no) (do_not_autoplace no) (hide yes) (effects (font (size 1.27 1.27))))
		(symbol "R_0_1"
			(rectangle (start -1.016 -2.54) (end 1.016 2.54) (stroke (width 0.254) (type default)) (fill (type none)))
		)
		(symbol "R_1_1"
			(pin passive line (at 0 3.81 270) (length 1.27) (name "" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))
			(pin passive line (at 0 -3.81 90) (length 1.27) (name "" (effects (font (size 1.27 1.27)))) (number "2" (effects (font (size 1.27 1.27)))))
		)
		(embedded_fonts no)
	)
	...
)
```
`C`: `(pin_names (offset 0.254))`, body = two `polyline`s at y = +/-0.762 with `(stroke (width 0.508) ...)`, pins at
`(0 3.81 270)` / `(0 -3.81 90)` with `(length 2.794)`, `ki_fp_filters "C_*"`. `R_Small`: pins at `(0 2.54 270)` /
`(0 -2.54 90)`, `(length 0.762)`, rectangle `-0.762..0.762 x -1.778..1.778`.

Derived symbols: `(symbol "Filter_EMI_C" (extends "C_Feedthrough") (property ...)... (embedded_fonts no))` — only
properties, no graphics/pins.

Inside a schematic's `lib_symbols` the same block appears with the name prefixed by the lib nickname
(`"Device:R"`) and `ki_keywords`/`ki_fp_filters` may be dropped (KiCad keeps `ki_fp_filters`). Placing `Device:R`
requires the library entry to be *copied*, not referenced.

`kicad-cli sym upgrade --force` on a v9 `.kicad_sym` (20241209) produced 20251024 / "10.0".

### `.kicad_mod` (`share/kicad/footprints/Resistor_SMD.pretty/R_0603_1608Metric.kicad_mod`, complete file)

```
(footprint "R_0603_1608Metric"
	(version 20260206)
	(generator "kicad-footprint-generator")
	(layer "F.Cu")
	(descr "Resistor SMD 0603 (1608 Metric), square (rectangular) end terminal, IPC-7351 nominal, ...")
	(tags "resistor")
	(property "Reference" "REF**"
		(at 0 -1.43 0)
		(layer "F.SilkS")
		(effects (font (size 1 1) (thickness 0.15)))
	)
	(property "Value" "R_0603_1608Metric"
		(at 0 1.43 0)
		(layer "F.Fab")
		(effects (font (size 1 1) (thickness 0.15)))
	)
	(property "KiLib_Generator" "SMD_2terminal_chip_molded"
		(at 0 0 0)
		(layer "F.SilkS")
		(hide yes)
		(effects (font (size 1 1) (thickness 0.15)))
	)
	(attr smd)
	(duplicate_pad_numbers_are_jumpers no)
	(fp_line (start -0.237258 -0.5225) (end 0.237258 -0.5225) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
	(fp_line (start -0.237258 0.5225) (end 0.237258 0.5225) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))
	(fp_rect (start -1.48 -0.73) (end 1.48 0.73) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))
	(fp_rect (start -0.8 -0.4125) (end 0.8 0.4125) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab"))
	(fp_text user "${REFERENCE}"
		(at 0 0 0)
		(layer "F.Fab")
		(effects (font (size 0.4 0.4) (thickness 0.06)))
	)
	(pad "1" smd roundrect (at -0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.25))
	(pad "2" smd roundrect (at 0.825 0) (size 0.8 0.95) (layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.25))
	(embedded_fonts no)
	(model "${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.step"
		(offset (xyz 0 0 0))
		(scale (xyz 1 1 1))
		(rotate (xyz 0 0 0))
	)
)
```
Library footprints carry no `uuid`s, no `Datasheet`/`Description` properties, no `path`, no nets. After
`kicad-cli fp upgrade --force`, KiCad wrote `(generator "pcbnew") (generator_version "10.0")`, added a `uuid` to every
graphic/pad/property, and added empty hidden `Datasheet` and `Description` properties — i.e. those are all optional on
input. Courtyard on `F.CrtYd` (width 0.05), fab outline on `F.Fab` (0.1), silk (0.12) are the KLC conventions used.

## 5. `.kicad_pro` and library tables

### `.kicad_pro` (JSON, `meta.version: 3`)

Top-level keys of the native v10 `pic_programmer.kicad_pro`:
`board, boards, component_class_settings, cvpcb, erc, legacy, libraries, meta, net_settings, pcbnew, schematic, sheets, text_variables, tuning_profiles`
(ecc83 lacks `component_class_settings` and `tuning_profiles` — both are optional).

- `board`: `3dviewports, design_settings, ipc2581, layer_pairs, layer_presets, viewports`
- `board.design_settings`: `defaults, diff_pair_dimensions, drc_exclusions, meta, rule_severities, rules, teardrop_options, teardrop_parameters, track_widths, tuning_pattern_settings, via_dimensions, zones_allow_external_fillets, zones_use_no_outline`
- `schematic`: `annotate_start_num, annotation, bom_export_filename, bom_fmt_presets, bom_fmt_settings, bom_presets, bom_settings, bus_aliases, connection_grid_size, drawing, legacy_lib_dir, legacy_lib_list, meta, net_format_name, ngspice, page_layout_descr_file, plot_directory, reuse_designators, space_save_all_events, spice_* (7 keys), subpart_first_id, subpart_id_separator, top_level_sheets, used_designators, variants`
- `net_settings`: `classes, meta, net_colors, netclass_assignments, netclass_patterns`; a class object:
  `{"bus_width":12,"clearance":0.25,"diff_pair_gap":0.25,"diff_pair_via_gap":0.25,"diff_pair_width":0.25,"line_style":0,"microvia_diameter":0.508,"microvia_drill":0.127,"name":"Default","pcb_color":"rgba(0, 0, 0, 0.000)","priority":2147483647,"schematic_color":"rgba(0, 0, 0, 0.000)","track_width":0.5,"tuning_profile":"","via_diameter":1.6,"via_drill":0.6,"wire_width":6}`
  (`tuning_profile` is new in v10.)
- `sheets`: `[["<root sch uuid>", "Root"], ["<sheet uuid>", "pic_sockets"]]` — root uuid must equal the root
  `.kicad_sch` `uuid`.
- `libraries`: `{"pinned_footprint_libs": [], "pinned_symbol_libs": []}`; `text_variables`: `{}`; `cvpcb`: `{"equivalence_files": []}`;
  `pcbnew`: `{"last_paths": {...}, "page_layout_descr_file": ""}`; `erc`: `erc_exclusions, meta, pin_map, rule_severities`.

The shipped **minimal default project** `share/kicad/template/kicad.kicad_pro` (what KiCad creates for a new project;
`meta.version` 1 is accepted and upgraded on save) is the safest thing for a generator to emit:

```json
{
  "board": {
    "design_settings": {
      "defaults": {},
      "diff_pair_dimensions": [],
      "drc_exclusions": [],
      "rules": {},
      "track_widths": [],
      "via_dimensions": []
    }
  },
  "boards": [],
  "libraries": {
    "pinned_footprint_libs": [],
    "pinned_symbol_libs": []
  },
  "meta": {
    "filename": "kicad.kicad_pro",
    "version": 1
  },
  "net_settings": {
    "classes": [],
    "meta": {
      "version": 0
    }
  },
  "pcbnew": {
    "page_layout_descr_file": ""
  },
  "sheets": [],
  "text_variables": {}
}
```
`meta.filename` must match the actual file name.

### sym-lib-table / fp-lib-table

Global tables exist at `%APPDATA%\kicad\10.0\sym-lib-table` and `...\fp-lib-table` (plus
`design-block-lib-table`, `kicad_common.json`, `eeschema.json`, `pcbnew.json`, etc.). v10 global tables are one-line
**delegations** to the shipped tables:

```
(sym_lib_table
	(version 7)
	(lib (name "KiCad") (type "Table") (uri "C:/Program Files/KiCad/10.0/share/kicad/template/sym-lib-table") (options "") (descr "KiCad Default Libraries"))
)
(fp_lib_table
	(version 7)
	(lib (name "KiCad") (type "Table") (uri "C:/Program Files/KiCad/10.0/share/kicad/template/fp-lib-table") (options "") (descr "KiCad Default Libraries"))
)
```
The shipped tables (`share/kicad/template/{sym,fp}-lib-table`) list every stock library:
`(lib (name "4xxx") (type "KiCad") (uri "${KICAD10_SYMBOL_DIR}/4xxx.kicad_sym") (options "") (descr "4xxx series symbols"))`,
`(lib (name "Audio_Module") (type "KiCad") (uri "${KICAD10_FOOTPRINT_DIR}/Audio_Module.pretty") (options "") (descr "..."))`.
So nicknames `Device`, `power`, `Resistor_SMD`, `Capacitor_SMD`, ... resolve globally.

Project-local tables (next to the `.kicad_pro`):
```
(fp_lib_table
  (version 7)
  (lib (name "Footprints")(type "KiCad")(uri "${KIPRJMOD}/footprints.pretty")(options "")(descr ""))
)
(sym_lib_table
  (version 7)
  (lib (name "ecc83-pp")(type "KiCad")(uri "${KIPRJMOD}/ecc83-pp.kicad_sym")(options "")(descr ""))
)
```

## 6. schemas, scripting, template

`share/kicad/schemas` (5 JSON Schemas, none describe the design file formats):
- `api.v1.schema.json` — "KiCad IPC API Plugin and Action schema" (`plugin.json` for IPC plugins).
- `pcm.v1.schema.json`, `pcm.v2.schema.json` — Plugin and Content Manager repository/package metadata.
- `kicad-remote-provider-metadata-v1.schema.json` — remote library provider metadata (`provider_name, api_base_url, auth, capabilities, parts, ...`).
- `kicad-remote-symbol-manifest-v1.schema.json` — remote symbol manifest (`part_id, display_name, summary, license, assets`).

`share/kicad/scripting`: `kicad_pyshell/` (pyshell editor) and `plugins/` footprint wizards
(`FootprintWizardBase.py`, `PadArray.py`, `bga_wizard.py`, `qfn_wizard.py`, `qfp_wizard.py`, `sdip_wizard.py`,
`FPC_wizard.py`, `circular_pad_array_wizard.py`, `qrcode_footprint_wizard.py`, `uss39_barcode.py`, `zip_wizard.py`,
`touch_slider_wizard.py`, `mutualcap_button_wizard.py`, `microMatch_connectors.py`, `scrollwheel_wizard.py`, `arc_test.py`).
No file-format documentation here.

`share/kicad/template`: `kicad.kicad_pro` (default project), `sym-lib-table`, `fp-lib-table`, page-layout files
(`pagelayout_default.kicad_wks`, `pagelayout_logo.kicad_wks`, `gost_*.kicad_wks`, ISO5457/ISO7200 A2/A3/A4 variants),
and project templates (`Arduino_Uno/`, `Arduino_Nano/`, `RaspberryPi-HAT/`, `RaspberryPi-uHAT/`, `EuroCard160mmX100mm/`,
`STM32_Nucleo-64_Morpho/`, `TI-LaunchPad-BoosterPack-*`, `BeagleBone-Black-Cape/`, `Hammond_1593K_Enclosure/`, ...).

## 7. Hand-written minimal files that KiCad 10.0.6 accepted

`fmt/gen/gen.kicad_sch` (two `Device:R` + `power:GND`, wires, junction, label, global_label): `sch erc` runs (1 error:
`power_pin_not_driven` — expected without a PWR_FLAG; warnings: `isolated_pin_label`, `lib_symbol_mismatch` from my
trimmed lib copy), `sch export netlist --format kicadsexpr` produces nets `GND`, `IN`, `OUT` with refs R1/R2.

`fmt/gen/gen.kicad_pcb` (one `Resistor_SMD:R_0603_1608Metric` with `(net "IN")`/`(net "GND")` pads, `gr_rect` outline on
Edge.Cuts, one `segment`, one `via` without capping/covering tokens, one `zone` without `filled_polygon`): `pcb drc`
loads, reports only `via_dangling` (expected).

Minimum viable root schematic (loads, ERC clean):
```
(kicad_sch (version 20260306) (generator "eeschema") (generator_version "10.0")
  (uuid "11111111-1111-1111-1111-111111111111") (paper "A4") (lib_symbols)
  (sheet_instances (path "/" (page "1"))))
```
Minimum viable board (loads; DRC only complains about the missing outline):
```
(kicad_pcb (version 20260206) (generator "pcbnew") (generator_version "10.0")
  (general (thickness 1.6) (legacy_teardrops no)) (paper "A4")
  (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
  (setup (pad_to_mask_clearance 0)) (embedded_fonts no))
```

## 8. Generator checklist distilled from the above

1. Headers: sch `20260306`, pcb/mod `20260206`, sym `20251024`; `generator_version "10.0"`.
2. Every `uuid` is a lowercase RFC-4122 string, unique per element (wires, junctions, labels, symbols, pins, sheets,
   footprints and every footprint child in a board, segments, vias, zones).
3. Schematic: mm, Y down, 1.27 mm grid; copy library symbols verbatim into `lib_symbols` under `"Nick:Name"`; a placed
   symbol carries all five standard properties (absolute coordinates), `(pin "n" (uuid))` per pin, and
   `(instances (project "<pro basename>" (path "/<root uuid>" (reference "R1") (unit 1))))`; root file ends with
   `(sheet_instances (path "/" (page "1")))`; sub-sheet files omit it; hierarchical sheet pins must match
   `hierarchical_label`s in the child.
4. Board: **nets by name only** — no `(net N "name")` table, never `(net 1)`; footprints use `property` for
   Reference/Value/Datasheet/Description and `fp_text user` only; pads embed the footprint rotation in their `at`;
   `path "/<root uuid>/<symbol uuid>"` links to the schematic; end with `(embedded_fonts no)`; put an outline on
   `Edge.Cuts`.
5. Project: emit the template `kicad.kicad_pro` with `meta.filename` set and `sheets` = `[[root uuid, "Root"]]`; add
   project `sym-lib-table`/`fp-lib-table` (`version 7`, `${KIPRJMOD}` URIs) only for project-local libraries.
6. Validate with `kicad-cli sch erc --exit-code-violations`, `kicad-cli sch export netlist`, and
   `kicad-cli pcb drc --exit-code-violations` (exit 3 = parse failure).
