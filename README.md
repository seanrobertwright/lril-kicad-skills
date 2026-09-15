# kicad-skills

Agent skills for designing real hardware with **KiCad 10** (tested on
10.0.6, Windows). The AI interviews you until nothing is assumed, writes the
design down, generates schematics, boards, symbols and footprints from that
written spec, and proves every file with KiCad's own tools (ERC, DRC,
netlist export, renders) before showing it to you.

## Skills

| skill | what it does |
|---|---|
| `kicad` | Core: environment facts, verified KiCad 10 file-format truths, the `kcs` command line and Python library that write and check `.kicad_sch`, `.kicad_pcb`, `.kicad_sym`, `.kicad_mod`, `.kicad_pro` |
| `kicad-interview` | The grill. Twelve phases of questions, one at a time, with recommendations; produces `design/DESIGN.md` and `design/design.json` |
| `kicad-parts` | Resolve every part to symbol + footprint + MPN; LCSC/JLCPCB price, stock and basic/extended lookup (`kcs jlc`); libraries from manufacturer pages, LCSC (easyeda2kicad), SnapEDA, Ultra Librarian, SamacSys |
| `kicad-symbol` | Draft the pin table straight from the datasheet PDF (`kcs pins-from-pdf`), confirm it, generate a KLC-style symbol |
| `kicad-footprint` | Generate IPC-7351B footprints (chip, gullwing, QFN/DFN, DIP, headers, custom) from package drawings |
| `kicad-schematic` | Build the schematic (flat or hierarchical sheets) from the spec, verify netlist == spec, ERC, PDF review loop |
| `kicad-pcb` | Build the board: stackup, outline, holes, placement from interview hints, zones, DRC loop, Freerouting first pass |
| `kicad-review` | Independent checklist review with a findings report |
| `kicad-export` | Gerbers/drill/pos/BOM with JLCPCB, PCBWay, OSH Park presets; STEP, PDF, jobsets |

## Install

```
npx skills add seanrobertwright/lril-kicad-skills   # skills.sh style, all skills
# or clone and copy skills/* into .claude/skills/ (Claude Code) - keep them
# together, the others call ../kicad/scripts/kcs.py
```

Repository: https://github.com/seanrobertwright/lril-kicad-skills

Requirements: KiCad 10 installed (`kicad-cli` is found automatically on
Windows/macOS/Linux, or set `KICAD_ROOT`), Python 3.10+. Optional: Java for
Freerouting, `pip install easyeda2kicad` for LCSC parts.

## Quick check

```
python skills/kicad/scripts/kcs.py env
python skills/kicad/scripts/kcs.py build examples/stm32node/design.json /tmp/stm32node
```

The second command writes a project, verifies it, and leaves a schematic
PDF and board renders under `/tmp/stm32node/kcs-out/`.

## How it fits together

```
interview -> design.json + DESIGN.md
          -> parts (stock libs | manufacturer | LCSC | generate symbol/footprint)
          -> kcs build  -> .kicad_sch  -> netlist == spec? ERC clean? PDF looks right?
                        -> .kicad_pcb  -> DRC clean? renders look right? route
          -> review report
          -> fab package
```

Everything that can be verified by KiCad is; everything else is written
into DESIGN.md with its source so you can check it.

## Verified facts (KiCad 10.0.6)

File versions: schematic `20260306`, board and footprint `20260206`,
symbol library `20251024`. Boards carry net names, not numbers. Sub-symbols
in `lib_symbols` are unprefixed. Schematic pin transform: flip Y, rotate
counter-clockwise, then mirror. Back-side footprint text: rotation + 180,
`justify mirror`. `kicad-cli` exit 5 = violations, 3 = failed to load.
Details and evidence in `skills/kicad/references/`.

## Development

`PROMPTS.md` logs every prompt that shaped this repo. Tests live as
scripts run against a real KiCad 10 install (see `tests/`). Skill evals
(prompts and expected outcomes for the skill-creator harness) are in
`evals/`.
