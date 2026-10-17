# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Absolute rules: things you MUST do

The following must always happen:
- all prompts MUST be added to PROMPTS.md
- if prompts are a response to the agent asking for feedback, include the feedback questions as well.

## What this repo is

Nine Claude Code skills (`skills/kicad*/SKILL.md`) that let an agent design
hardware in KiCad 10: interview the user, write a machine-checkable spec,
generate `.kicad_sch` / `.kicad_pcb` / `.kicad_sym` / `.kicad_mod` /
`.kicad_pro` files directly, and prove them with `kicad-cli`. All code lives
in `skills/kicad/scripts/` (the `kcs.py` CLI and the `kcslib` package,
Python 3.10+, stdlib only). The other eight skills are prose that call
`../kicad/scripts/kcs.py`, so the `skills/*` folders must be installed side
by side.

There is no `pyproject.toml`, linter config, or test runner config. Tests
are plain scripts.

## Commands

Everything needs a real KiCad 10 install (`kicad-cli` on PATH or
`KICAD_ROOT` set). Check the environment first; stop if it reports problems:

```bash
python skills/kicad/scripts/kcs.py env
```

Run tests (each is a standalone script; run one by name):

```bash
python tests/test_geom.py   # pin transform for every rotation/mirror, netlist-verified
python tests/test_pcb.py    # board writer; pad positions cross-checked with pcbnew
python tests/test_sym.py    # symbol generator, project library, ERC/netlist round trip
python tests/test_fp.py     # footprint generator vs stock footprints, DRC
python tests/test_hier.py   # hierarchical build of the example, sheet pins, placement hints
python tests/test_e2e.py    # full build of examples/stm32node/design.json
```

`tests/test_geom_unit.py` is the one `unittest` module; it covers the
`geom` input checks and point helpers and needs no KiCad:

```bash
python -m unittest tests/test_geom_unit.py -v
```

Tests write to a fresh `tempfile.mkdtemp(prefix="kcs-test-")` and fail by
assertion, so a pass is exit code 0. `test_e2e` and `test_hier` also print
an `OK` line; `test_geom` prints the netlist comparison and ERC counts for
you to read.

Build the bundled example end to end (schematic, board, project, ERC,
netlist-vs-spec, DRC, renders):

```bash
python skills/kicad/scripts/kcs.py build examples/stm32node/design.json <out-dir>
python skills/kicad/scripts/kcs.py spec validate examples/stm32node/design.json
```

Optional extras: `pip install pdfplumber` (for `kcs pins-from-pdf`),
`pip install easyeda2kicad` (LCSC parts), Java (Freerouting via `kcs autoroute`).

Skill evals live in `evals/*.evals.json` in skill-creator format; run them
with `/skill-creator` or by hand as described in `evals/README.md`.

## Architecture

### Data flow

```text
design.json  --build.load_spec/validate_spec-->  spec dict
  --build.build_schematic-->  sch.Schematic per sheet  --save-->  .kicad_sch
  --build.build_board-->      pcb.Board                --save-->  .kicad_pcb
  --project.write_pro-->      .kicad_pro + project lib tables
  --check.netlist/compare_nets, check.erc, check.drc, check.render_board-->  BuildResult
```

The spec is netlist-level on purpose: every net lists its `(ref, pin)`
pairs, every unused pin is explicitly no-connect, and `validate_spec`
refuses a symbol with undecided pins. The full key reference is
`skills/kicad-interview/references/design-json.md`; the module docstring of
`kcslib/build.py` has the short form.

### `kcslib` modules

- `sexpr` - dependency-free S-expression reader/writer. Bare tokens are
  `Atom` (a `str` subclass), quoted strings are plain `str`, numbers keep
  their original text so unchanged files round-trip byte-for-byte apart
  from whitespace. Use `num()` for computed numbers. Never edit a KiCad
  file with regex; parse, modify the tree, write back.
- `env` - discovers the KiCad root, `kicad-cli`, bundled python (which has
  the `pcbnew` SWIG module), library dirs, and exposes `run_cli`. Discovery
  only, writes nothing.
- `libs` - reads the global and project `sym-lib-table` / `fp-lib-table`
  (KiCad 10 nests the stock table behind a `(type "Table")` entry), resolves
  `Lib:Name` ids, follows `(extends ...)`, extracts pin geometry, searches.
- `geom` - the one place coordinate math lives. Symbol libraries are Y-up;
  placed schematics and boards are Y-down. Pin transform is
  flip Y, rotate CCW, then mirror. Grid is 1.27 mm.
- `sch` - `Schematic` builder. `add_symbol` returns a `PlacedSymbol` that
  knows where every pin ends up, so `connect_label`, `connect_power` and
  `wire_pins` attach exactly on pin ends. Copies used symbols into
  `lib_symbols`.
- `pcb` - `Board` builder. Copies footprints verbatim from the library and
  adds position, layer, net names on pads, and the schematic `path` so
  "Update PCB from Schematic" recognises them. Back-side text rules live
  here.
- `build` - orchestration: layout by group, hierarchical sheets with sheet
  pins for crossing nets, board placement from `board.hints`, then the
  verification chain.
- `check` - wraps `kicad-cli sch erc`, `pcb drc`, netlist export, PDF/SVG/PNG
  export and returns plain dicts. `compare_nets` is the netlist-equals-spec
  gate.
- `sym` / `fp` - deterministic KLC-style symbol and IPC-7351B footprint
  generators plus their `check_*` KLC linters.
- `project` - `.kicad_pro` writer with per-fab design rule presets
  (`FAB_RULES`).
- `export`, `autoroute`, `parts`, `pinsheet` - fab packages and STEP;
  Freerouting via DSN/SES and zone fill through the bundled pcbnew; LCSC
  lookup (keyword search endpoints are bot-blocked, only `C` numbers work);
  pdfplumber pin-table extraction.

### Verified KiCad 10.0.6 facts the writers depend on

Schematic version `20260306`, board and footprint `20260206`, symbol library
`20251024`. Boards carry net names, not numbers. Sub-symbols in
`lib_symbols` are unprefixed. There is no headless schematic API, so
schematics are written as text. `kicad-cli` exit 5 means violations, 3
means failed to load, which means the generated file is wrong, not KiCad.
Evidence is in `skills/kicad/references/`; update those files when a fact
changes rather than restating it in code comments.

## Conventions

- Every generator output is verified by round-tripping through `kicad-cli`
  (netlist-vs-spec, ERC, DRC, render) and then looked at. Keep that chain
  intact when adding features; a new writer feature needs a test in
  `tests/` that runs against the real install.
- Skill prose lives in `SKILL.md` with a frontmatter `description` that is
  the trigger text; the `kicad` skill is the router and must be loaded
  first. Cross-skill references use relative paths (`../kicad/...`).
- `PROMPTS.md` logs every prompt given to the AI for this repo, verbatim,
  numbered. Append each new user prompt before doing other work.
- Line endings are LF everywhere (`.gitattributes`); renders and models
  are binary.
- Windows is the tested platform. KiCad is at `C:\Program Files\KiCad\10.0`;
  quote paths and use forward slashes inside KiCad files.
