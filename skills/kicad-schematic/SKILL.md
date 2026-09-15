---
name: kicad-schematic
description: Create, edit and verify KiCad 10 schematics (.kicad_sch) from a design spec. Use when the user wants a schematic drawn, wired, cleaned up, checked with ERC, or turned into a netlist, or asks to add/remove/rewire parts in an existing schematic. Generates the file from design/design.json with the kcs tool, proves connectivity by comparing KiCad's exported netlist with the spec, runs ERC, renders a PDF and inspects it, then iterates on readability. Never draws before the kicad-interview design contract exists.
---

# KiCad schematic

Prerequisite: an approved design spec (from **kicad-interview**; normally
`design/design.json`, but any path works) with every part resolved to a real
symbol and footprint (**kicad-parts**). The spec keys (`components`, `nets`,
`groups`, `sheets`, `wires`, `at`/`rot` overrides, `board`) are documented in
`../kicad-interview/references/design-json.md`; read it before editing a
spec. The kicad core skill's `kcs` tool does the writing; you do the
judgement.

`KCS = python <skills>/kicad/scripts/kcs.py`

## Build loop

1. `KCS spec validate design/design.json` - must print `ok: true`.
2. `KCS build design/design.json <project-dir>` - writes `<name>.kicad_sch`,
   `<name>.kicad_pro`, (and the board unless `--no-board`), then prints:
   - `netlist matches spec: True/False` with every mismatch listed
   - ERC violation counts by type
   - a DRC line for the board: at this stage "N unrouted" and silkscreen
     warnings are expected (routing is **kicad-pcb**'s job), DRC *errors* are not
   - paths of the schematic PDF and board renders in `<project-dir>/kcs-out/`
3. If the netlist does not match: the spec and the drawing disagree. Fix the
   cause (usually a pin number vs pin name mix-up, or a label typo), never
   the symptom.
4. ERC must be zero errors. Warnings are reviewed one by one and either fixed
   or justified in DESIGN.md. Typical fixes:
   - `power_pin_not_driven`: the builder adds PWR_FLAG automatically for
     undriven power nets; if it still appears, the net is not in `power_nets`.
   - `pin_not_connected`: a pin is missing from `nets`/`no_connect` - decide it.
   - `isolated_pin_label`: a label used once - typo or missing connection.
   - `lib_symbol_mismatch`: the project symbol changed; rebuild.
5. Open the PDF with the Read tool and check it like a reviewer would (see
   "Readability" below). Improve by editing the spec (groups, `at`, `rot`,
   `wires`), rebuild, look again. Two or three passes are normal.
6. Sanity-check the *engineering*, not only the connectivity: for every
   bus, confirm with `KCS sym info` that the chosen pins really carry that
   peripheral (hardware I2C/SPI/UART pins, not any GPIO), that LED/diode
   pin 1 (K) and 2 (A) are the right way round, and that datasheet-required
   support parts (regulator output capacitor value, reset capacitor, crystal
   load caps) are present. A matching netlist proves the drawing equals the
   spec, not that the spec is right.
7. Tell the user what was built, what was verified, and what remains manual.
   If there is no DESIGN.md yet, say so and record the ERC/netlist status in
   the reply instead.

## How the builder draws

- Components are grouped into titled, dashed blocks in the order given by
  `groups`. Big parts (more than 4 pins) go in a row; passives in a grid
  below, or to the right if the block would overflow; the paper size bumps
  A4 -> A3 -> A2 automatically.
- Power nets become power symbols. Adjacent same-net supply pins on one side
  of an IC share a bus bar and one symbol (the STM32 VDD pattern).
- Every other net becomes a local label at a 2.54 mm stub (global label for
  `global_nets`). Explicit `wires` draw Manhattan wires instead.
- `no_connect` pins get the X marker; `unused_pins_nc` does it for every
  remaining pin of that part.
- Symbols embed `lib_symbols` copies, per-pin uuids and the `instances` block
  so KiCad opens the file without a library lookup and the board can be
  updated from the schematic later.
- With `sheets` in the spec, each listed sheet becomes its own
  `.kicad_sch`; the root holds one sheet symbol per sheet with pins for
  every net that crosses sheets, joined on the root by short wires and
  labels. Crossing nets get hierarchical labels on the sub-sheets; power
  nets stay power symbols and `global_nets` stay global labels. The
  netlist check still compares the whole hierarchy against the spec.

Coordinates: mm, Y down, everything on the 1.27 mm grid (the writer refuses
off-grid positions). Rotations are counter-clockwise; pin positions come
from the verified transform in `kcslib/geom.py`.

## Readability rules (what to look for in the PDF)

- Signal flow left to right, power at the top, ground at the bottom.
- ICs with power pins up and ground pins down; passives near the pin they
  serve (use `at`/`rot` to move decoupling caps next to their IC when the
  auto layout scatters them, or `wires` to draw them directly).
- No overlapping text; reference above/right, value below/right.
- Labels read left-to-right; net names consistent with DESIGN.md.
- Each block titled; one function per block; connectors at the page edges.
- Use `sheets` above roughly 40 components or three function blocks; one
  sheet per block. Check every sub-sheet page of the PDF, not only page 1.

## Editing an existing schematic

Parse it (`kcslib.sexpr.load`), modify, `dump` back; keep a `.bak`. For
anything beyond property edits prefer rebuilding from the spec, or ask the
user to do the manual edit in the GUI and then re-verify with
`KCS erc` and `KCS netlist`. Never regex-edit a `.kicad_sch`.

## Hand-off

When ERC is clean and the netlist matches: update DESIGN.md (schematic
status, ERC summary, date), then continue with **kicad-pcb**.

Reference: `../kicad/references/kicad10-file-formats.md` (schematic anatomy),
`../kicad/scripts/kcslib/sch.py` (writer API for custom drawing).
