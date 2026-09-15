---
name: kicad-symbol
description: Create KiCad 10 schematic symbols (.kicad_sym) for parts missing from the stock library, from a datasheet pin table or a manufacturer page. Use when a symbol is missing, the user says "make a symbol for", "I need the symbol for this chip", pastes a pinout, or a design spec references a part not in the KiCad libraries. Transcribes the pinout into a pin table the user confirms, generates a KLC-style symbol with kcs symgen, registers it in the project sym-lib-table, and verifies it loads and renders.
---

# KiCad symbol creation

A symbol is only as good as its pin table. The table comes from the
datasheet (or the manufacturer's page), is shown to the user for
confirmation, and is then generated deterministically.

`KCS = python <skills>/kicad/scripts/kcs.py`

## Steps

1. **Search first.** `KCS sym search <name>` across the 223 stock libraries
   and the project library. Many "missing" parts exist under a family name
   (e.g. `MCU_ST_STM32F1:STM32F103C8Tx`). Check the description and pin count.
2. **Get the pinout from the source.** Download the datasheet PDF (curl with
   a browser user agent, or the file the user gives you). Record: document
   title, revision/date, page. Never type a pinout from memory.
3. **Draft the pin table from the PDF**:

   ```
   KCS pins-from-pdf datasheet.pdf --name TPS7A0233 --package DBV --out pins.json
   ```

   It finds pin tables (multi-row headers, several package columns such as
   TI's `DQN | DBV | YCH`; pick one with `--package`), maps number/name/type/
   description, guesses the KiCad electrical type and side, and writes a
   `symgen` pin table with a confidence per pin plus warnings (missing pin
   numbers, low-confidence types, package columns seen). Needs
   `pip install pdfplumber` (falls back to pypdf text parsing). If nothing is
   recognised, pass `--pages` with the pin-description pages, or transcribe
   by hand from the page image (Read the PDF).
4. **Review with the user.** Print the draft as a markdown table next to the
   datasheet page number: number, name, type, side, confidence. Fix every
   low-confidence row and every type that disagrees with the datasheet
   *meaning* (the extractor guesses `passive` when unsure; a regulator's
   "Input"/"Output" supply pins are `power_in`/`power_out` in KiCad even
   though the datasheet column says Input/Output). Fill `footprint`,
   `datasheet`, `description`, `keywords`, `fp_filters`. Remove `_extraction`
   and the `confidence`/`source`/`description` keys once confirmed. Electrical types:
   `input`, `output`, `bidirectional`, `tri_state`, `passive`, `power_in`,
   `power_out`, `open_collector`, `open_emitter`, `no_connect`, `unspecified`.
5. **Generate**: `KCS symgen pins.json <project>/<Lib>.kicad_sym` (merges
   into an existing library, replaces a symbol with the same name).
6. **Register** the library in the project: add it to `design.json` ->
   `libs.symbols` as `{"name": "MyParts", "uri": "${KIPRJMOD}/MyParts.kicad_sym"}`
   (the builder writes the table), or directly:

   ```python
   from kcslib import project
   project.write_lib_table(project_dir, "sym", [("MyParts", "${KIPRJMOD}/MyParts.kicad_sym", "project parts")])
   ```

   (`"sym"` for symbol libraries, `"fp"` for footprint libraries.)
7. **Verify**: `KCS klc <lib>` (grid, duplicates, datasheet/description),
   `KCS sym info MyParts:<Name> --project <project-dir>` (project libraries
   are only visible with `--project`), then
   `KCS symview MyParts:<Name> --project <project-dir> --out sym.pdf` and
   look at the PDF with Read (the Read tool cannot display SVG). Check pin
   order, sides, overbars, and that no text overlaps a pin.
8. Record the symbol in DESIGN.md's parts table with its source. If there is
   no project yet, keep the library next to the pin table and say where it is.

## pins.json format

```json
{
  "name": "TPS7A0233", "reference": "U", "value": "TPS7A0233",
  "footprint": "Package_TO_SOT_SMD:SOT-23-5",
  "datasheet": "https://www.ti.com/lit/ds/symlink/tps7a02.pdf",
  "description": "200 mA ultra-low-IQ LDO, 3.3 V fixed, SOT-23-5",
  "keywords": "ldo regulator", "fp_filters": "SOT?23*",
  "units": 1, "power": false,
  "pins": [
    {"number": "1", "name": "IN",  "type": "power_in",  "side": "left"},
    {"number": "2", "name": "GND", "type": "power_in",  "side": "bottom"},
    {"number": "3", "name": "EN",  "type": "input",     "side": "left", "gap_before": 1},
    {"number": "4", "name": "NC",  "type": "no_connect","side": "right"},
    {"number": "5", "name": "OUT", "type": "power_out", "side": "right"}
  ]
}
```

A list of such objects generates several symbols into one library. Options
per pin: `shape` (`line`, `inverted`, `clock`, ...), `unit` (for multi-unit
parts), `hidden`, `gap_before` (blank slots for grouping),
`alternates` (`[{"name": "UART1_TX", "type": "output"}]`). Overbars: `~{RESET}`.

## Layout conventions the generator applies (KLC)

- Inputs left, outputs right, power top, ground bottom; group by function
  with gaps; pins in datasheet order within a group.
- Pin length 2.54 mm, pin pitch 2.54 mm, pin ends on the 2.54 mm grid
  (S4.1), body outline 0.254 mm with background fill (S3.x), name offset
  0.508 mm, reference top-left and value bottom-left outside the body.
- Unused/NC pins typed `no_connect` and hidden. Multiple pins with the same
  function (e.g. four VDD): all visible, or stacked per S4.3 only if the
  user asks; the schematic builder handles multiple VDD pins with a bus bar.
- Power symbols: set `"power": true`; a single hidden `power_in` pin.

For the full rule list read `../kicad/references/part-sources-and-klc.md`.

## Importing instead of generating

If the manufacturer, SnapEDA, Ultra Librarian, SamacSys or LCSC (via
`easyeda2kicad`) provides a `.kicad_sym`, see **kicad-parts**; then still run
`KCS klc` and `KCS sym info`, compare the pin table with the datasheet, and
run `KCS upgrade <file>` to normalise it to the 10.0 format.
