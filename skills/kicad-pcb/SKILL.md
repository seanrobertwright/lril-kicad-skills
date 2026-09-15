---
name: kicad-pcb
description: Create and check KiCad 10 boards (.kicad_pcb): stackup, outline, mounting, footprint placement, routing, zones, DRC. Use when the user wants a PCB laid out, parts placed, traces routed, an autorouter run, DRC fixed, a board resized, layers changed, or a ground pour added. Builds the board from design/design.json via the kcs tool, cross-checks it against the schematic (schematic parity), runs DRC, renders top/bottom images and inspects them, and offers Freerouting for a first-pass route.
---

# KiCad PCB

Prerequisite: a verified schematic (**kicad-schematic**) and the board
section of `design/design.json` filled in during the interview (size,
layers, fab limits, mounting, placement constraints).

`KCS = python <skills>/kicad/scripts/kcs.py`

## Build loop

1. `KCS build design/design.json <project-dir>` (re)creates the board:
   outline (rect with radius or polygon), stackup for 2/4/6 layers, mounting
   holes, every footprint with pad nets and the schematic path (so KiCad's
   "Update PCB from Schematic" recognises them), zones, silk texts.
   Explicit `placement` entries are honoured, then `hints` (`edge`,
   `center`, `near`, `rot`, `layer` from the interview's mechanical
   answers), then the rest are shelf-packed by group inside the outline
   with a gap. Nothing is routed. Every footprint carries its sheet path, so
   "Update PCB from Schematic" in KiCad matches hierarchical designs too.
2. Read the DRC summary and the two PNG renders (`kcs-out/*-top.png`,
   `*-bottom.png`) with the Read tool. Check: parts inside the outline,
   connectors on the edge they belong to, decoupling caps next to their IC,
   crystal close to the MCU, nothing under connectors, mounting holes clear.
3. Placement pass: start with `board.hints` (cheap, keeps working when the
   board size changes), then pin the parts that matter with
   `board.placement` (`ref: [x, y, rot, layer]`, mm from the board's
   top-left). Rebuild, look again. Iterate until the render is sensible.
4. Routing:
   - **Manual by the user in KiCad** (recommended for anything with power,
     RF, USB, or fine pitch): hand over with a list of critical nets and
     widths from DESIGN.md.
   - **Freerouting first pass**: `KCS autoroute <pcb>` (needs Java; downloads
     the jar once). Then `KCS drc <routed.pcb> --parity`, render, inspect,
     and tell the user it is a starting point.
   - **Scripted tracks** for simple boards: `kcslib.pcb.Board.track/via/route`
     with pad positions from `PlacedFootprint.pad_pos`.
5. `KCS fill <pcb>` fills zones (bundled pcbnew) so DRC sees the pours.
6. `KCS drc <pcb> --parity` must show zero errors and zero unconnected
   items before **kicad-review** and **kicad-export**.

## DRC triage

| type | usual cause / fix |
|---|---|
| `courtyards_overlap` | parts too close: move, or accept for connectors that intentionally overlap |
| `copper_edge_clearance` | pads within 0.5 mm of Edge.Cuts: move inward or shrink the fab's edge rule |
| `silk_over_copper`, `silk_overlap` | reference text over pads: move text or hide refs on dense boards |
| `pth_inside_courtyard` / `hole_to_hole` | mounting hole too close: change `inset` |
| `unconnected_items` | not routed yet |
| `lib_footprint_mismatch` | project footprint edited: intended? |
| `schematic_parity` | board and schematic diverged: rebuild or update from schematic in KiCad |

Severity of each check is in the project file (`board.design_settings.rule_severities`).

## Design rules from the fab

Set the numbers agreed in the interview (min track/space, via drill/size,
edge clearance, mask expansion) into `board.design_settings` of the spec so
they land in the `.kicad_pro` and DRC checks against them. Common defaults:

| fab (standard) | track/space | drill / via | notes |
|---|---|---|---|
| JLCPCB 2-layer | 0.127 / 0.127 mm | 0.3 / 0.6 mm | 0.2 mm edge clearance |
| PCBWay | 0.15 / 0.15 mm | 0.3 / 0.6 mm | |
| OSH Park | 0.152 / 0.152 mm | 0.254 / 0.508 mm | 2 oz copper |

Track width for current (1 oz outer, 10 C rise): 0.25 mm ~ 0.7 A, 0.5 mm
~ 1.3 A, 1 mm ~ 2.3 A, 2 mm ~ 4 A. Use two or more vias for power crossings.

## Layout rules the reviewer will check

- Decoupling cap within 2 mm of its pin, ground via next to it.
- Crystal: short symmetric traces, ground guard, no signals under it.
- USB D+/D-: 90 ohm diff pair, no stubs, ESD at the connector, length-matched.
- Switching regulator: input cap, inductor, diode/switch loop as small as
  possible; feedback trace away from the switch node.
- Ground pour on B.Cu (2-layer) or dedicated GND plane (4-layer); stitch.
- Connectors on the edge with the plug direction outward; keep-outs honoured.
- Silkscreen: pin 1, polarity, connector names, board name and revision.
- Mounting holes clear of copper unless intentionally grounded.

## 3D and mechanical

`KCS step <pcb> <out.step>` exports the assembly for enclosure checks (exit
code 2 only means some models are missing).

Reference: `../kicad/references/kicad10-file-formats.md` (board anatomy),
`../kicad/scripts/kcslib/pcb.py` (writer API).
