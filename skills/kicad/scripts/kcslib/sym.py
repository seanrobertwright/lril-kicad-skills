"""Generate KiCad 10 symbol libraries (.kicad_sym) that follow the KiCad
Library Conventions (KLC) for the common "rectangle with pins" style.

Input is a plain pin table, the kind you transcribe from a datasheet::

    spec = SymbolSpec(
        name="TPS7A0233", reference="U", value="TPS7A0233",
        footprint="Package_TO_SOT_SMD:SOT-23-5", datasheet="https://...",
        description="200mA ultra-low-IQ LDO, 3.3V", keywords="ldo regulator",
        pins=[
            PinSpec("1", "IN", "power_in", "left"),
            PinSpec("2", "GND", "power_in", "bottom"),
            PinSpec("3", "EN", "input", "left"),
            PinSpec("4", "NC", "no_connect", "right"),
            PinSpec("5", "OUT", "power_out", "right"),
        ])
    write_library([spec], "MyParts.kicad_sym")

KLC rules applied: 2.54 mm pin length (S4.1), pins on the 2.54 grid (S4.1),
pin ends on the 100 mil grid, body outline 0.254 mm (S3.2), background fill
for ICs (S3.3), name offset 0.508 mm (S4.1), reference/value placement
(S3.6), ``~{NAME}`` overbar notation preserved, power pins default to
`power_in`, NC pins hidden of type no_connect (S4.6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import sexpr
from .sexpr import A, Atom, num

SYM_VERSION = 20251024
GENERATOR = "kicad_symbol_editor"
GENERATOR_VERSION = "10.0"

PIN_TYPES = {"input", "output", "bidirectional", "tri_state", "passive", "free", "unspecified",
             "power_in", "power_out", "open_collector", "open_emitter", "no_connect"}
PIN_SHAPES = {"line", "inverted", "clock", "inverted_clock", "input_low", "clock_low", "output_low",
              "edge_clock_high", "non_logic"}
SIDES = ("left", "right", "top", "bottom")


@dataclass
class PinSpec:
    number: str
    name: str
    etype: str = "passive"
    side: str = "left"
    shape: str = "line"
    unit: int = 1
    hidden: bool | None = None       # None = auto (hide no_connect pins)
    gap_before: int = 0              # extra 2.54 mm slots before this pin (grouping)
    alternates: list[tuple[str, str]] = field(default_factory=list)  # (name, etype)

    def __post_init__(self):
        if self.etype not in PIN_TYPES:
            raise ValueError(f"pin {self.number}: unknown electrical type {self.etype!r}")
        if self.side not in SIDES:
            raise ValueError(f"pin {self.number}: side must be one of {SIDES}")
        if self.shape not in PIN_SHAPES:
            raise ValueError(f"pin {self.number}: unknown shape {self.shape!r}")


@dataclass
class SymbolSpec:
    name: str
    reference: str
    pins: list[PinSpec]
    value: str | None = None
    footprint: str = ""
    datasheet: str = ""
    description: str = ""
    keywords: str = ""
    fp_filters: str = ""
    pin_length: float = 2.54
    pin_pitch: float = 2.54
    body_fill: str = "background"   # background | none
    hide_pin_numbers: bool = False
    hide_pin_names: bool = False
    name_offset: float = 0.508
    extra_props: dict[str, str] = field(default_factory=dict)
    power: bool = False
    min_width: float = 7.62
    units: int = 1
    units_interchangeable: bool = False


def _effects(size: float = 1.27, hide: bool = False, justify: list[str] | None = None) -> list:
    e = A("effects", A("font", A("size", num(size), num(size))))
    if justify:
        e.append(A("justify", *[Atom(j) for j in justify]))
    if hide:
        e.append(A("hide", Atom("yes")))
    return e


def _prop(key: str, value: str, x: float, y: float, rot: float = 0, hide: bool = False,
          justify: list[str] | None = None) -> list:
    p = A("property", key, value, A("at", num(x), num(y), num(rot)))
    p.append(A("show_name", Atom("no")))
    p.append(A("do_not_autoplace", Atom("no")))
    if hide:
        p.append(A("hide", Atom("yes")))
    p.append(_effects(1.27, justify=justify))
    return p


def _text_width(text: str, size: float = 1.27) -> float:
    """Rough width of KiCad stroke font text: ~0.8 * size per character."""
    stripped = text.replace("~{", "").replace("}", "")
    return len(stripped) * size * 0.8


def _snap_up(v: float, grid: float = 2.54) -> float:
    import math
    return math.ceil(v / grid - 1e-9) * grid


def layout_unit(spec: SymbolSpec, unit: int) -> tuple[list[list], list[list], tuple[float, float, float, float]]:
    """Return (graphics, pins, bbox) for one unit in library coordinates (Y up)."""
    pins = [p for p in spec.pins if p.unit == unit]

    def is_hidden(p: PinSpec) -> bool:
        return p.hidden if p.hidden is not None else (p.etype == "no_connect")

    # visible pins first so hidden NC pins do not leave gaps in the layout
    by_side = {s: [p for p in pins if p.side == s and not is_hidden(p)] + [p for p in pins if p.side == s and is_hidden(p)]
               for s in SIDES}
    pitch = spec.pin_pitch

    def slots(ps: list[PinSpec]) -> int:
        return sum(1 + p.gap_before for p in ps if not is_hidden(p))

    # body size from pin counts and name lengths
    left_names = max([_text_width(p.name) for p in by_side["left"]] + [0])
    right_names = max([_text_width(p.name) for p in by_side["right"]] + [0])
    top_names = max([_text_width(p.name) for p in by_side["top"]] + [0])
    bot_names = max([_text_width(p.name) for p in by_side["bottom"]] + [0])
    inner_w = left_names + right_names + 2 * spec.name_offset + 2.54
    inner_h = top_names + bot_names + 2 * spec.name_offset + 2.54
    w = max(spec.min_width, _snap_up(inner_w), (max(slots(by_side["top"]), slots(by_side["bottom"])) + 1) * pitch)
    h = max(5.08, _snap_up(inner_h), (max(slots(by_side["left"]), slots(by_side["right"])) + 1) * pitch)
    # keep the body edges on the 1.27 grid and pin ends on 2.54 grid
    half_w = _snap_up(w / 2, 1.27)
    half_h = _snap_up(h / 2, 1.27)
    x0, x1, y0, y1 = -half_w, half_w, -half_h, half_h

    pin_nodes: list[list] = []

    def emit(p: PinSpec, x: float, y: float, angle: float) -> None:
        hidden = p.hidden if p.hidden is not None else (p.etype == "no_connect")
        node = A("pin", Atom(p.etype), Atom(p.shape), A("at", num(x), num(y), num(angle)),
                 A("length", num(spec.pin_length)))
        if hidden:
            node.append(A("hide", Atom("yes")))
        node.append(A("name", p.name, _effects(1.27)))
        node.append(A("number", p.number, _effects(1.27)))
        for alt_name, alt_type in p.alternates:
            node.append(A("alternate", alt_name, Atom(alt_type), Atom("line")))
        pin_nodes.append(node)

    def place_vertical(ps: list[PinSpec], x: float, angle: float) -> None:
        n = slots(ps)
        # centre the group on the body (rounded up to a whole pitch so every
        # pin end stays on the 2.54 mm grid, KLC S4.1), top pin first
        y = _snap_up(((n - 1) * pitch) / 2, pitch)
        for p in ps:
            y -= p.gap_before * pitch
            emit(p, x, y, angle)
            y -= pitch

    def place_horizontal(ps: list[PinSpec], y: float, angle: float) -> None:
        n = slots(ps)
        x = -_snap_up(((n - 1) * pitch) / 2, pitch)
        for p in ps:
            x += p.gap_before * pitch
            emit(p, x, y, angle)
            x += pitch

    place_vertical(by_side["left"], x0 - spec.pin_length, 0)
    place_vertical(by_side["right"], x1 + spec.pin_length, 180)
    place_horizontal(by_side["top"], y1 + spec.pin_length, 270)
    place_horizontal(by_side["bottom"], y0 - spec.pin_length, 90)

    graphics = [A("rectangle", A("start", num(x0), num(y1)), A("end", num(x1), num(y0)),
                  A("stroke", A("width", num(0.254)), A("type", Atom("default"))),
                  A("fill", A("type", Atom(spec.body_fill))))]
    # text placement must clear the pin band on sides that have pins
    y_top = y1 + (spec.pin_length if by_side["top"] else 0)
    y_bot = y0 - (spec.pin_length if by_side["bottom"] else 0)
    return graphics, pin_nodes, (x0, y_bot, x1, y_top)


def build_symbol(spec: SymbolSpec) -> list:
    value = spec.value or spec.name
    sym = A("symbol", spec.name)
    if spec.power:
        sym.append(A("power", Atom("global")))
    if spec.hide_pin_numbers:
        sym.append(A("pin_numbers", A("hide", Atom("yes"))))
    pn = A("pin_names", A("offset", num(spec.name_offset)))
    if spec.hide_pin_names:
        pn.append(A("hide", Atom("yes")))
    sym.append(pn)
    sym += [A("exclude_from_sim", Atom("no")), A("in_bom", Atom("yes")), A("on_board", Atom("yes")),
            A("in_pos_files", Atom("yes")), A("duplicate_pin_numbers_are_jumpers", Atom("no"))]
    units_out = []
    bboxes = []
    for u in range(1, spec.units + 1):
        g, p, bb = layout_unit(spec, u)
        units_out.append((u, g, p))
        bboxes.append(bb)
    x0 = min(b[0] for b in bboxes); y0 = min(b[1] for b in bboxes)
    x1 = max(b[2] for b in bboxes); y1 = max(b[3] for b in bboxes)
    # KLC S3.6: reference above-left, value below-left of body (outside pins)
    sym.append(_prop("Reference", spec.reference, x0, y1 + 1.27, justify=["left"]))
    sym.append(_prop("Value", value, x0, y0 - 1.27, justify=["left"]))
    sym.append(_prop("Footprint", spec.footprint, 0, 0, hide=True))
    sym.append(_prop("Datasheet", spec.datasheet, 0, 0, hide=True))
    sym.append(_prop("Description", spec.description, 0, 0, hide=True))
    if spec.keywords:
        sym.append(_prop("ki_keywords", spec.keywords, 0, 0, hide=True))
    if spec.fp_filters:
        sym.append(_prop("ki_fp_filters", spec.fp_filters, 0, 0, hide=True))
    for k, v in spec.extra_props.items():
        sym.append(_prop(k, v, 0, 0, hide=True))
    for u, g, p in units_out:
        unit_no = u if spec.units > 1 else 0
        gsub = A("symbol", f"{spec.name}_{unit_no}_1", *g)
        sym.append(gsub)
        psub = A("symbol", f"{spec.name}_{u}_1", *p)
        sym.append(psub)
    sym.append(A("embedded_fonts", Atom("no")))
    return sym


def build_library(symbols: list[list]) -> list:
    lib = A("kicad_symbol_lib", A("version", num(SYM_VERSION)), A("generator", GENERATOR),
            A("generator_version", GENERATOR_VERSION))
    lib += symbols
    return lib


def write_library(specs: list[SymbolSpec], path: str | Path, merge: bool = True) -> Path:
    """Write (or merge into) a .kicad_sym file. Existing symbols with the same
    name are replaced."""
    path = Path(path)
    new = {s.name: build_symbol(s) for s in specs}
    if merge and path.exists():
        lib = sexpr.load(path)
        kept = [c for c in sexpr.children(lib, "symbol") if str(c[1]) not in new]
        sexpr.remove_children(lib, "symbol")
        lib += kept
        lib += list(new.values())
        sexpr.set_child(lib, A("version", num(SYM_VERSION)))
        sexpr.set_child(lib, A("generator_version", GENERATOR_VERSION))
    else:
        lib = build_library(list(new.values()))
    sexpr.dump(lib, path)
    return path


# --------------------------------------------------------------------------- #
# KLC-style checks
# --------------------------------------------------------------------------- #
def check_symbol(sym: list) -> list[str]:
    """Cheap KLC sanity checks on a symbol node. Returns human-readable problems."""
    problems: list[str] = []
    name = str(sym[1])
    pins = []
    for sub in sexpr.children(sym, "symbol"):
        pins += sexpr.children(sub, "pin")
    numbers = [str(sexpr.child(p, "number")[1]) for p in pins]
    dupes = {n for n in numbers if numbers.count(n) > 1}
    if dupes:
        problems.append(f"{name}: duplicate pin numbers {sorted(dupes)} (allowed only for stacked pins)")
    for p in pins:
        at = sexpr.floats(sexpr.child(p, "at"))
        ln = sexpr.floats(sexpr.child(p, "length"))[0]
        for v in at[:2]:
            if abs(v / 2.54 - round(v / 2.54)) > 1e-3:
                problems.append(f"{name}: pin {sexpr.child(p, 'number')[1]} end ({at[0]},{at[1]}) is off the 2.54 mm grid (KLC S4.1)")
                break
        if ln < 2.54:
            problems.append(f"{name}: pin {sexpr.child(p, 'number')[1]} length {ln} < 2.54 (KLC S4.1)")
        if str(p[1]) == "power_in" and str(sexpr.child(p, "name")[1]).upper() in ("NC", "N/C"):
            problems.append(f"{name}: pin named NC is typed power_in")
    if not sexpr.get_property(sym, "Datasheet"):
        problems.append(f"{name}: Datasheet property is empty (KLC S6.1)")
    if not sexpr.get_property(sym, "Description"):
        problems.append(f"{name}: Description is empty (KLC S6.2)")
    ref = sexpr.get_property(sym, "Reference") or ""
    if ref.endswith("?") or ref.endswith("1"):
        problems.append(f"{name}: Reference should be a bare prefix like 'U', got {ref!r}")
    return problems
