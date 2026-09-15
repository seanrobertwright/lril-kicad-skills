---
name: kicad-export
description: Produce manufacturing and documentation outputs from a KiCad 10 project: gerbers, drill files, pick-and-place/position files, BOM (JLCPCB/PCBWay/OSH Park/generic presets), STEP 3D, PDF plots, board renders, netlists, statistics and reusable kicad-cli jobsets. Use when the user wants to order boards, upload to a fab, get gerbers, a BOM, a CPL/position file, a 3D model, or print the schematic. Refuses to export a board with DRC errors unless the user overrides.
---

# KiCad export

`KCS = python <skills>/kicad/scripts/kcs.py`

## Gate

Before any fab output: `KCS erc <sch>` and `KCS drc <pcb> --parity` must
report zero errors and zero unconnected items. If not, stop and say what is
wrong; export only after the user explicitly says to override, and record
the override in DESIGN.md.

## Fab package

```
KCS fab <pcb> <sch> <out-dir> --fab jlcpcb|pcbway|oshpark|generic
```

Writes `gerbers/` (layers per preset, Protel extensions, drill + map,
job file), a zip ready to upload, `<name>-pos.csv` (JLCPCB columns
`Designator, Mid X, Mid Y, Layer, Rotation` when the preset is jlcpcb), and
`<name>-bom.csv` with the preset's columns (JLCPCB: `Designator, Comment,
Footprint, LCSC Part #, Qty`). Tell the user which files to upload where,
and the preset's notes (JLCPCB rotation offsets for some packages; check
their assembly preview).

Requirements for a correct position file: components have the schematic
`in_pos_files yes` (default), DNP parts are excluded, the aux origin is set
(the builder puts it at the board's bottom-left).

## Other outputs

| need | command |
|---|---|
| 3D model for enclosure | `KCS step <pcb> <out.step>` (exit 2 = some 3D models missing, file still written) |
| schematic PDF | `KCS pdf <sch>` |
| board PDF (layers) | `KCS pdf <pcb>` |
| renders | `KCS render <pcb>` |
| netlist for another tool | `kicad-cli sch export netlist --format kicadsexpr\|kicadxml\|spice\|cadstar\|orcadpcb2\|pads\|allegro` |
| board statistics | `kicad-cli pcb export stats --format json` |
| IPC-2581 / ODB++ | `kicad-cli pcb export ipc2581` / `odb` |
| IPC-D-356 test netlist | `kicad-cli pcb export ipcd356` |

Full flag reference: `../kicad/references/kicad-cli-help.txt`.

## Jobsets (repeatable exports)

KiCad 10 jobsets (`<name>.kicad_jobset`, JSON) run several jobs in one
command: `kicad-cli jobset run --file <name>.kicad_jobset <project.kicad_pro>`.
The format and every verified job type/setting are in
`../kicad/references/kicad10-cli-and-apis.md` (section "Jobsets"). Create
one per fab so the user can re-export after edits with a single command.
Gotchas: relative output paths resolve against the shell's working
directory; an unknown settings key silently disables all jobs.

## Release checklist

1. DESIGN.md revision bumped, date set; silkscreen rev matches.
2. ERC/DRC clean (or overrides logged).
3. BOM reviewed: every line has MPN, quantities match, DNP excluded.
4. Gerber review: open the gerber zip in KiCad's GerbView or the fab's
   viewer; check Edge.Cuts closed, drills present, mask openings, silk.
5. Position file: rotation sanity for polarized parts (diodes, ICs).
6. Archive: zip the project folder + outputs as `<name>-rev<X>-<date>.zip`.
