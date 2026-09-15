"""Manufacturing exports through kicad-cli with per-fab presets."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from . import env as kenv

FAB_PRESETS: dict[str, dict] = {
    "jlcpcb": {
        "gerber_layers": "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
        "gerber_args": ["--subtract-soldermask", "--no-x2", "--use-drill-file-origin"],
        "drill_args": ["--format", "excellon", "--excellon-units", "mm", "--excellon-zeros-format", "decimal",
                       "--drill-origin", "plot", "--generate-map", "--map-format", "gerberx2", "--excellon-separate-th"],
        "pos_args": ["--format", "csv", "--units", "mm", "--side", "both", "--use-drill-file-origin", "--exclude-dnp"],
        "bom_fields": "Reference,Value,Footprint,LCSC,${QUANTITY}",
        "bom_labels": "Designator,Comment,Footprint,LCSC Part #,Qty",
        "bom_group": "Value,Footprint,LCSC",
        "pos_columns": {"Ref": "Designator", "PosX": "Mid X", "PosY": "Mid Y", "Rot": "Rotation", "Side": "Layer"},
        "notes": "JLCPCB: rotation offsets differ from KiCad for some packages; check the assembly preview. "
                 "Gerber layers named with ProtelExt (.GTL etc.) are fine. Add LCSC part numbers as a 'LCSC' field.",
    },
    "pcbway": {
        "gerber_layers": "F.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
        "gerber_args": ["--subtract-soldermask", "--use-drill-file-origin"],
        "drill_args": ["--format", "excellon", "--excellon-units", "mm", "--excellon-zeros-format", "decimal",
                       "--drill-origin", "plot", "--generate-map", "--map-format", "gerberx2"],
        "pos_args": ["--format", "csv", "--units", "mm", "--side", "both", "--use-drill-file-origin", "--exclude-dnp"],
        "bom_fields": "Reference,Value,Footprint,MPN,Manufacturer,${QUANTITY}",
        "bom_labels": "Designator,Value,Footprint,MPN,Manufacturer,Qty",
        "bom_group": "Value,Footprint,MPN",
        "pos_columns": None,
        "notes": "PCBWay accepts KiCad gerbers directly; include the drill map.",
    },
    "oshpark": {
        "gerber_layers": "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts",
        "gerber_args": ["--use-drill-file-origin"],
        "drill_args": ["--format", "excellon", "--excellon-units", "in", "--excellon-zeros-format", "decimal",
                       "--drill-origin", "plot"],
        "pos_args": ["--format", "csv", "--units", "mm", "--side", "both"],
        "bom_fields": "Reference,Value,Footprint,${QUANTITY}",
        "bom_labels": "Reference,Value,Footprint,Qty",
        "bom_group": "Value,Footprint",
        "pos_columns": None,
        "notes": "OSH Park also accepts the .kicad_pcb file directly (simplest).",
    },
    "generic": {
        "gerber_layers": "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts,F.Fab,B.Fab",
        "gerber_args": ["--subtract-soldermask", "--use-drill-file-origin"],
        "drill_args": ["--format", "excellon", "--excellon-units", "mm", "--excellon-zeros-format", "decimal",
                       "--drill-origin", "plot", "--generate-map", "--map-format", "pdf"],
        "pos_args": ["--format", "csv", "--units", "mm", "--side", "both", "--use-drill-file-origin", "--exclude-dnp"],
        "bom_fields": "Reference,Value,Footprint,MPN,Manufacturer,Datasheet,${QUANTITY}",
        "bom_labels": "Reference,Value,Footprint,MPN,Manufacturer,Datasheet,Qty",
        "bom_group": "Value,Footprint,MPN",
        "pos_columns": None,
        "notes": "",
    },
}


def _run(args: list[str]) -> str:
    res = kenv.run_cli(*args)
    if res.returncode not in (0, 2):  # 2 = warnings (e.g. missing 3D models on STEP)
        raise RuntimeError(f"kicad-cli {' '.join(args[:3])} failed ({res.returncode}):\n{res.stdout}\n{res.stderr}")
    return res.stdout + res.stderr


def fab_package(pcb_path: Path, sch_path: Path | None, out_dir: Path, fab: str = "generic",
                copper_layers: int = 2) -> dict:
    preset = FAB_PRESETS[fab]
    out_dir = Path(out_dir)
    gerb = out_dir / "gerbers"
    gerb.mkdir(parents=True, exist_ok=True)
    layers = preset["gerber_layers"]
    if copper_layers == 2:
        layers = ",".join(l for l in layers.split(",") if not l.startswith("In"))
    else:
        inner = ",".join(f"In{i+1}.Cu" for i in range(copper_layers - 2))
        layers = ",".join(l for l in layers.split(",") if not l.startswith("In"))
        layers = layers.replace("F.Cu,", f"F.Cu,{inner},")
    log = {}
    log["gerbers"] = _run(["pcb", "export", "gerbers", "-o", str(gerb) + "/", "--layers", layers, *preset["gerber_args"], str(pcb_path)])
    log["drill"] = _run(["pcb", "export", "drill", "-o", str(gerb) + "/", *preset["drill_args"], str(pcb_path)])
    pos = out_dir / f"{pcb_path.stem}-pos.csv"
    log["pos"] = _run(["pcb", "export", "pos", "-o", str(pos), *preset["pos_args"], str(pcb_path)])
    if preset.get("pos_columns"):
        _rewrite_pos(pos, preset["pos_columns"], fab)
    if sch_path:
        bom = out_dir / f"{pcb_path.stem}-bom.csv"
        log["bom"] = _run(["sch", "export", "bom", "-o", str(bom), "--fields", preset["bom_fields"],
                           "--labels", preset["bom_labels"], "--group-by", preset["bom_group"], "--exclude-dnp",
                           str(sch_path)])
    log["notes"] = preset["notes"]
    # archive the gerbers for upload
    import shutil
    zip_path = out_dir / f"{pcb_path.stem}-{fab}-gerbers"
    shutil.make_archive(str(zip_path), "zip", gerb)
    log["zip"] = str(zip_path) + ".zip"
    return log


def _rewrite_pos(pos: Path, columns: dict[str, str], fab: str) -> None:
    text = pos.read_text(encoding="utf-8")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return
    out = io.StringIO()
    fields = [columns.get(k, k) for k in rows[0].keys()]
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader()
    for r in rows:
        row = {columns.get(k, k): v for k, v in r.items()}
        if fab == "jlcpcb":
            row["Layer"] = {"top": "Top", "bottom": "Bottom"}.get(row.get("Layer", "").lower(), row.get("Layer"))
        w.writerow(row)
    pos.write_text(out.getvalue(), encoding="utf-8")


def step(pcb_path: Path, out: Path) -> str:
    return _run(["pcb", "export", "step", "-o", str(out), "--subst-models", "--include-tracks", "--include-zones", str(pcb_path)])


def pcb_pdf(pcb_path: Path, out: Path, layers: str = "F.Cu,B.Cu,F.SilkS,B.SilkS,Edge.Cuts,F.Fab") -> str:
    return _run(["pcb", "export", "pdf", "-o", str(out), "--layers", layers, "--mode-multipage",
                 "--include-border-title", str(pcb_path)])


def sch_pdf(sch_path: Path, out: Path) -> str:
    return _run(["sch", "export", "pdf", "-o", str(out), str(sch_path)])


def stats(pcb_path: Path) -> str:
    return _run(["pcb", "export", "stats", "--format", "json", "-o", str(Path(pcb_path).with_suffix(".stats.json")), str(pcb_path)])
