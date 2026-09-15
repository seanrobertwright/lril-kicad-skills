---
name: kicad
description: Core KiCad 10 skill and router. Use whenever the user mentions KiCad, schematics, PCBs, boards, footprints, symbols, gerbers, ERC/DRC, or wants to design electronics hardware, even if they do not say "KiCad". Provides the environment facts (kicad-cli, file-format versions, library paths), the `kcs` command line that writes and verifies KiCad 10 files, and the workflow that chains the other kicad-* skills (interview, parts, symbol, footprint, schematic, pcb, review, export). Load this first, then the specific skill for the task.
---

# KiCad 10 core

This skill family lets an AI design real hardware in KiCad 10 the way a careful
engineer would: interview first, write everything down, generate files from
that written spec, and verify every file with KiCad's own tools before showing
it to the user. Nothing is left to assumption, nothing is trusted unverified.

## What is verified vs. what is inferred

Verified against KiCad 10.0.6 on Windows (see `references/`):

| Fact | Value |
|---|---|
| Schematic format version | `20260306`, generator `eeschema`, generator_version `10.0` |
| Board format version | `20260206`, generator `pcbnew` |
| Symbol library version | `20251024`, generator `kicad_symbol_editor` |
| Footprint version | `20260206` |
| Net numbering on boards | none; pads/tracks/zones carry `(net "NAME")` by name |
| Sub-symbol names in `lib_symbols` | bare `Name_unit_style`; only the top-level name gets `Lib:` |
| Schematic coordinates | mm, Y down, 1.27 mm grid; symbol libraries are Y up |
| Symbol transform | pin = origin + mirror(rotate_ccw(flipY(lib_pin), rot)) |
| Footprint text on back side | angle = rotation + 180, Y negated, layers swapped, `justify mirror` |
| Headless schematic API | none (no SWIG for eeschema, IPC API is GUI+board only in v10) |
| `kicad-cli` exit codes | 0 ok, 5 = violations with `--exit-code-violations`, 3 = failed to load |

Everything the generators produce is checked by round-tripping through
`kicad-cli` (ERC, DRC, netlist export, PDF/PNG render). If a command below
reports a load failure the file is wrong, not KiCad.

## The `kcs` command line

All tooling lives in `scripts/` and needs only Python 3.10+ (no packages).
Run it as:

```
python <this-skill-dir>/scripts/kcs.py <command> ...
```

| Command | Purpose |
|---|---|
| `env` | KiCad install, version, library paths, bundled python |
| `sym search <text>` / `sym info <Lib:Name>` | find stock/project symbols; list pins (number, name, type, unit) |
| `fp search <text>` / `fp info <Lib:Name>` | find footprints; list pads |
| `spec validate <design.json>` | structural + library checks on the design spec |
| `build <design.json> <project-dir>` | schematic (flat or hierarchical) + board + project from the spec, then ERC, netlist-vs-spec, DRC, PDF/PNG |
| `erc <sch>` / `drc <pcb> [--parity]` | JSON summaries of violations |
| `netlist <sch>` / `netcheck <spec> <sch>` | nets to pins; compare against the spec |
| `render <pcb>` / `pdf <sch|pcb>` | images you can look at with the Read tool |
| `symgen <pins.json> <lib.kicad_sym>` | KLC-style symbol from a pin table |
| `fpgen <pkg.json> <lib.pretty>` | IPC-7351B footprint from package dimensions |
| `klc <file>` | quick KLC checks on a symbol library or footprint |
| `fab <pcb> <sch> <out> --fab jlcpcb\|pcbway\|oshpark\|generic` | gerbers, drill, pos, BOM, zip |
| `step <pcb> <out.step>` | 3D export |
| `autoroute <pcb>` / `fill <pcb>` | Freerouting via DSN/SES; zone fill via bundled pcbnew |
| `upgrade <file>` | rewrite any KiCad file to the 10.0 format |
| `jlc <C12345>` | LCSC/JLCPCB price, stock, package, basic/extended, EasyEDA model availability |
| `pins-from-pdf <pdf> --package X` | draft a symgen pin table from a datasheet, with confidence per pin |

Run `python scripts/kcs.py env` at the start of every session and stop if it
reports problems (wrong version, missing kicad-cli).

## Workflow (which skill when)

1. **kicad-interview** - always first for a new design. It interrogates the
   user until `design/DESIGN.md` and `design/design.json` contain every
   decision with its source. No schematic is drawn before the user approves
   the design contract.
2. **kicad-parts** - resolve every component to a concrete symbol, footprint,
   MPN and (optionally) distributor number. Stock libraries first; then
   manufacturer/LCSC/SnapEDA sources; then generate.
3. **kicad-symbol** / **kicad-footprint** - only for parts the stock library
   lacks. Always from the datasheet, never from memory.
4. **kicad-schematic** - `kcs build` from the spec, verify netlist == spec,
   ERC clean, then look at the PDF and iterate on placement/readability.
5. **kicad-pcb** - stackup, outline, placement, routing (manual or
   Freerouting), DRC clean, renders reviewed.
6. **kicad-review** - independent checklist review before any export.
7. **kicad-export** - fab package for the chosen manufacturer.

For an existing project (user already has files): run `kcs erc`/`kcs drc`,
export PDF/renders, read them, then go to kicad-review.

## Rules that apply in every kicad-* skill

- **Look, do not assume.** Symbol pin numbers, footprint pad numbers, pin
  types and library names come from `kcs sym info` / `kcs fp info` or the
  datasheet, never from memory. Pinouts of SOT-23 transistors, regulators,
  crystals and connectors vary between manufacturers.
- **Every pin is decided.** The spec validator refuses a symbol whose pins are
  neither on a net nor marked no-connect. Ask the user, do not guess.
- **Verify with KiCad, then with your eyes.** After every generation step:
  netlist-vs-spec, ERC/DRC JSON, then open the PDF/PNG with the Read tool and
  check it reads like a schematic a human drew. Fix and rerun.
- **Record decisions with their source** (`user`, `datasheet p.N`,
  `computed`, `recommended-accepted`) in DESIGN.md. A computed value shows its
  formula and inputs.
- **Never edit a user's KiCad file by regex.** Parse with `kcslib.sexpr`,
  modify the tree, write back, and back up first.
- **Windows paths**: KiCad lives in `C:\Program Files\KiCad\10.0`; the bundled
  python is `bin\python.exe` (has `pcbnew`). Quote paths. Use forward slashes
  inside KiCad files.

## Where to read more

- `references/kicad10-file-formats.md` - verified anatomy of every file type
  with real snippets (read when hand-editing or debugging a load failure).
- `references/kicad10-cli-and-apis.md` - every `kicad-cli` flag, ERC/DRC JSON
  shape, jobset format, SWIG and kipy limits.
- `references/kicad-cli-help.txt` - raw `--help` of every command.
- `references/part-sources-and-klc.md` - where symbols/footprints come from
  and the KLC rules that matter.
- `scripts/kcslib/` - `sexpr` (parser/writer), `libs` (library access),
  `sch` (schematic writer), `pcb` (board writer), `sym`/`fp` (generators),
  `build` (spec to project), `check` (ERC/DRC/netlist), `export`, `autoroute`.
