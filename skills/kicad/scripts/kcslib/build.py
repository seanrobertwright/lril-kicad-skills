"""Turn a *design spec* (JSON) into a KiCad 10 project: schematic (flat or
hierarchical), board, and project file, then verify the result against the
spec with kicad-cli.

The spec is deliberately netlist-level so that everything the AI decided in
the design interview is written down explicitly and machine-checkable. The
format is documented in ``kicad-interview/references/design-json.md``; the
essentials::

    {
      "project": "blinky", "title": "Blinky", "rev": "A", "paper": "A4",
      "libs": {"symbols": [...], "footprints": [...]},
      "power_nets": ["+3V3", "GND"], "global_nets": ["SWDIO"],
      "groups": [{"name": "power", "title": "Power supply"}],
      "sheets": [{"name": "Power", "file": "power.kicad_sch", "groups": ["power"]}],
      "components": [{"ref": "U1", "symbol": "Lib:Name", "value": "...", "footprint": "Lib:Name",
                      "group": "power", "props": {"MPN": "..."}}],
      "nets": {"GND": [["U1", "1"], ["C1", "2"]]},
      "no_connect": [["U2", "7"]], "unused_pins_nc": ["U2"],
      "wires": [[["R1", "2"], ["D1", "1"]]],
      "board": {"width": 50, "height": 40, "layers": 2, "fab": "jlcpcb",
                "zones": [{"net": "GND", "layer": "B.Cu"}],
                "mounting_holes": {"inset": 3.5},
                "placement": {"U1": [10, 10, 0, "F.Cu"]},
                "hints": {"J1": {"edge": "left", "rot": 90}, "U2": {"center": true}, "C3": {"near": "U2"}}}
    }

Coordinates are millimetres.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from . import check, geom, libs, pcb, project, sch, sexpr

PAPER_SIZES = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "USLetter": (279.4, 215.9), "USLedger": (431.8, 279.4)}


@dataclass
class BuildResult:
    project_dir: Path
    sch_path: Path
    pcb_path: Path | None
    pro_path: Path
    netlist_check: dict
    erc: dict
    drc: dict | None = None
    notes: list[str] = field(default_factory=list)
    sheet_paths: list[Path] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"project: {self.project_dir}", f"schematic: {self.sch_path.name}"]
        if self.sheet_paths:
            lines.append("sheets: " + ", ".join(p.name for p in self.sheet_paths))
        if self.pcb_path:
            lines.append(f"board: {self.pcb_path.name}")
        nc = self.netlist_check
        lines.append(f"netlist matches spec: {nc['ok']}")
        for p in nc["problems"]:
            lines.append(f"  - {p}")
        if nc.get("pins_not_in_spec"):
            lines.append(f"  pins connected but absent from spec: {nc['pins_not_in_spec'][:10]}")
        sev = {}
        for v in self.erc["violations"]:
            sev[(v["severity"], v["type"])] = sev.get((v["severity"], v["type"]), 0) + 1
        lines.append(f"ERC: {sum(sev.values())} violations " + ", ".join(f"{k[1]}({k[0]})x{n}" for k, n in sorted(sev.items())))
        if self.drc:
            sev = {}
            for v in self.drc["violations"]:
                sev[(v["severity"], v["type"])] = sev.get((v["severity"], v["type"]), 0) + 1
            lines.append(f"DRC: {sum(sev.values())} violations, {len(self.drc['unconnected'])} unrouted " +
                         ", ".join(f"{k[1]}({k[0]})x{n}" for k, n in sorted(sev.items())))
        lines += [f"note: {n}" for n in self.notes]
        return "\n".join(lines)


def load_spec(path: str | Path) -> dict:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("YAML specs need PyYAML; use JSON or `pip install pyyaml`") from exc
        return yaml.safe_load(text)
    return json.loads(text)


project_dir_hint: Path | None = None


def validate_spec(spec: dict) -> list[str]:
    """Structural + library checks. Returns a list of problems (empty = fine)."""
    problems: list[str] = []
    for key in ("project", "components", "nets"):
        if key not in spec:
            problems.append(f"missing top-level key {key!r}")
    if problems:
        return problems
    refs = {}
    for c in spec["components"]:
        for key in ("ref", "symbol", "value"):
            if key not in c:
                problems.append(f"component {c} missing {key!r}")
        if c.get("ref") in refs:
            problems.append(f"duplicate reference {c['ref']}")
        refs[c.get("ref")] = c
        if "footprint" not in c:
            problems.append(f"{c.get('ref')}: no footprint assigned (every part must have one before the board can be built)")
    pin_use: dict[tuple[str, str], str] = {}
    for net, pins in spec["nets"].items():
        if not isinstance(pins, list) or not pins:
            problems.append(f"net {net!r} has no pins")
            continue
        for p in pins:
            if not (isinstance(p, list) and len(p) == 2):
                problems.append(f"net {net!r}: pin entry {p!r} must be [ref, pin]")
                continue
            ref, pin = str(p[0]), str(p[1])
            if ref not in refs:
                problems.append(f"net {net!r} references unknown component {ref!r}")
            key = (ref, pin)
            if key in pin_use and pin_use[key] != net:
                problems.append(f"pin {ref}.{pin} is on two nets: {pin_use[key]!r} and {net!r}")
            pin_use[key] = net
        if len(pins) == 1 and net not in spec.get("power_nets", []):
            problems.append(f"net {net!r} has a single pin ({pins[0]}); single-pin nets are usually a mistake")
    for p in spec.get("no_connect", []):
        key = (str(p[0]), str(p[1]))
        if key in pin_use:
            problems.append(f"pin {key} is marked no-connect but is on net {pin_use[key]!r}")
    # sheets reference known groups, each group at most once
    seen_groups: dict[str, str] = {}
    for sh in spec.get("sheets", []):
        for key in ("name", "file", "groups"):
            if key not in sh:
                problems.append(f"sheet {sh} missing {key!r}")
        for g in sh.get("groups", []):
            if g in seen_groups:
                problems.append(f"group {g!r} is assigned to two sheets ({seen_groups[g]!r} and {sh.get('name')!r})")
            seen_groups[g] = sh.get("name", "")
    # board hints reference known refs
    for ref, hint in (spec.get("board", {}).get("hints") or {}).items():
        if ref not in refs:
            problems.append(f"board.hints: unknown reference {ref!r}")
        if hint.get("near") and hint["near"] not in refs:
            problems.append(f"board.hints: {ref} near unknown reference {hint['near']!r}")
    # pins must exist on the symbol; every non-hidden pin should be accounted for
    used_by_ref: dict[str, set[str]] = {}
    for (ref, pin) in list(pin_use) + [(str(p[0]), str(p[1])) for p in spec.get("no_connect", [])]:
        used_by_ref.setdefault(ref, set()).add(pin)
    for ref, c in refs.items():
        try:
            node = libs.resolve_symbol(c["symbol"], project_dir_hint)
        except Exception as exc:  # unknown library / symbol
            problems.append(f"{ref}: symbol {c.get('symbol')!r} not found ({exc})")
            continue
        if c.get("footprint"):
            try:
                libs.footprint_path(c["footprint"], project_dir_hint)
            except Exception as exc:
                problems.append(f"{ref}: footprint {c['footprint']!r} not found ({exc}); "
                                f"use `kcs fp search` to find the right name")
        unit = int(c.get("unit", 1))
        pins = [p for p in libs.symbol_pins(node) if p.unit in (0, unit)]
        have = {p.number for p in pins}
        names = {p.name: p.number for p in pins}
        for pin in used_by_ref.get(ref, set()):
            if pin not in have:
                hint = f" (did you mean pin {names[pin]!r} = {pin!r} by name?)" if pin in names else ""
                problems.append(f"{ref}: pin {pin!r} does not exist on {c['symbol']}; pins are {sorted(have)}{hint}")
        missing = [p for p in pins if not p.hidden and p.number not in used_by_ref.get(ref, set())
                   and p.etype != "no_connect"]
        if missing and ref in spec.get("unused_pins_nc", []):
            missing = []  # user declared: every remaining pin is deliberately unconnected
        if missing:
            problems.append(f"{ref}: pins not on any net and not marked no_connect: "
                            + ", ".join(f"{p.number}({p.name})" for p in missing[:12])
                            + (" ..." if len(missing) > 12 else "")
                            + " - decide each one explicitly")
    return problems


# --------------------------------------------------------------------------- #
# Schematic
# --------------------------------------------------------------------------- #
def _pin_map(spec: dict) -> dict[tuple[str, str], str]:
    m: dict[tuple[str, str], str] = {}
    for net, pins in spec["nets"].items():
        for ref, pin in pins:
            m[(str(ref), str(pin))] = net
    return m


def _label_width(text: str) -> float:
    return len(text) * 1.27 * 0.85 + 2.54


def _put(s: sch.Schematic, c: dict, at: tuple[float, float]) -> sch.PlacedSymbol:
    return s.add_symbol(c["symbol"], c["ref"], c["value"], at, rot=float(c.get("rot", 0)),
                        mirror=c.get("mirror"), unit=int(c.get("unit", 1)),
                        footprint=c.get("footprint", ""), props=c.get("props"),
                        dnp=bool(c.get("dnp", False)), datasheet=c.get("datasheet", ""))


def _layout(s: sch.Schematic, comps: list[dict], spec: dict, pin_net: dict, power_nets: set[str],
            top_margin: float = 22.86) -> dict[str, sch.PlacedSymbol]:
    """Place ``comps`` on schematic ``s`` in titled group blocks; bump the
    paper size if the page overflows. Returns ref -> placed symbol."""
    groups: dict[str, list[dict]] = {}
    order: list[str] = [g["name"] for g in spec.get("groups", [])]
    for c in comps:
        g = c.get("group", "main")
        groups.setdefault(g, []).append(c)
        if g not in order:
            order.append(g)
    titles = {g["name"]: g.get("title", g["name"]) for g in spec.get("groups", [])}

    def measure(c: dict) -> tuple[float, float]:
        node = s._ensure_lib_symbol(c["symbol"])
        unit = int(c.get("unit", 1))
        x0, y0, x1, y1 = libs.symbol_bbox(node, unit)
        rot = float(c.get("rot", 0))
        w, h = (x1 - x0, y1 - y0) if rot % 180 == 0 else (y1 - y0, x1 - x0)
        allow = 0.0
        for p in libs.symbol_pins(node):
            if p.unit not in (0, unit):
                continue
            net = pin_net.get((c["ref"], p.number))
            if net and net not in power_nets:
                allow = max(allow, _label_width(net))
        return (w + 2 * allow + 5.08, h + 2 * 7.62)

    sizes_all = {c["ref"]: measure(c) for c in comps}

    def plan(paper_name: str) -> tuple[list[dict], float]:
        page_w, page_h = PAPER_SIZES.get(paper_name, (297, 210))
        margin_x, margin_y = 20.32, top_margin
        usable_w = page_w - 2 * margin_x - 10
        usable_h = page_h - margin_y - 40  # keep clear of the title block
        cursor_x, cursor_y, row_h = margin_x, margin_y, 0.0
        blocks: list[dict] = []
        for gname in order:
            members = groups.get(gname, [])
            if not members:
                continue
            sizes = {c["ref"]: sizes_all[c["ref"]] for c in members}
            big = [c for c in members if not c.get("at") and len(libs.symbol_pins(s._ensure_lib_symbol(c["symbol"]))) > 4]
            small = [c for c in members if not c.get("at") and c not in big]
            fixed = [c for c in members if c.get("at")]
            big_w = sum(sizes[c["ref"]][0] for c in big)
            big_h = max([sizes[c["ref"]][1] for c in big] + [0])
            small_w = max([sizes[c["ref"]][0] for c in small] + [0])
            small_h = max([sizes[c["ref"]][1] for c in small] + [0])
            n_small = len(small)
            cols = max(1, int(math.sqrt(n_small) + 0.999)) if n_small else 1
            below_h = big_h + math.ceil(n_small / cols) * small_h + 7.62
            side = big and n_small and below_h > usable_h
            if side:
                rows_fit = max(1, int(big_h // small_h)) if small_h else 1
                cols = max(1, math.ceil(n_small / rows_fit))
                block_w = big_w + cols * small_w + 5.08
                block_h = max(big_h, math.ceil(n_small / cols) * small_h) + 7.62
            else:
                block_w = max(big_w, cols * small_w) + 5.08
                block_h = below_h
            if cursor_x + block_w > margin_x + usable_w and cursor_x > margin_x:
                cursor_x = margin_x
                cursor_y += row_h + 7.62
                row_h = 0
            blocks.append({"name": gname, "bx": cursor_x, "by": cursor_y, "w": block_w, "h": block_h, "big": big,
                           "small": small, "fixed": fixed, "cols": cols, "side": side, "sizes": sizes,
                           "big_w": big_w, "big_h": big_h, "small_w": small_w, "small_h": small_h})
            cursor_x += block_w + 5.08
            row_h = max(row_h, block_h)
        bottom = max([b["by"] + b["h"] for b in blocks] + [0])
        return blocks, bottom - (margin_y + usable_h)

    paper = s.paper
    for paper_try in [paper] + [p for p in ("A3", "A2") if p != paper]:
        blocks, overflow = plan(paper_try)
        if overflow <= 0:
            break
    s.paper = paper_try

    placed: dict[str, sch.PlacedSymbol] = {}
    for blk in blocks:
        bx, by = blk["bx"], blk["by"]
        sizes = blk["sizes"]
        x = bx + 2.54
        for c in blk["big"]:
            w, h = sizes[c["ref"]]
            placed[c["ref"]] = _put(s, c, geom.snap_pt((x + w / 2, by + 5.08 + h / 2)))
            x += w
        if blk["side"]:
            gx, gy = bx + 2.54 + blk["big_w"] + 2.54, by + 5.08
        else:
            gx, gy = bx + 2.54, by + 5.08 + blk["big_h"] + (2.54 if blk["big"] else 0)
        cols = blk["cols"]
        for i, c in enumerate(blk["small"]):
            col, row = i % cols, i // cols
            w, h = blk["small_w"], blk["small_h"]
            placed[c["ref"]] = _put(s, c, geom.snap_pt((gx + col * w + w / 2, gy + row * h + h / 2)))
        for c in blk["fixed"]:
            placed[c["ref"]] = _put(s, c, tuple(c["at"]))
        if len(blocks) > 1 or spec.get("groups"):
            s.add_rect((geom.snap(bx - 1.27), geom.snap(by - 1.27)), (geom.snap(bx + blk["w"]), geom.snap(by + blk["h"])))
            s.add_text(titles.get(blk["name"], blk["name"]), (geom.snap(bx), geom.snap(by - 2.54)), size=2.0)
    return placed


def _is_gnd(net: str) -> bool:
    return net.upper().startswith(("GND", "VSS", "-"))


def _connect(s: sch.Schematic, placed: dict[str, sch.PlacedSymbol], spec: dict, power_nets: set[str],
             global_nets: set[str], hier_nets: set[str], flag_nets: set[str]) -> None:
    """Draw connectivity for the symbols on one sheet."""
    pin_net = _pin_map(spec)
    wired_pins: set[tuple[str, str]] = set()
    for a, b in spec.get("wires", []):
        if str(a[0]) in placed and str(b[0]) in placed:
            s.wire_pins(placed[str(a[0])], str(a[1]), placed[str(b[0])], str(b[1]))
            wired_pins.add((str(a[0]), str(a[1])))
            wired_pins.add((str(b[0]), str(b[1])))
    # power nets: power symbols; adjacent same-net pins on one side share a bus bar
    for net, pins in spec["nets"].items():
        if net not in power_nets:
            continue
        by_sym: dict[str, list[str]] = {}
        for ref, pin in pins:
            if str(ref) in placed:
                by_sym.setdefault(str(ref), []).append(str(pin))
        for ref, pnums in by_sym.items():
            sym = placed[ref]
            by_dir: dict[tuple[int, int], list[str]] = {}
            for pn in pnums:
                d = sym.pin_dir(pn)
                by_dir.setdefault((int(d[0]), int(d[1])), []).append(pn)
            for d, group in by_dir.items():
                pts = sorted(((sym.pin_pos(pn), pn) for pn in group), key=lambda t: (t[0][1], t[0][0]))
                stub = 3.81 if d[1] == 0 else 2.54
                if len(pts) == 1:
                    s.connect_power(sym, pts[0][1], net, stub=stub)
                    continue
                ends = [((p[0] + d[0] * stub), (p[1] + d[1] * stub)) for p, _ in pts]
                for (p, pn), e in zip(pts, ends):
                    s.add_wire(p, e)
                for a, b in zip(ends, ends[1:]):
                    s.add_wire(a, b)
                for e in ends[1:-1]:
                    s.add_junction(e)
                if d[1] == 0:
                    end = ends[-1] if _is_gnd(net) else ends[0]
                    tail = (end[0], end[1] + (2.54 if _is_gnd(net) else -2.54))
                    s.add_wire(end, tail)
                    s.add_junction(end)
                    s.add_power(net, tail, rot=0)
                else:
                    end = ends[0]
                    tail = (end[0], end[1] + d[1] * 2.54)
                    s.add_wire(end, tail)
                    s.add_junction(end)
                    rot = 0 if (d[1] > 0) == _is_gnd(net) else 180
                    s.add_power(net, tail, rot=rot)
    # PWR_FLAG on undriven power nets: a small "flag island" (power symbol +
    # PWR_FLAG) below the placed symbols, the usual KiCad convention. Power
    # symbols are global, so the island connects wherever it sits.
    if flag_nets and placed:
        bottom = max(sym.bbox()[3] for sym in placed.values())
        left = min(sym.bbox()[0] for sym in placed.values())
        y = geom.snap(bottom + 20.32)   # below the group frame
        x = geom.snap(left + 2.54)
        s.add_text("Power flags", (x, y - 6.35), size=1.27)
        for net in sorted(flag_nets):
            if not [1 for r, p in spec["nets"][net] if str(r) in placed]:
                continue
            s.add_power(net, (x, y), rot=0)
            s.add_wire((x, y), (x + 7.62, y))
            s.add_pwr_flag((x + 7.62, y), rot=0)
            x += 30.48
    # signal nets: labels on every pin not already wired explicitly
    for net, pins in spec["nets"].items():
        if net in power_nets:
            continue
        for ref, pin in pins:
            key = (str(ref), str(pin))
            if key in wired_pins or key[0] not in placed:
                continue
            sym = placed[key[0]]
            if net in global_nets:
                s.connect_label(sym, key[1], net, global_=True)
            elif net in hier_nets:
                pos = sym.pin_pos(key[1])
                d = sym.pin_dir(key[1])
                end = (round(pos[0] + d[0] * 2.54, 4), round(pos[1] + d[1] * 2.54, 4))
                s.add_wire(pos, end)
                s.add_hier_label(net, end, sch.Schematic._rot_for_dir(d), shape="passive")
            else:
                s.connect_label(sym, key[1], net)
    for ref, pin in spec.get("no_connect", []):
        if str(ref) in placed:
            s.connect_nc(placed[str(ref)], str(pin))
    nc_list = [list(map(str, x)) for x in spec.get("no_connect", [])]
    for ref in spec.get("unused_pins_nc", []):
        if str(ref) not in placed:
            continue
        sym = placed[str(ref)]
        for p in sym.visible_pins():
            if (str(ref), p.number) not in pin_net and [str(ref), p.number] not in nc_list:
                s.connect_nc(sym, p.number)


@dataclass
class SheetBuild:
    name: str            # "" for the root
    file: str
    schematic: sch.Schematic
    placed: dict[str, sch.PlacedSymbol]
    sheet_uuid: str | None = None


def build_schematic(spec: dict, project_dir: Path) -> tuple[list[SheetBuild], dict]:
    """Place and connect everything. Returns ([root, *subsheets], expected_nets)."""
    paper = spec.get("paper", "A4")
    power_nets = set(spec.get("power_nets", []))
    global_nets = set(spec.get("global_nets", []))
    pin_net = _pin_map(spec)
    comps = spec["components"]
    expected = {n: [(str(r), str(p)) for r, p in pins] for n, pins in spec["nets"].items()}

    # which sheet does each component live on?
    sheet_of_group: dict[str, str] = {}
    for sh in spec.get("sheets", []):
        for g in sh["groups"]:
            sheet_of_group[g] = sh["name"]
    comp_sheet = {c["ref"]: sheet_of_group.get(c.get("group", "main"), "") for c in comps}

    # nets spanning more than one sheet need hierarchical labels + sheet pins
    net_sheets: dict[str, set[str]] = {}
    for net, pins in spec["nets"].items():
        for ref, _ in pins:
            net_sheets.setdefault(net, set()).add(comp_sheet[str(ref)])
    hier_nets = {n for n, shs in net_sheets.items() if len(shs) > 1 and n not in power_nets and n not in global_nets}

    # power nets with no power_out driver get a PWR_FLAG on the first sheet that has a pin
    flag_by_sheet: dict[str, set[str]] = {}
    for net in power_nets:
        pins = spec["nets"].get(net, [])
        driven = False
        for ref, pin in pins:
            c = next((x for x in comps if x["ref"] == str(ref)), None)
            if not c:
                continue
            node = libs.resolve_symbol(c["symbol"], project_dir)
            for p in libs.symbol_pins(node):
                if p.number == str(pin) and p.etype == "power_out":
                    driven = True
        if not driven and pins:
            flag_by_sheet.setdefault(comp_sheet[str(pins[0][0])], set()).add(net)

    root = sch.Schematic(spec["project"], title=spec.get("title", spec["project"]), paper=paper,
                         rev=spec.get("rev", ""), company=spec.get("company", ""), project_dir=project_dir)
    builds: list[SheetBuild] = []
    sheets_spec = spec.get("sheets", [])

    # ---- sub-sheets -------------------------------------------------------------
    sheet_uuids: dict[str, str] = {sh["name"]: sch.new_uuid() for sh in sheets_spec}
    for sh in sheets_spec:
        sub = sch.Schematic(spec["project"], title=f"{spec.get('title', spec['project'])} - {sh['name']}", paper=paper,
                            rev=spec.get("rev", ""), company=spec.get("company", ""), project_dir=project_dir,
                            sheet_path=f"/{root.uuid}/{sheet_uuids[sh['name']]}")
        sub.lib_symbols = root.lib_symbols  # share the cache; each file embeds what it uses
        members = [c for c in comps if comp_sheet[c["ref"]] == sh["name"]]
        placed = _layout(sub, members, spec, pin_net, power_nets)
        _connect(sub, placed, spec, power_nets, global_nets, hier_nets, flag_by_sheet.get(sh["name"], set()))
        builds.append(SheetBuild(sh["name"], sh["file"], sub, placed, sheet_uuids[sh["name"]]))

    # ---- root: sheet symbols in a row, then any root-level components ------------
    root_members = [c for c in comps if comp_sheet[c["ref"]] == ""]
    sheet_row_h = 0.0
    if sheets_spec:
        x = 25.4
        y = 25.4
        for sb in builds:
            sh = next(s_ for s_ in sheets_spec if s_["name"] == sb.name)
            # nets on this sheet that cross to other sheets -> sheet pins (inputs left, outputs right by name only)
            crossing = sorted(n for n in hier_nets if sb.name in net_sheets[n])
            left = crossing[: (len(crossing) + 1) // 2]
            right = crossing[(len(crossing) + 1) // 2:]
            w = max(30.48, geom.snap(max([_label_width(n) for n in crossing] + [0]) * 2 + 7.62))
            h = geom.snap((max(len(left), len(right)) + 1) * 2.54 + 2.54)
            pins = [(n, "passive", "left") for n in left] + [(n, "passive", "right") for n in right]
            uid = root.add_sheet(sb.name, sb.file, (x, y), (w, h), pins, sheet_uuid=sb.sheet_uuid,
                                 page=str(builds.index(sb) + 2))
            for n in crossing:
                px, py, rot = root.sheet_pin_pos(uid, n)
                d = (-1, 0) if n in left else (1, 0)
                end = (round(px + d[0] * 2.54, 4), py)
                root.add_wire((px, py), end)
                root.add_label(n, end, 180 if d[0] < 0 else 0)
            x += w + max([_label_width(n) for n in crossing] + [0]) * 2 + 12.7
            sheet_row_h = max(sheet_row_h, h)
            page_w = PAPER_SIZES.get(root.paper, (297, 210))[0]
            if x > page_w - 40:
                x = 25.4
                y += sheet_row_h + 12.7
                sheet_row_h = 0
        top = y + sheet_row_h + 15.24
    else:
        top = 22.86
    placed_root = _layout(root, root_members, spec, pin_net, power_nets, top_margin=top) if root_members else {}
    _connect(root, placed_root, spec, power_nets, global_nets, hier_nets, flag_by_sheet.get("", set()))
    builds.insert(0, SheetBuild("", f"{spec['project']}.kicad_sch", root, placed_root))
    return builds, expected


# --------------------------------------------------------------------------- #
# Board
# --------------------------------------------------------------------------- #
def build_board(spec: dict, builds: list[SheetBuild], project_dir: Path) -> pcb.Board:
    bspec = spec.get("board", {})
    layers = int(bspec.get("layers", 2))
    b = pcb.Board(copper_layers=layers, thickness=float(bspec.get("thickness", 1.6)),
                  title=spec.get("title", spec["project"]), rev=spec.get("rev", ""), project_dir=project_dir,
                  mask_color=bspec.get("mask_color", "Green"), silk_color=bspec.get("silk_color", "White"))
    w = float(bspec.get("width", 50))
    h = float(bspec.get("height", 40))
    ox, oy = bspec.get("origin", [50, 50])
    if bspec.get("outline_polygon"):
        b.outline_polygon([(ox + p[0], oy + p[1]) for p in bspec["outline_polygon"]])
    else:
        b.outline_rect(ox, oy, w, h, radius=float(bspec.get("corner_radius", 0)))
    b.aux_origin = (ox, oy + h)
    pin_net = _pin_map(spec)
    placement = dict(bspec.get("placement", {}))
    hints = bspec.get("hints") or {}
    gap = float(bspec.get("placement_gap", 2.0))  # leaves room for reference silkscreen
    edge = float(bspec.get("edge_clearance", 1.5))

    # where does each symbol live (for the footprint's schematic path)?
    where: dict[str, tuple[sch.PlacedSymbol, str, str, str]] = {}
    for sb in builds:
        for ref, sym in sb.placed.items():
            sheetname = "/" if sb.name == "" else f"/{sb.name}/"
            where[ref] = (sym, sb.schematic.sheet_path, sheetname, sb.file)

    mh = bspec.get("mounting_holes")
    if mh:
        inset = float(mh.get("inset", 3.5))
        fpid = mh.get("footprint", "MountingHole:MountingHole_3.2mm_M3")
        for i, (hx, hy) in enumerate([(ox + inset, oy + inset), (ox + w - inset, oy + inset),
                                      (ox + inset, oy + h - inset), (ox + w - inset, oy + h - inset)][: int(mh.get("count", 4))]):
            b.mounting_hole(f"H{i+1}", (hx, hy), fpid)

    comps = [c for c in spec["components"] if c.get("footprint")]
    by_ref = {c["ref"]: c for c in comps}

    def place(c: dict, at: tuple[float, float], rot: float, layer: str) -> pcb.PlacedFootprint:
        ref = c["ref"]
        sym, path, sheetname, sheetfile = where.get(ref, (None, None, "/", ""))
        nets = {p.number: pin_net.get((ref, p.number)) for p in (sym.pins if sym else [])}
        nets = {k: v for k, v in nets.items() if v}
        return b.add_footprint(c["footprint"], ref, c["value"], at, float(rot), layer, pad_nets=nets,
                               sch_path=f"{path}/{sym.uuid}" if sym else None, sheetname=sheetname, sheetfile=sheetfile,
                               dnp=bool(c.get("dnp", False)), props={k: v for k, v in (c.get("props") or {}).items()})

    # measure every footprint (bbox at its hinted rotation)
    sizes: dict[str, tuple[float, float, float, float]] = {}
    for c in comps:
        rot = float(hints.get(c["ref"], {}).get("rot", 0))
        node = libs.load_footprint(c["footprint"], project_dir)
        tmp = pcb.Board()
        f = tmp.add_footprint(c["footprint"], c["ref"], c["value"], (0, 0), rot, "F.Cu", fp_node=node)
        x0, y0, x1, y1 = f.bbox()
        sizes[c["ref"]] = (x1 - x0, y1 - y0, -x0, -y0)  # width, height, origin offset from bbox corner

    obstacles: list[tuple[float, float, float, float]] = [f.bbox() for f in b.footprints.values()]

    def overlaps(box: tuple[float, float, float, float], g: float) -> bool:
        for o in obstacles:
            if box[0] < o[2] + g and box[2] > o[0] - g and box[1] < o[3] + g and box[3] > o[1] - g:
                return True
        return False

    # 1) explicit placements
    for ref, (px, py, prot, playr) in placement.items():
        if ref in by_ref:
            f = place(by_ref[ref], (ox + float(px), oy + float(py)), prot, playr)
            obstacles.append(f.bbox())
    done = set(placement)

    # 2) hints: edges and center
    edge_groups: dict[str, list[str]] = {}
    for ref, hint in hints.items():
        if ref in done or ref not in by_ref:
            continue
        if hint.get("edge") in ("left", "right", "top", "bottom"):
            edge_groups.setdefault(hint["edge"], []).append(ref)
        elif hint.get("center"):
            fw, fh, offx, offy = sizes[ref]
            cx, cy = ox + w / 2 - fw / 2, oy + h / 2 - fh / 2
            f = place(by_ref[ref], (round(cx + offx, 2), round(cy + offy, 2)), float(hint.get("rot", 0)), hint.get("layer", "F.Cu"))
            obstacles.append(f.bbox())
            done.add(ref)
    for side, refs in edge_groups.items():
        n = len(refs)
        for i, ref in enumerate(refs):
            fw, fh, offx, offy = sizes[ref]
            hint = hints[ref]
            if side in ("left", "right"):
                cy = oy + h * (i + 1) / (n + 1) - fh / 2
                cx = ox + edge if side == "left" else ox + w - edge - fw
            else:
                cx = ox + w * (i + 1) / (n + 1) - fw / 2
                cy = oy + edge if side == "top" else oy + h - edge - fh
            # nudge inward until clear of obstacles
            box = (cx, cy, cx + fw, cy + fh)
            for _ in range(60):
                if not overlaps(box, gap):
                    break
                if side in ("left", "right"):
                    cy += 1.0 if i % 2 == 0 else -1.0
                else:
                    cx += 1.0 if i % 2 == 0 else -1.0
                box = (cx, cy, cx + fw, cy + fh)
            f = place(by_ref[ref], (round(cx + offx, 2), round(cy + offy, 2)), float(hint.get("rot", 0)), hint.get("layer", "F.Cu"))
            obstacles.append(f.bbox())
            done.add(ref)

    # 3) "near" hints: spiral search around the target
    for ref, hint in hints.items():
        if ref in done or ref not in by_ref or not hint.get("near"):
            continue
        target = b.footprints.get(hint["near"])
        if target is None:
            b.notes.append(f"{ref}: 'near {hint['near']}' ignored because {hint['near']} was not placed before it")
            continue
        tx0, ty0, tx1, ty1 = target.bbox()
        tcx, tcy = (tx0 + tx1) / 2, (ty0 + ty1) / 2
        fw, fh, offx, offy = sizes[ref]
        best = None
        for r in [x * 0.5 for x in range(1, 80)]:
            for k in range(16):
                ang = 2 * math.pi * k / 16
                cx, cy = tcx + r * math.cos(ang) - fw / 2, tcy + r * math.sin(ang) - fh / 2
                box = (cx, cy, cx + fw, cy + fh)
                if box[0] < ox + edge or box[1] < oy + edge or box[2] > ox + w - edge or box[3] > oy + h - edge:
                    continue
                if not overlaps(box, min(gap, 1.0)):
                    best = (cx, cy)
                    break
            if best:
                break
        if best is None:
            b.notes.append(f"{ref}: no free spot near {hint['near']}; packed with the rest")
            continue
        f = place(by_ref[ref], (round(best[0] + offx, 2), round(best[1] + offy, 2)), float(hint.get("rot", 0)), hint.get("layer", "F.Cu"))
        obstacles.append(f.bbox())
        done.add(ref)

    # 4) shelf-pack the rest by group
    todo = [c for c in comps if c["ref"] not in done]
    group_order = [g["name"] for g in spec.get("groups", [])]
    todo.sort(key=lambda c: (group_order.index(c.get("group", "main")) if c.get("group", "main") in group_order else 99,
                             -sizes[c["ref"]][1]))
    fixed_obstacles = list(obstacles)

    def pack(g: float) -> dict[str, tuple[float, float]] | None:
        obs = list(fixed_obstacles)

        def ov(box):
            for o in obs:
                if box[0] < o[2] + g and box[2] > o[0] - g and box[1] < o[3] + g and box[3] > o[1] - g:
                    return True
            return False

        out: dict[str, tuple[float, float]] = {}
        cx, cy, row_h = ox + edge, oy + edge, 0.0
        for c in todo:
            fw, fh, offx, offy = sizes[c["ref"]]
            ok = False
            for _ in range(600):
                if cx + fw > ox + w - edge:
                    cx = ox + edge
                    cy += row_h + g
                    row_h = 0
                if cy + fh > oy + h - edge:
                    break
                box = (cx, cy, cx + fw, cy + fh)
                if ov(box):
                    cx += 0.5
                    continue
                out[c["ref"]] = (round(cx + offx, 2), round(cy + offy, 2))
                obs.append(box)
                cx += fw + g
                row_h = max(row_h, fh)
                ok = True
                break
            if not ok:
                return None
        return out

    result = None
    used_gap = gap
    for g in (gap, gap * 0.5, 0.5):
        result = pack(g)
        if result is not None:
            used_gap = g
            break
    if result is None:
        result = {}
        px = ox + w + 5
        for c in todo:
            fw, fh, offx, offy = sizes[c["ref"]]
            result[c["ref"]] = (round(px + offx, 2), round(oy + offy, 2))
            px += fw + 1
            b.notes.append(f"{c['ref']}: no room inside the {w}x{h} mm outline; parked outside it - enlarge the board or place manually")
    elif used_gap != gap and todo:
        b.notes.append(f"placement gap reduced to {used_gap} mm to fit the {w}x{h} mm outline; consider a larger board")
    for c in todo:
        place(c, result[c["ref"]], float(hints.get(c["ref"], {}).get("rot", 0)), "F.Cu")

    for ref, f in b.footprints.items():
        x0, y0, x1, y1 = f.bbox()
        if x0 < ox or y0 < oy or x1 > ox + w or y1 > oy + h:
            b.notes.append(f"{ref}: courtyard extends beyond the board outline (bbox {x0:.1f},{y0:.1f}-{x1:.1f},{y1:.1f})")
    for z in bspec.get("zones", []):
        pts = [(ox, oy), (ox + w, oy), (ox + w, oy + h), (ox, oy + h)]
        if bspec.get("outline_polygon"):
            pts = [(ox + p[0], oy + p[1]) for p in bspec["outline_polygon"]]
        b.zone(z["net"], z.get("layer", "B.Cu"), pts, priority=int(z.get("priority", 0)),
               clearance=float(z.get("clearance", 0.3)), connect=z.get("connect", "thermal"))
    for t in bspec.get("texts", []):
        b.gr_text(t["text"], (ox + t["at"][0], oy + t["at"][1]), t.get("layer", "F.SilkS"), float(t.get("size", 1.0)))
    return b


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def build(spec: dict, project_dir: str | Path, with_board: bool = True, render: bool = True) -> BuildResult:
    global project_dir_hint
    project_dir = Path(project_dir)
    project_dir.mkdir(parents=True, exist_ok=True)
    name = spec["project"]
    lib_spec = spec.get("libs", {})
    if lib_spec.get("symbols"):
        project.write_lib_table(project_dir, "sym", [(l["name"], l["uri"], l.get("descr", "")) for l in lib_spec["symbols"]])
    if lib_spec.get("footprints"):
        project.write_lib_table(project_dir, "fp", [(l["name"], l["uri"], l.get("descr", "")) for l in lib_spec["footprints"]])
    libs._load_symbol_file.cache_clear()
    project_dir_hint = project_dir
    problems = validate_spec(spec)
    if problems:
        raise ValueError("spec problems:\n  " + "\n  ".join(problems))
    builds, expected = build_schematic(spec, project_dir)
    root = builds[0]
    sch_path = root.schematic.save(project_dir / root.file)
    sheet_paths = [sb.schematic.save(project_dir / sb.file) for sb in builds[1:]]
    pro_path = project.write_pro(project_dir, name, root_sheet_uuid=root.schematic.uuid,
                                 board_design_settings=spec.get("board", {}).get("design_settings"),
                                 fab=spec.get("board", {}).get("fab", "generic"))
    nl = check.netlist(sch_path)
    ncheck = check.compare_nets(expected, nl["nets"])
    erc = check.erc(sch_path)
    notes: list[str] = []
    pcb_path = None
    drc = None
    if with_board:
        b = build_board(spec, builds, project_dir)
        pcb_path = b.save(project_dir / f"{name}.kicad_pcb")
        drc = check.drc(pcb_path, schematic_parity=True)
        notes += b.notes
    out = project_dir / "kcs-out"
    out.mkdir(exist_ok=True)
    if render:
        try:
            check.export_pdf(sch_path, out / f"{name}-schematic.pdf")
            notes.append(f"schematic PDF: {out / (name + '-schematic.pdf')}")
            if pcb_path:
                check.render_board(pcb_path, out / f"{name}-top.png", "top")
                check.render_board(pcb_path, out / f"{name}-bottom.png", "bottom")
                notes.append(f"board renders: {out / (name + '-top.png')}, {out / (name + '-bottom.png')}")
        except Exception as exc:  # pragma: no cover
            notes.append(f"render failed: {exc}")
    (out / "netlist.json").write_text(json.dumps(nl, indent=1), encoding="utf-8")
    return BuildResult(project_dir, sch_path, pcb_path, pro_path, ncheck, erc, drc, notes, sheet_paths)
