"""Locate the KiCad 10 installation, its bundled tools and library paths.

Everything here is discovery only. Nothing is written.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

KICAD_MAJOR = "10"


@dataclass
class KicadEnv:
    root: Path | None = None            # e.g. C:/Program Files/KiCad/10.0
    cli: Path | None = None             # kicad-cli executable
    python: Path | None = None          # KiCad's bundled python (has pcbnew SWIG)
    share: Path | None = None           # <root>/share/kicad
    symbol_dir: Path | None = None
    footprint_dir: Path | None = None
    model3d_dir: Path | None = None
    template_dir: Path | None = None
    user_config: Path | None = None     # ~/AppData/Roaming/kicad/10.0
    user_docs: Path | None = None       # ~/Documents/KiCad/10.0
    version: str | None = None
    problems: list[str] = field(default_factory=list)

    def env_vars(self) -> dict[str, str]:
        """Values for ${KICAD10_*} expansion in lib tables."""
        out: dict[str, str] = {}
        if self.symbol_dir:
            out[f"KICAD{KICAD_MAJOR}_SYMBOL_DIR"] = str(self.symbol_dir)
        if self.footprint_dir:
            out[f"KICAD{KICAD_MAJOR}_FOOTPRINT_DIR"] = str(self.footprint_dir)
        if self.model3d_dir:
            out[f"KICAD{KICAD_MAJOR}_3DMODEL_DIR"] = str(self.model3d_dir)
        if self.template_dir:
            out[f"KICAD{KICAD_MAJOR}_TEMPLATE_DIR"] = str(self.template_dir)
        if self.user_docs:
            out[f"KICAD{KICAD_MAJOR}_3RD_PARTY"] = str(self.user_docs / "3rdparty")
        # explicit environment wins
        for k in list(out):
            if os.environ.get(k):
                out[k] = os.environ[k]
        return out

    def as_dict(self) -> dict:
        d = {k: (str(v) if isinstance(v, Path) else v) for k, v in self.__dict__.items()}
        d["env_vars"] = self.env_vars()
        return d


def _candidate_roots() -> list[Path]:
    cands: list[Path] = []
    explicit = os.environ.get("KICAD_ROOT")
    if explicit:
        cands.append(Path(explicit))
    system = platform.system()
    if system == "Windows":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), r"C:\Program Files"):
            kdir = Path(base) / "KiCad"
            if kdir.is_dir():
                versions = sorted((p for p in kdir.iterdir() if p.is_dir()), reverse=True)
                cands.extend(versions)
    elif system == "Darwin":
        cands.append(Path("/Applications/KiCad/KiCad.app/Contents"))
    else:
        cands.extend([Path("/usr"), Path("/usr/local"), Path("/snap/kicad/current/usr")])
    return cands


def _cli_in(root: Path) -> Path | None:
    system = platform.system()
    names = ["kicad-cli.exe", "kicad-cli"]
    dirs = [root / "bin", root / "MacOS", root]
    for d in dirs:
        for n in names:
            p = d / n
            if p.is_file():
                return p
    if system != "Windows":
        found = shutil.which("kicad-cli")
        if found:
            return Path(found)
    return None


def discover() -> KicadEnv:
    env = KicadEnv()
    system = platform.system()
    for root in _candidate_roots():
        cli = _cli_in(root)
        if cli:
            env.root = root
            env.cli = cli
            break
    if not env.cli:
        found = shutil.which("kicad-cli")
        if found:
            env.cli = Path(found)
            env.root = env.cli.parent.parent
    if not env.cli:
        env.problems.append("kicad-cli not found. Install KiCad 10 or set KICAD_ROOT.")
        return env

    root = env.root
    share_candidates = [root / "share" / "kicad", root / "SharedSupport", Path("/usr/share/kicad")]
    for s in share_candidates:
        if (s / "symbols").is_dir():
            env.share = s
            break
    if env.share:
        env.symbol_dir = env.share / "symbols"
        env.footprint_dir = env.share / "footprints"
        env.model3d_dir = env.share / "3dmodels"
        env.template_dir = env.share / "template"
    else:
        env.problems.append("KiCad share directory (symbols/footprints) not found.")

    for py in (root / "bin" / "python.exe", root / "bin" / "python3", root / "Frameworks" / "Python.framework" / "Versions" / "Current" / "bin" / "python3"):
        if py.is_file():
            env.python = py
            break

    if system == "Windows":
        env.user_config = Path(os.environ.get("APPDATA", "")) / "kicad" / f"{KICAD_MAJOR}.0"
        env.user_docs = Path.home() / "Documents" / "KiCad" / f"{KICAD_MAJOR}.0"
    elif system == "Darwin":
        env.user_config = Path.home() / "Library" / "Preferences" / "kicad" / f"{KICAD_MAJOR}.0"
        env.user_docs = Path.home() / "Documents" / "KiCad" / f"{KICAD_MAJOR}.0"
    else:
        env.user_config = Path.home() / ".config" / "kicad" / f"{KICAD_MAJOR}.0"
        env.user_docs = Path.home() / ".local" / "share" / "kicad" / f"{KICAD_MAJOR}.0"

    try:
        out = subprocess.run([str(env.cli), "version"], capture_output=True, text=True, timeout=30)
        env.version = out.stdout.strip() or out.stderr.strip()
    except Exception as exc:  # pragma: no cover
        env.problems.append(f"kicad-cli version failed: {exc}")
    if env.version and not env.version.startswith(KICAD_MAJOR + "."):
        env.problems.append(f"Expected KiCad {KICAD_MAJOR}.x, found {env.version}")
    return env


_CACHE: KicadEnv | None = None


def get() -> KicadEnv:
    global _CACHE
    if _CACHE is None:
        _CACHE = discover()
    return _CACHE


def run_cli(*args: str, cwd: Path | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    env = get()
    if not env.cli:
        raise RuntimeError("kicad-cli not available: " + "; ".join(env.problems))
    return subprocess.run([str(env.cli), *args], capture_output=True, text=True, cwd=cwd, timeout=timeout)


if __name__ == "__main__":
    print(json.dumps(get().as_dict(), indent=2))
