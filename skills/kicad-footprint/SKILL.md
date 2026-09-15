---
name: kicad-footprint
description: Create KiCad 10 footprints (.kicad_mod) for packages missing from the stock library, from datasheet package drawings, using IPC-7351B land-pattern rules and KLC conventions. Use when a footprint is missing, the user says "make a footprint", "land pattern", "pad layout", gives package dimensions, or a part's package is non-standard (custom connector, module, odd QFN). Also attaches 3D models. Generates with kcs fpgen (chip, gullwing, QFN/DFN, DIP, headers, custom pads), validates against DRC, renders and inspects.
---

# KiCad footprint creation

`KCS = python <skills>/kicad/scripts/kcs.py`

## Steps

1. **Search first.** `KCS fp search <package>` - the stock library has ~14k
   footprints named by package (`Package_SO:SOIC-8_3.9x4.9mm_P1.27mm`,
   `Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm`, `Resistor_SMD:R_0603_1608Metric`).
   Match the *package dimensions* from the datasheet, not just the name;
   `KCS fp info` lists pad positions to compare with the drawing.
   `_HandSolder` variants exist for hand assembly.
2. **Read the package drawing** (datasheet "Package Information" pages).
   Record: body L x W x H, lead span (tip-to-tip) X and Y, lead width and
   length with tolerances, pitch, pin count, pin-1 location, exposed pad
   size, and the page number. Ask the user to confirm the numbers you
   transcribed; a wrong lead span is the most common footprint error.
3. **Generate** with `KCS fpgen pkg.json <project>/<Lib>.pretty`:

```json
{"kind": "gullwing", "name": "TSSOP-16_4.4x5mm_P0.65mm",
 "pins": 16, "pitch": 0.65, "body_w": 4.4, "body_h": 5.0,
 "lead_span_x": 6.4, "lead_w": 0.25, "lead_l": 0.6, "density": "N",
 "description": "TSSOP-16, 4.4x5 mm body, 0.65 mm pitch (JEDEC MO-153)",
 "tags": "tssop", "model": "${KIPRJMOD}/parts.3dshapes/TSSOP-16.step"}
```

   Kinds and their fields:
   - `chip`: `body_l, body_w, term_l, height, polarized` (0402..2512, LEDs, diodes)
   - `gullwing`: as above; `sides: 4` for QFP (`lead_span_y` if not square);
     asymmetric rows with `left_pins`/`right_pins` lists (SOT-23-3: `["1","2"]` / `["3"]`)
   - `no_lead`: `pins, pitch, body, body_h, lead_w, lead_l, ep: [w, h], sides: 2|4, paste_split`
   - `dip`: `pins, pitch, row_spacing, drill, pad_d` (pin 1 at origin, KiCad style)
   - `header`: `pins_per_row, rows, pitch, drill, pad_d`
   - anything else: build a `FootprintSpec` with explicit `PadSpec`s in Python
     (`kcslib.fp`), e.g. connectors with slots, castellated modules.
   Density `L`/`N`/`M` selects the IPC-7351B toe/heel/side fillets. The
   generator adds F.Fab outline with pin-1 chamfer, silkscreen clear of
   pads with a pin-1 dot, courtyard at the density offset, `${REFERENCE}`
   on F.Fab, and paste windows on exposed pads.
4. **Verify**: `KCS klc <file.kicad_mod>`; compare pads with the datasheet
   recommended land pattern if it gives one (many do - prefer the
   manufacturer's pattern when it exists, entered as a `custom` spec); drop
   the footprint on a scratch board and run `KCS drc` (clearance between
   pads must pass the fab's rule);
   `KCS fpview MyParts:<Name> --project <project-dir> --out fp.png` and look
   at the PNG with Read (project footprint libraries need `--project`).
5. **3D model**: download the STEP from the manufacturer (or a generic from
   the stock `3dmodels` folder), save under `<project>/parts.3dshapes/`, and
   reference it as `${KIPRJMOD}/parts.3dshapes/<name>.step`. Check alignment
   with `KCS render` or `KCS step`.
6. **Register** the `.pretty` directory in `design.json` -> `libs.footprints`
   and record the footprint in DESIGN.md with its source page.

## Conventions applied (KLC F-rules)

Silkscreen 0.12 mm, fab 0.10 mm, courtyard 0.05 mm on a 0.01 mm grid;
courtyard offset 0.25 mm (nominal), 0.5 mm for connectors/crystals;
silk never over pads (0.2 mm clearance); THT pad 1 rectangular; SMD origin
at the body centre, THT origin at pin 1; names follow the stock pattern
`<Family>-<pins>_<body>x<body>mm_P<pitch>mm[_EP<w>x<h>mm]`.

## Importing instead of generating

Vendor footprints (SnapEDA/UL/SamacSys/LCSC via easyeda2kicad) are often in
older formats: run `KCS upgrade <file.kicad_mod>` and then the same
verification. Never trust a downloaded pad layout without comparing to the
datasheet drawing; mirror-image connectors are a classic failure.

Reference: `../kicad/references/part-sources-and-klc.md`,
`../kicad/scripts/kcslib/fp.py`.
