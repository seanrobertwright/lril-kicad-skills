#!/usr/bin/env python3
"""kcs - KiCad skills command line.

Run with any Python 3.10+ (no third-party packages needed):

    python skills/kicad/scripts/kcs.py <command> [options]

Commands
--------
  env                         show KiCad install, versions, library paths
  sym search <text>           search stock + project symbol libraries
  sym info <Lib:Name>         pins, units, footprint filters of a symbol
  fp search <text>            search footprint libraries
  fp info <Lib:Name>          pads of a footprint
  spec validate <spec.json>   structural checks on a design spec
  build <spec.json> <dir>     schematic (+board) from a spec, then ERC/netlist/DRC
  erc <file.kicad_sch>        ERC as JSON summary
  drc <file.kicad_pcb>        DRC as JSON summary
  netlist <file.kicad_sch>    nets -> pins as JSON
  netcheck <spec> <sch>       compare a schematic's netlist with the spec
  render <file.kicad_pcb>     PNG renders (top/bottom) for visual review
  pdf <file.kicad_sch|pcb>    PDF for visual review
  symgen <pins.json> <lib>    generate a .kicad_sym from a pin table
  fpgen <pkg.json> <dir.pretty>  generate a .kicad_mod from package dimensions
  klc <file>                  KLC-style checks on a .kicad_sym or .kicad_mod
  fab <pcb> <sch> <out> [--fab jlcpcb|pcbway|oshpark|generic]  gerbers, drill, pos, bom, zip
  step <pcb> <out.step>       STEP export
  autoroute <pcb> [out]       Freerouting (Java) autoroute + zone fill
  fill <pcb>                  fill zones in place (pcbnew python)
  upgrade <file>              rewrite sch/pcb/sym/fp to the KiCad 10 format
  symview <Lib:Name> [--project dir]  PDF of one symbol with its pins labelled (look at it with Read)
  fpview <Lib:Name> [--project dir]   PNG render of one footprint
  jlc <C12345>                LCSC/JLCPCB price, stock, package, basic/extended, datasheet
  pins-from-pdf <pdf>         draft a symgen pin table from a datasheet (review before use)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kcslib import autoroute, build, check, env as kenv, export, fp as fpgen, libs, parts, pinsheet, sexpr, sym as symgen  # noqa: E402


def _print(obj) -> None:
    print(json.dumps(obj, indent=1, default=str))


def cmd_env(a):
    _print(kenv.get().as_dict())


def cmd_sym(a):
    if a.sub == "search":
        _print(libs.search_symbols(a.text, Path(a.project) if a.project else None, limit=a.limit))
    else:
        node = libs.resolve_symbol(a.text, Path(a.project) if a.project else None)
        pins = libs.symbol_pins(node)
        _print({"lib_id": a.text, "description": libs.symbol_description(node), "units": libs.symbol_units(node),
                "power": libs.is_power_symbol(node), "footprint": sexpr.get_property(node, "Footprint"),
                "fp_filters": sexpr.get_property(node, "ki_fp_filters"),
                "datasheet": sexpr.get_property(node, "Datasheet"), "bbox": libs.symbol_bbox(node),
                "pins": [{"number": p.number, "name": p.name, "type": p.etype, "unit": p.unit, "at": [p.x, p.y],
                          "angle": p.angle, "hidden": p.hidden} for p in pins]})


def cmd_fp(a):
    if a.sub == "search":
        _print(libs.search_footprints(a.text, Path(a.project) if a.project else None, limit=a.limit))
    else:
        node = libs.load_footprint(a.text, Path(a.project) if a.project else None)
        _print({"fp_id": a.text, "descr": (sexpr.child(node, "descr") or ["", ""])[1],
                "attr": [str(x) for x in (sexpr.child(node, "attr") or [])[1:]],
                "model": (sexpr.child(node, "model") or ["", ""])[1], "pads": libs.footprint_pads(node)})


def cmd_spec(a):
    spec = build.load_spec(a.spec)
    probs = build.validate_spec(spec)
    _print({"ok": not probs, "problems": probs, "components": len(spec.get("components", [])),
            "nets": len(spec.get("nets", {}))})
    sys.exit(0 if not probs else 1)


def cmd_build(a):
    spec = build.load_spec(a.spec)
    res = build.build(spec, a.dir, with_board=not a.no_board, render=not a.no_render)
    print(res.summary())
    if not res.netlist_check["ok"]:
        sys.exit(2)


def cmd_erc(a):
    r = check.erc(Path(a.file), a.severity)
    _print({"ok": r["ok"], "count": len(r["violations"]), "violations": r["violations"]})


def cmd_drc(a):
    r = check.drc(Path(a.file), a.severity, schematic_parity=a.parity)
    _print({"ok": r["ok"], "violations": r["violations"], "unconnected": r["unconnected"],
            "schematic_parity": r["schematic_parity"]})


def cmd_netlist(a):
    _print(check.netlist(Path(a.file)))


def cmd_netcheck(a):
    spec = build.load_spec(a.spec)
    expected = {n: [(str(r), str(p)) for r, p in pins] for n, pins in spec["nets"].items()}
    _print(check.compare_nets(expected, check.netlist(Path(a.sch))["nets"]))


def cmd_render(a):
    p = Path(a.file)
    out = Path(a.out) if a.out else p.parent / "kcs-out"
    out.mkdir(exist_ok=True)
    files = []
    for side in ("top", "bottom"):
        files.append(str(check.render_board(p, out / f"{p.stem}-{side}.png", side, zoom=a.zoom)))
    _print(files)


def cmd_pdf(a):
    p = Path(a.file)
    out = Path(a.out) if a.out else p.with_suffix(".pdf")
    if p.suffix == ".kicad_sch":
        export.sch_pdf(p, out)
    else:
        export.pcb_pdf(p, out)
    print(out)


def cmd_symgen(a):
    data = json.loads(Path(a.pins).read_text(encoding="utf-8"))
    specs = data if isinstance(data, list) else [data]
    out = []
    for d in specs:
        pins = [symgen.PinSpec(str(p["number"]), p["name"], p.get("type", "passive"), p.get("side", "left"),
                               p.get("shape", "line"), int(p.get("unit", 1)), p.get("hidden"), int(p.get("gap_before", 0)),
                               [(x["name"], x.get("type", "passive")) for x in p.get("alternates", [])])
                for p in d["pins"]]
        out.append(symgen.SymbolSpec(d["name"], d.get("reference", "U"), pins, d.get("value"), d.get("footprint", ""),
                                     d.get("datasheet", ""), d.get("description", ""), d.get("keywords", ""),
                                     d.get("fp_filters", ""), power=bool(d.get("power", False)),
                                     units=int(d.get("units", 1)), extra_props=d.get("props", {}),
                                     hide_pin_numbers=bool(d.get("hide_pin_numbers", False)),
                                     hide_pin_names=bool(d.get("hide_pin_names", False))))
    path = symgen.write_library(out, a.lib, merge=not a.replace)
    lib = sexpr.load(path)
    problems = {}
    for s in sexpr.children(lib, "symbol"):
        pr = symgen.check_symbol(s)
        if pr:
            problems[str(s[1])] = pr
    _print({"written": str(path), "symbols": [s.name for s in out], "klc": problems})


def cmd_fpgen(a):
    d = json.loads(Path(a.pkg).read_text(encoding="utf-8"))
    kind = d.pop("kind")
    name = d.pop("name")
    gen = {"chip": fpgen.chip, "gullwing": fpgen.gullwing, "no_lead": fpgen.no_lead, "dip": fpgen.dip, "header": fpgen.header}[kind]
    spec = gen(name, **d)
    path = fpgen.write_footprint(spec, a.pretty)
    _print({"written": str(path), "pads": libs.footprint_pads(sexpr.load(path)), "klc": fpgen.check_footprint(sexpr.load(path))})


def cmd_klc(a):
    p = Path(a.file)
    tree = sexpr.load(p)
    if p.suffix == ".kicad_sym":
        _print({str(s[1]): symgen.check_symbol(s) for s in sexpr.children(tree, "symbol")})
    else:
        _print({str(tree[1]): fpgen.check_footprint(tree)})


def cmd_fab(a):
    pcb = Path(a.pcb)
    layers = 2
    try:
        tree = sexpr.load(pcb)
        layers = sum(1 for l in (sexpr.child(tree, "layers") or []) if isinstance(l, list) and str(l[2]) == "signal")
    except Exception:
        pass
    _print(export.fab_package(pcb, Path(a.sch) if a.sch else None, Path(a.out), a.fab, layers))


def cmd_step(a):
    print(export.step(Path(a.pcb), Path(a.out)))


def cmd_autoroute(a):
    print(autoroute.autoroute(Path(a.pcb), Path(a.out) if a.out else None, passes=a.passes))


def cmd_fill(a):
    autoroute.fill_zones(Path(a.pcb))
    print("zones filled:", a.pcb)


def cmd_jlc(a):
    _print(parts.search(a.query))


def cmd_pins_from_pdf(a):
    pages = None
    if a.pages:
        pages = []
        for part in a.pages.split(","):
            if "-" in part:
                lo, hi = part.split("-")
                pages += list(range(int(lo), int(hi) + 1))
            else:
                pages.append(int(part))
    ex = pinsheet.extract(a.pdf, pages, package=a.package)
    data = ex.to_json(a.name)
    if a.out:
        Path(a.out).write_text(json.dumps(data, indent=1), encoding="utf-8")
        print(f"draft pin table written to {a.out} ({len(data['pins'])} pins, method {ex.method}, "
              f"pages {sorted(set(ex.pages_scanned))}, package columns {ex.package_columns}, used {ex.package_used!r})")
        for w in ex.warnings:
            print("warning:", w)
    else:
        _print(data)


def cmd_symview(a):
    """Render one symbol to a PDF the Read tool can display (SVG cannot be viewed directly)."""
    import tempfile
    from kcslib import sch as schmod
    proj = Path(a.project) if a.project else None
    tmp = Path(tempfile.mkdtemp(prefix="kcs-symview-"))
    s = schmod.Schematic("symview", title=a.lib_id, paper="A5", project_dir=proj)
    sym = s.add_symbol(a.lib_id, "U1", a.lib_id.split(":")[-1], at=(101.6, 76.2))
    for p in sym.visible_pins():
        s.connect_label(sym, p.number, p.name or p.number)
    p = s.save(tmp / "symview.kicad_sch")
    out = Path(a.out) if a.out else Path.cwd() / (a.lib_id.replace(":", "_") + ".pdf")
    check.export_pdf(p, out)
    print(out)


def cmd_fpview(a):
    """Render one footprint to a PNG via a scratch board."""
    import tempfile
    proj = Path(a.project) if a.project else None
    tmp = Path(tempfile.mkdtemp(prefix="kcs-fpview-"))
    from kcslib import pcb as pcbmod
    b = pcbmod.Board(project_dir=proj)
    f = b.add_footprint(a.fp_id, "X1", a.fp_id.split(":")[-1], (50, 50))
    x0, y0, x1, y1 = f.bbox()
    m = 3
    b.outline_rect(x0 - m, y0 - m, (x1 - x0) + 2 * m, (y1 - y0) + 2 * m)
    p = b.save(tmp / "fpview.kicad_pcb")
    out = Path(a.out) if a.out else Path.cwd() / (a.fp_id.replace(":", "_") + ".png")
    check.render_board(p, out, "top", zoom=1.0)
    print(out)


def cmd_upgrade(a):
    p = Path(a.file)
    kind = {".kicad_sch": "sch", ".kicad_pcb": "pcb", ".kicad_sym": "sym", ".kicad_mod": "fp"}[p.suffix]
    res = kenv.run_cli(kind, "upgrade", "--force", str(p))
    print(res.stdout + res.stderr)
    sys.exit(res.returncode)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kcs", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("env").set_defaults(fn=cmd_env)
    for name, fn in (("sym", cmd_sym), ("fp", cmd_fp)):
        p = sp.add_parser(name)
        p.add_argument("sub", choices=["search", "info"])
        p.add_argument("text")
        p.add_argument("--project", help="project dir (for project-local lib tables)")
        p.add_argument("--limit", type=int, default=40)
        p.set_defaults(fn=fn)
    p = sp.add_parser("spec"); p.add_argument("sub", choices=["validate"]); p.add_argument("spec"); p.set_defaults(fn=cmd_spec)
    p = sp.add_parser("build"); p.add_argument("spec"); p.add_argument("dir")
    p.add_argument("--no-board", action="store_true"); p.add_argument("--no-render", action="store_true"); p.set_defaults(fn=cmd_build)
    p = sp.add_parser("erc"); p.add_argument("file"); p.add_argument("--severity", default="all", choices=["all", "error", "warning"]); p.set_defaults(fn=cmd_erc)
    p = sp.add_parser("drc"); p.add_argument("file"); p.add_argument("--severity", default="all", choices=["all", "error", "warning"])
    p.add_argument("--parity", action="store_true", help="also check schematic parity"); p.set_defaults(fn=cmd_drc)
    p = sp.add_parser("netlist"); p.add_argument("file"); p.set_defaults(fn=cmd_netlist)
    p = sp.add_parser("netcheck"); p.add_argument("spec"); p.add_argument("sch"); p.set_defaults(fn=cmd_netcheck)
    p = sp.add_parser("render"); p.add_argument("file"); p.add_argument("--out"); p.add_argument("--zoom", type=float, default=1.0); p.set_defaults(fn=cmd_render)
    p = sp.add_parser("pdf"); p.add_argument("file"); p.add_argument("--out"); p.set_defaults(fn=cmd_pdf)
    p = sp.add_parser("symgen"); p.add_argument("pins"); p.add_argument("lib"); p.add_argument("--replace", action="store_true"); p.set_defaults(fn=cmd_symgen)
    p = sp.add_parser("fpgen"); p.add_argument("pkg"); p.add_argument("pretty"); p.set_defaults(fn=cmd_fpgen)
    p = sp.add_parser("klc"); p.add_argument("file"); p.set_defaults(fn=cmd_klc)
    p = sp.add_parser("fab"); p.add_argument("pcb"); p.add_argument("sch", nargs="?"); p.add_argument("out")
    p.add_argument("--fab", default="generic", choices=list(export.FAB_PRESETS)); p.set_defaults(fn=cmd_fab)
    p = sp.add_parser("step"); p.add_argument("pcb"); p.add_argument("out"); p.set_defaults(fn=cmd_step)
    p = sp.add_parser("autoroute"); p.add_argument("pcb"); p.add_argument("out", nargs="?"); p.add_argument("--passes", type=int, default=100); p.set_defaults(fn=cmd_autoroute)
    p = sp.add_parser("fill"); p.add_argument("pcb"); p.set_defaults(fn=cmd_fill)
    p = sp.add_parser("upgrade"); p.add_argument("file"); p.set_defaults(fn=cmd_upgrade)
    p = sp.add_parser("symview", help="render a symbol (stock or project) to a PDF you can look at")
    p.add_argument("lib_id"); p.add_argument("--project"); p.add_argument("--out"); p.set_defaults(fn=cmd_symview)
    p = sp.add_parser("fpview", help="render a footprint (stock or project) to a PNG you can look at")
    p.add_argument("fp_id"); p.add_argument("--project"); p.add_argument("--out"); p.set_defaults(fn=cmd_fpview)
    p = sp.add_parser("jlc", help="LCSC/JLCPCB part lookup by LCSC number (C12345); explains the fallback for keywords")
    p.add_argument("query"); p.set_defaults(fn=cmd_jlc)
    p = sp.add_parser("pins-from-pdf", help="draft a symgen pin table from a datasheet PDF")
    p.add_argument("pdf"); p.add_argument("--pages", help="e.g. 3-5,9"); p.add_argument("--name", default="PART")
    p.add_argument("--package", help="package column to use when the table lists several (e.g. DBV, LQFP48)")
    p.add_argument("--out", help="write pins.json here instead of printing"); p.set_defaults(fn=cmd_pins_from_pdf)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
