"""Symbol and footprint library access.

* Reads the global ``sym-lib-table`` / ``fp-lib-table`` (KiCad 10 nests the
  stock table via a ``(type "Table")`` entry) plus any project-local tables.
* Resolves ``Lib:Name`` ids to parsed S-expression nodes.
* Extracts pin geometry from symbols, following ``(extends ...)``.
* Searches libraries by name/description/keywords.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import env as kenv
from . import sexpr
from .sexpr import Atom, children, child, floats, get_property, is_node

_VAR_RE = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


def expand(uri: str, extra: dict[str, str] | None = None) -> str:
    vars_ = dict(kenv.get().env_vars())
    if extra:
        vars_.update(extra)

    def repl(m: re.Match) -> str:
        key = m.group(1)
        return vars_.get(key, os.environ.get(key, m.group(0)))

    return _VAR_RE.sub(repl, uri)


@dataclass(frozen=True)
class LibEntry:
    name: str
    type: str
    uri: str
    descr: str = ""

    def path(self, project_dir: Path | None = None) -> Path:
        extra = {"KIPRJMOD": str(project_dir)} if project_dir else None
        return Path(expand(self.uri, extra))


def _read_table(path: Path, project_dir: Path | None) -> list[LibEntry]:
    if not path.is_file():
        return []
    tree = sexpr.load(path)
    out: list[LibEntry] = []
    for lib in children(tree, "lib"):
        fields = {c[0]: (c[1] if len(c) > 1 else "") for c in lib if isinstance(c, list)}
        entry = LibEntry(str(fields.get("name", "")), str(fields.get("type", "KiCad")),
                         str(fields.get("uri", "")), str(fields.get("descr", "")))
        if entry.type == "Table":
            out.extend(_read_table(entry.path(project_dir), project_dir))
        else:
            out.append(entry)
    return out


def symbol_libs(project_dir: Path | None = None) -> dict[str, LibEntry]:
    """Name -> entry. Project table entries override global ones."""
    e = kenv.get()
    result: dict[str, LibEntry] = {}
    if e.user_config:
        for ent in _read_table(e.user_config / "sym-lib-table", project_dir):
            result[ent.name] = ent
    if not result and e.template_dir:
        for ent in _read_table(e.template_dir / "sym-lib-table", project_dir):
            result[ent.name] = ent
    if project_dir:
        for ent in _read_table(Path(project_dir) / "sym-lib-table", Path(project_dir)):
            result[ent.name] = ent
    return result


def footprint_libs(project_dir: Path | None = None) -> dict[str, LibEntry]:
    e = kenv.get()
    result: dict[str, LibEntry] = {}
    if e.user_config:
        for ent in _read_table(e.user_config / "fp-lib-table", project_dir):
            result[ent.name] = ent
    if not result and e.template_dir:
        for ent in _read_table(e.template_dir / "fp-lib-table", project_dir):
            result[ent.name] = ent
    if project_dir:
        for ent in _read_table(Path(project_dir) / "fp-lib-table", Path(project_dir)):
            result[ent.name] = ent
    return result


@lru_cache(maxsize=64)
def _load_symbol_file(path: str) -> list:
    return sexpr.load(path)


# --------------------------------------------------------------------------- #
# Symbols
# --------------------------------------------------------------------------- #
@dataclass
class Pin:
    number: str
    name: str
    etype: str          # passive, input, output, bidirectional, power_in, ...
    shape: str          # line, inverted, clock, ...
    x: float            # library coords (Y up), mm
    y: float
    angle: float        # 0 = pin points right (connect on its left/outer end...)
    length: float
    unit: int
    hidden: bool = False

    @property
    def end(self) -> tuple[float, float]:
        """Connection point of the pin (library coords, Y up)."""
        # In KiCad symbol libs (at x y angle) is the connection end; the pin
        # body extends from there toward the symbol body. So the end *is* (x, y).
        return (self.x, self.y)


def split_lib_id(lib_id: str) -> tuple[str, str]:
    if ":" not in lib_id:
        raise ValueError(f"lib_id must be 'Library:Symbol', got {lib_id!r}")
    lib, name = lib_id.split(":", 1)
    return lib, name


def _symbol_from_tree(tree: list, name: str) -> list | None:
    for s in children(tree, "symbol"):
        if len(s) > 1 and s[1] == name:
            return s
    return None


def load_symbol(lib_id: str, project_dir: Path | None = None) -> list:
    """Return the raw ``(symbol "Name" ...)`` node from its library file.

    Derived symbols (``extends``) are returned as-is; use :func:`resolve_symbol`
    for a flattened copy suitable for embedding in a schematic.
    """
    lib, name = split_lib_id(lib_id)
    libs = symbol_libs(project_dir)
    if lib not in libs:
        raise KeyError(f"Symbol library {lib!r} is not in any sym-lib-table")
    path = libs[lib].path(project_dir)
    if not path.is_file():
        raise FileNotFoundError(f"Library {lib!r} -> {path} does not exist")
    tree = _load_symbol_file(str(path))
    node = _symbol_from_tree(tree, name)
    if node is None:
        raise KeyError(f"Symbol {name!r} not found in {path.name}")
    return node


def resolve_symbol(lib_id: str, project_dir: Path | None = None) -> list:
    """Flattened deep copy: ``extends`` parents merged, sub-symbols renamed to
    ``Lib:Name_u_s`` form as KiCad expects inside a schematic ``lib_symbols``."""
    import copy

    lib, name = split_lib_id(lib_id)
    node = copy.deepcopy(load_symbol(lib_id, project_dir))
    ext = child(node, "extends")
    if ext is not None:
        parent = resolve_symbol(f"{lib}:{ext[1]}", project_dir)
        # child properties override parent's; parent supplies graphics + pins
        merged = copy.deepcopy(parent)
        merged[1] = name
        child_props = {p[1]: p for p in children(node, "property")}
        for i, c in enumerate(merged):
            if is_node(c, "property") and c[1] in child_props:
                merged[i] = child_props.pop(c[1])
        for p in child_props.values():
            merged.append(p)
        for tok in ("pin_numbers", "pin_names", "exclude_from_sim", "in_bom", "on_board",
                    "in_pos_files", "duplicate_pin_numbers_are_jumpers", "power"):
            c = child(node, tok)
            if c is not None:
                sexpr.set_child(merged, c)
        # rename sub-symbols from Parent_u_s to Name_u_s
        for sub in children(merged, "symbol"):
            sub[1] = re.sub(r"^.*?(_\d+_\d+)$", name + r"\1", sub[1])
        node = merged
    # KiCad stores embedded symbols with the library prefix on the top-level
    # name only; sub-symbols keep the bare "Name_unit_style" form.
    node[1] = f"{lib}:{name}"
    for sub in children(node, "symbol"):
        if sub[1].startswith(lib + ":"):
            sub[1] = sub[1][len(lib) + 1:]
    return node


def _parse_pin(p: list, unit: int) -> Pin:
    etype = str(p[1]) if len(p) > 1 else "passive"
    shape = str(p[2]) if len(p) > 2 else "line"
    at = child(p, "at")
    x, y, ang = (floats(at) + [0, 0, 0])[:3] if at else (0.0, 0.0, 0.0)
    ln = child(p, "length")
    length = floats(ln)[0] if ln else 2.54
    name_node = child(p, "name")
    num_node = child(p, "number")
    hidden = any(isinstance(c, Atom) and c == "hide" for c in p) or (
        child(p, "hide") is not None and len(child(p, "hide")) > 1 and child(p, "hide")[1] == "yes")
    return Pin(
        number=str(num_node[1]) if num_node else "",
        name=str(name_node[1]) if name_node else "",
        etype=etype, shape=shape, x=x, y=y, angle=ang, length=length, unit=unit, hidden=hidden,
    )


def symbol_pins(sym: list) -> list[Pin]:
    """All pins of a (resolved) symbol node, with their unit number.

    Sub-symbol names end in ``_<unit>_<style>``; unit 0 means "all units".
    """
    pins: list[Pin] = []
    for sub in children(sym, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", sub[1])
        unit = int(m.group(1)) if m else 0
        for p in children(sub, "pin"):
            pins.append(_parse_pin(p, unit))
    # pins directly under the symbol (rare)
    for p in children(sym, "pin"):
        pins.append(_parse_pin(p, 0))
    return pins


def symbol_units(sym: list) -> int:
    units = {0}
    for sub in children(sym, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", sub[1])
        if m:
            units.add(int(m.group(1)))
    return max(units) if units else 1


def symbol_bbox(sym: list, unit: int = 1) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) in library coords over graphics + pin ends."""
    xs: list[float] = []
    ys: list[float] = []
    for sub in children(sym, "symbol"):
        m = re.search(r"_(\d+)_(\d+)$", sub[1])
        u = int(m.group(1)) if m else 0
        if u not in (0, unit):
            continue
        for shape in sub:
            if not isinstance(shape, list):
                continue
            for pt in sexpr.find_all(shape, "xy"):
                v = floats(pt)
                xs.append(v[0]); ys.append(v[1])
            for tok in ("start", "end", "mid", "center", "at"):
                c = child(shape, tok)
                if c is not None:
                    v = floats(c)
                    xs.append(v[0]); ys.append(v[1])
            if is_node(shape, "circle"):
                c = child(shape, "center"); r = child(shape, "radius")
                if c and r:
                    cx, cy = floats(c); rr = floats(r)[0]
                    xs += [cx - rr, cx + rr]; ys += [cy - rr, cy + rr]
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def is_power_symbol(sym: list) -> bool:
    return child(sym, "power") is not None


