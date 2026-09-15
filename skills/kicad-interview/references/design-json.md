# design.json - the machine-checkable design spec

`kcs build` consumes this file. Keep it next to DESIGN.md in `design/`.
Validate with `python <kicad-skill>/scripts/kcs.py spec validate design/design.json`.

```json
{
  "project": "blinky",                       // file base name (no spaces)
  "title": "Blinky", "rev": "A", "company": "", "paper": "A4",
  "libs": {                                  // project-local libraries (optional)
    "symbols":    [{"name": "MyParts", "uri": "${KIPRJMOD}/MyParts.kicad_sym"}],
    "footprints": [{"name": "MyParts", "uri": "${KIPRJMOD}/MyParts.pretty"}]
  },
  "power_nets":  ["+3V3", "GND", "VBUS"],    // drawn as power symbols; PWR_FLAG added when undriven
  "global_nets": ["SWDIO", "SWCLK"],         // drawn as global labels
  "groups": [                                // schematic blocks, in drawing order
    {"name": "power", "title": "USB input and 3.3 V regulator"},
    {"name": "mcu",   "title": "MCU"}
  ],
  "sheets": [                                // optional hierarchy: one file per sheet, groups assigned to sheets
    {"name": "Power", "file": "power.kicad_sch", "groups": ["power"]},
    {"name": "MCU",   "file": "mcu.kicad_sch",   "groups": ["mcu"]}
  ],                                         // groups not listed stay on the root sheet; nets crossing sheets get
                                             // hierarchical labels + sheet pins automatically (power nets are global)
  "components": [
    {"ref": "U1", "symbol": "Regulator_Linear:AMS1117-3.3", "value": "AMS1117-3.3",
     "footprint": "Package_TO_SOT_SMD:SOT-223-3_TabPin2", "group": "power",
     "props": {"MPN": "AMS1117-3.3", "Manufacturer": "AMS", "LCSC": "C6186"},
     "datasheet": "https://...", "dnp": false,
     "rot": 0, "mirror": null, "at": null, "unit": 1}   // at = [x, y] mm to pin a symbol manually
  ],
  "nets": {                                  // net name -> [[ref, pin], ...]; pin = symbol pin NUMBER
    "GND":  [["U1", "1"], ["C1", "2"]],
    "VBUS": [["U1", "3"], ["C1", "1"]]
  },
  "no_connect": [["U2", "A6"]],              // pins deliberately left open (drawn with an X)
  "unused_pins_nc": ["U2"],                  // "every remaining pin of U2 is open" - only after the user confirmed
  "wires": [[["R1", "2"], ["D1", "1"]]],     // optional direct wires instead of labels
  "board": {
    "fab": "jlcpcb",                          // jlcpcb | pcbway | oshpark | generic: sets DRC rules in the .kicad_pro
    "width": 50, "height": 40, "layers": 2, "thickness": 1.6, "corner_radius": 2,
    "origin": [50, 50],                       // board top-left in page coordinates
    "outline_polygon": null,                  // [[x,y],...] relative to origin, overrides the rectangle
    "zones": [{"net": "GND", "layer": "B.Cu"}],
    "mounting_holes": {"inset": 3.5, "count": 4, "footprint": "MountingHole:MountingHole_3.2mm_M3"},
    "placement": {"J1": [5, 20, 90, "F.Cu"]},  // ref -> [x, y, rot, layer] relative to origin; others auto-packed
    "hints": {                                 // softer than placement; from the interview's mechanical questions
      "J1": {"edge": "left", "rot": 90},       // edge: left|right|top|bottom (spread evenly along that edge)
      "U2": {"center": true},                  // board centre
      "C3": {"near": "U2"},                    // first free spot around the target (decoupling, crystals)
      "J2": {"edge": "right", "rot": 90, "layer": "F.Cu"}
    },
    "placement_gap": 1.0, "edge_clearance": 1.5,
    "texts": [{"text": "BLINKY rev A", "at": [25, 38], "layer": "F.SilkS", "size": 1.0}],
    "design_settings": {}                     // merged into the .kicad_pro board design settings
  }
}
```

Rules the validator enforces:

- every component has ref, symbol, value, footprint; references unique
- every symbol and footprint exists in the stock or project libraries
- every `[ref, pin]` names a real pin number of that symbol/unit
- a pin is on at most one net; a pin on a net is not also no-connect
- no single-pin nets (except power nets)
- every visible pin of every symbol is on a net, in `no_connect`, or the
  component is in `unused_pins_nc`
- every group is assigned to at most one sheet; every `hints` reference exists

Use `sheets` above roughly 40 components or whenever the interview produced
more than three function blocks; one sheet per block keeps each page readable.

Net naming: power nets in the `power:` library style (`+3V3`, `+5V`, `GND`,
`VBUS`, `VIN`). Signal nets in UPPER_SNAKE (`SWDIO`, `I2C_SCL`, `LED_K`).
Active-low with a `~{NAME}` overbar or `nNAME` consistently.
