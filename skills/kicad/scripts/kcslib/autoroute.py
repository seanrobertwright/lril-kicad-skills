"""Optional autorouting through Freerouting (Java) using KiCad's Specctra
DSN/SES bridge, driven by KiCad's bundled pcbnew Python.

Flow: board -> DSN (pcbnew SWIG) -> freerouting.jar -> SES -> board (SWIG).
The result is a *starting point*: review every trace, re-run DRC, and expect
to hand-tune power, RF and high-speed nets.
"""
from __future__ import annotations

import shutil
import subprocess
import urllib.request
from pathlib import Path

from . import env as kenv

FREEROUTING_API = "https://api.github.com/repos/freerouting/freerouting/releases/latest"


def _latest_jar_url() -> str:
    import json

    with urllib.request.urlopen(FREEROUTING_API, timeout=30) as resp:  # noqa: S310 - fixed https URL
        data = json.load(resp)
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".jar"):
            return asset["browser_download_url"]
    raise RuntimeError("no .jar asset in the latest Freerouting release")


def jar_path() -> Path:
    e = kenv.get()
    base = (e.user_docs or Path.home()) / "3rdparty" / "freerouting"
    base.mkdir(parents=True, exist_ok=True)
    return base / "freerouting.jar"


def ensure_jar(download: bool = True) -> Path:
    p = jar_path()
    if p.is_file():
        return p
    if not download:
        raise FileNotFoundError(f"freerouting.jar not found at {p}")
    url = _latest_jar_url()
    print(f"downloading Freerouting from {url} to {p} ...")
    urllib.request.urlretrieve(url, p)  # noqa: S310 - https URL from the GitHub API
    return p


def _swig(script: str) -> str:
    e = kenv.get()
    if not e.python:
        raise RuntimeError("KiCad's bundled python (with pcbnew) not found")
    res = subprocess.run([str(e.python), "-c", script], capture_output=True, text=True, timeout=600)
    if res.returncode != 0:
        raise RuntimeError(res.stdout + res.stderr)
    return res.stdout


def export_dsn(pcb_path: Path, dsn: Path) -> None:
    _swig(f"import pcbnew; b=pcbnew.LoadBoard(r'{pcb_path}'); assert pcbnew.ExportSpecctraDSN(b, r'{dsn}')")


def import_ses(pcb_path: Path, ses: Path, out: Path) -> None:
    _swig(f"import pcbnew; b=pcbnew.LoadBoard(r'{pcb_path}'); assert pcbnew.ImportSpecctraSES(b, r'{ses}'); "
          f"pcbnew.SaveBoard(r'{out}', b)")


def fill_zones(pcb_path: Path, out: Path | None = None) -> None:
    out = out or pcb_path
    _swig(f"import pcbnew; b=pcbnew.LoadBoard(r'{pcb_path}'); f=pcbnew.ZONE_FILLER(b); f.Fill(b.Zones()); "
          f"pcbnew.SaveBoard(r'{out}', b)")


def autoroute(pcb_path: Path, out: Path | None = None, passes: int = 100, timeout_s: int = 900) -> Path:
    if not shutil.which("java"):
        raise RuntimeError("Java is required for Freerouting (java not on PATH)")
    pcb_path = Path(pcb_path)
    out = Path(out) if out else pcb_path.with_name(pcb_path.stem + "-routed.kicad_pcb")
    work = pcb_path.parent / "kcs-out"
    work.mkdir(exist_ok=True)
    dsn = work / (pcb_path.stem + ".dsn")
    ses = work / (pcb_path.stem + ".ses")
    export_dsn(pcb_path, dsn)
    jar = ensure_jar()
    res = subprocess.run(["java", "-jar", str(jar), "-de", str(dsn), "-do", str(ses), "-mp", str(passes),
                          "-dr", "-oit", "1"], capture_output=True, text=True, timeout=timeout_s)
    if not ses.is_file():
        raise RuntimeError("Freerouting produced no .ses file:\n" + res.stdout[-2000:] + res.stderr[-2000:])
    import_ses(pcb_path, ses, out)
    fill_zones(out)
    return out