def symbol_description(sym: list) -> str:
    return get_property(sym, "Description") or ""


def search_symbols(query: str, project_dir: Path | None = None, limit: int = 40,
                   libs: list[str] | None = None) -> list[dict]:
    """Case-insensitive substring search over name/description/keywords."""
    q = query.lower()
    hits: list[dict] = []
    for lib, ent in symbol_libs(project_dir).items():
        if libs and lib not in libs:
            continue
        path = ent.path(project_dir)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if q not in text.lower():
            continue
        tree = _load_symbol_file(str(path))
        for s in children(tree, "symbol"):
            name = str(s[1])
            desc = get_property(s, "Description") or ""
            kw = get_property(s, "ki_keywords") or ""
            hay = f"{name} {desc} {kw}".lower()
            if q in hay:
                hits.append({"lib_id": f"{lib}:{name}", "description": desc, "keywords": kw,
                             "footprint": get_property(s, "Footprint") or "",
                             "fp_filters": get_property(s, "ki_fp_filters") or ""})
                if len(hits) >= limit:
                    return hits
    return hits


# --------------------------------------------------------------------------- #
# Footprints
# --------------------------------------------------------------------------- #
def footprint_path(fp_id: str, project_dir: Path | None = None) -> Path:
    lib, name = split_lib_id(fp_id)
    libs = footprint_libs(project_dir)
    if lib not in libs:
        raise KeyError(f"Footprint library {lib!r} is not in any fp-lib-table")
    path = libs[lib].path(project_dir) / f"{name}.kicad_mod"
    if not path.is_file():
        raise FileNotFoundError(f"Footprint {fp_id!r} -> {path} does not exist")
    return path


def load_footprint(fp_id: str, project_dir: Path | None = None) -> list:
    return sexpr.load(footprint_path(fp_id, project_dir))


def search_footprints(query: str, project_dir: Path | None = None, limit: int = 60,
                      libs: list[str] | None = None) -> list[str]:
    q = query.lower()
    hits: list[str] = []
    for lib, ent in footprint_libs(project_dir).items():
        if libs and lib not in libs:
            continue
        d = ent.path(project_dir)
        if not d.is_dir():
            continue
        for f in d.glob("*.kicad_mod"):
            if q in f.stem.lower() or q in lib.lower():
                hits.append(f"{lib}:{f.stem}")
                if len(hits) >= limit:
                    return hits
    return hits


def footprint_pads(fp: list) -> list[dict]:
    out = []
    for p in children(fp, "pad"):
        at = child(p, "at")
        size = child(p, "size")
        out.append({
            "number": str(p[1]), "type": str(p[2]), "shape": str(p[3]),
            "at": floats(at)[:2] if at else [0, 0],
            "size": floats(size) if size else [0, 0],
            "layers": [str(x) for x in (child(p, "layers") or [])[1:]],
        })
    return out
