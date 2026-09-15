"""Run kicad-cli ERC/DRC/netlist and turn the results into plain Python."""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from . import env as kenv
from . import sexpr


def _tmp(suffix: str) -> Path:
    fd = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    fd.close()
    return Path(fd.name)


def erc(sch_path: Path, severity: str = "all") -> dict:
    out = _tmp(".json")
    args = ["sch", "erc", "--format", "json", "--units", "mm", "-o", str(out)]
    args.append({"all": "--severity-all", "error": "--severity-error", "warning": "--severity-warning"}[severity])
    args.append(str(sch_path))
    res = kenv.run_cli(*args)
    data = {"ok": res.returncode == 0, "stdout": res.stdout, "stderr": res.stderr, "violations": []}
    if out.exists() and out.stat().st_size:
        raw = json.loads(out.read_text(encoding="utf-8"))
        data["raw"] = raw
        for sheet in raw.get("sheets", []):
            for v in sheet.get("violations", []):
                data["violations"].append({
                    "sheet": sheet.get("path", "/"), "type": v.get("type"), "severity": v.get("severity"),
                    "description": v.get("description"),
                    "items": [{"description": i.get("description"), "pos": i.get("pos"), "uuid": i.get("uuid")}
                              for i in v.get("items", [])],
                })
        out.unlink(missing_ok=True)
    return data


def drc(pcb_path: Path, severity: str = "all", schematic_parity: bool = False) -> dict:
    out = _tmp(".json")
    args = ["pcb", "drc", "--format", "json", "--units", "mm", "-o", str(out)]
    args.append({"all": "--severity-all", "error": "--severity-error", "warning": "--severity-warning"}[severity])
    if schematic_parity:
        args.append("--schematic-parity")
    args.append(str(pcb_path))
    res = kenv.run_cli(*args)
    data = {"ok": res.returncode == 0, "stdout": res.stdout, "stderr": res.stderr,
            "violations": [], "unconnected": [], "schematic_parity": []}
    if out.exists() and out.stat().st_size:
        raw = json.loads(out.read_text(encoding="utf-8"))
        data["raw"] = raw
        for key in ("violations", "unconnected_items", "schematic_parity"):
            for v in raw.get(key, []):
                data[{"violations": "violations", "unconnected_items": "unconnected",
                      "schematic_parity": "schematic_parity"}[key]].append({
                    "type": v.get("type"), "severity": v.get("severity"), "description": v.get("description"),
                    "items": [{"description": i.get("description"), "pos": i.get("pos")} for i in v.get("items", [])],
                })
        out.unlink(missing_ok=True)
    return data


def netlist(sch_path: Path) -> dict:
    """Export the KiCad s-expression netlist and return {net_name: [(ref, pin), ...]}
    plus a components map {ref: {value, footprint, lib_id}}."""
    out = _tmp(".net")
    res = kenv.run_cli("sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(sch_path))
    if res.returncode != 0 or not out.exists():
        raise RuntimeError(f"netlist export failed: {res.stdout}\n{res.stderr}")
    tree = sexpr.load(out)
    out.unlink(missing_ok=True)
    nets: dict[str, list[tuple[str, str]]] = {}
    for net in sexpr.find_all(sexpr.child(tree, "nets") or [], "net"):
        name = str(sexpr.child(net, "name")[1])
        nodes = []
        for node in sexpr.children(net, "node"):
            ref = str(sexpr.child(node, "ref")[1])
            pin = str(sexpr.child(node, "pin")[1])
            nodes.append((ref, pin))
        nets[name] = sorted(nodes)
    comps: dict[str, dict] = {}
    for comp in sexpr.children(sexpr.child(tree, "components") or [], "comp"):
        ref = str(sexpr.child(comp, "ref")[1])
        ls = sexpr.child(comp, "libsource")
        lib = str(sexpr.child(ls, "lib")[1]) if ls else ""
        part = str(sexpr.child(ls, "part")[1]) if ls else ""
        comps[ref] = {
            "value": str((sexpr.child(comp, "value") or ["", ""])[1]),
            "footprint": str((sexpr.child(comp, "footprint") or ["", ""])[1]),
            "lib_id": f"{lib}:{part}",
        }
    return {"nets": nets, "components": comps}


def compare_nets(expected: dict[str, list[tuple[str, str]]], actual: dict[str, list[tuple[str, str]]]) -> dict:
    """Compare intended connectivity with the exported netlist.

    Net *names* only have to match for named nets; the check is on pin groups:
    every expected group must appear as (a subset of) exactly one actual net,
    and no actual net may merge two expected groups.
    """
    problems: list[str] = []
    pin_to_actual: dict[tuple[str, str], str] = {}
    for name, nodes in actual.items():
        if name.startswith("unconnected-"):
            continue
        for n in nodes:
            pin_to_actual[tuple(n)] = name

    def _auto(n: str) -> bool:
        return n.startswith("Net-") or n.startswith("unconnected-")

    for name, nodes in expected.items():
        nodes = [tuple(n) for n in nodes]
        found = {pin_to_actual.get(n, "<unconnected>") for n in nodes}
        if len(found) > 1:
            problems.append(f"net {name!r} is split across actual nets {sorted(found)}: pins {nodes}")
        elif found == {"<unconnected>"}:
            problems.append(f"net {name!r}: none of its pins {nodes} are connected")
        else:
            act = next(iter(found))
            # a user-named net must come out under that name (allowing the
            # hierarchical "/name" and "/sheet/name" forms)
            if not _auto(act) and act.lstrip("/").split("/")[-1] != name and act != name:
                problems.append(f"net {name!r}: pins {nodes} ended up on net {act!r}")
    # merges: two expected nets on one actual net
    actual_to_expected: dict[str, set[str]] = {}
    for name, nodes in expected.items():
        for n in nodes:
            a = pin_to_actual.get(tuple(n))
            if a:
                actual_to_expected.setdefault(a, set()).add(name)
    for a, names in actual_to_expected.items():
        if len(names) > 1:
            problems.append(f"actual net {a!r} shorts expected nets {sorted(names)}")
    expected_pins = {tuple(n) for nodes in expected.values() for n in nodes}
    extra = [(n, a) for n, a in pin_to_actual.items() if n not in expected_pins and not a.startswith("unconnected-")]
    return {"ok": not problems, "problems": problems, "pins_not_in_spec": extra}


def export_pdf(sch_path: Path, out: Path) -> Path:
    res = kenv.run_cli("sch", "export", "pdf", "-o", str(out), str(sch_path))
    if res.returncode != 0:
        raise RuntimeError(res.stdout + res.stderr)
    return out


def export_svg(sch_path: Path, out_dir: Path) -> list[Path]:
    res = kenv.run_cli("sch", "export", "svg", "-o", str(out_dir), str(sch_path))
    if res.returncode != 0:
        raise RuntimeError(res.stdout + res.stderr)
    return sorted(Path(out_dir).glob("*.svg"))


def render_board(pcb_path: Path, out: Path, side: str = "top", width: int = 1600, height: int = 1200,
                 zoom: float = 1.0, background: str = "opaque") -> Path:
    res = kenv.run_cli("pcb", "render", "-o", str(out), "--width", str(width), "--height", str(height),
                       "--side", side, "--zoom", str(zoom), "--background", background, str(pcb_path))
    if res.returncode != 0:
        raise RuntimeError(res.stdout + res.stderr)
    return out
