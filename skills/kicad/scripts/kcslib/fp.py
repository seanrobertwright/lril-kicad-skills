"""Generate KiCad 10 footprints (.kicad_mod) for the common package families
from datasheet package dimensions, following IPC-7351B land-pattern rules
and the KiCad Library Conventions (KLC F-rules).

Supported generators
--------------------
* ``chip``       two-terminal chip (0402/0603/0805/1206..., also LED/diode)
* ``gullwing``   SOIC / SSOP / TSSOP / SOT-23 / SOT-223 / QFP (two or four sides)
* ``no_lead``    QFN / DFN with optional exposed pad and paste splitting
* ``dip``        through-hole dual in-line
* ``header``     through-hole pin headers (1..N rows)
* ``custom``     explicit pad list

All dimensions in mm. The result is a plain S-expression node; write it with
:func:`write_footprint`.

IPC-7351B density levels: "L" (least), "N" (nominal, default), "M" (most).
"""
from __future__ import annotations

import math
import uuid as _uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import sexpr
from .sexpr import A, Atom, num

FP_VERSION = 20260206
GENERATOR = "pcbnew"
GENERATOR_VERSION = "10.0"

SILK_W = 0.12      # KLC F5.1
FAB_W = 0.10       # KLC F5.2
CRTYD_W = 0.05     # KLC F5.3
SILK_CLEAR = 0.20  # silk to pad clearance
COURTYARD = {"L": 0.10, "N": 0.25, "M": 0.50}  # KLC F5.3 typical courtyard offsets

# IPC-7351B fillet tables (toe, heel, side) per density
FILLET = {
    "gullwing": {"L": (0.15, 0.25, 0.01), "N": (0.35, 0.35, 0.03), "M": (0.55, 0.45, 0.05)},
    "gullwing_p<0.625": {"L": (0.15, 0.25, -0.04), "N": (0.35, 0.35, -0.02), "M": (0.55, 0.45, 0.01)},
    "no_lead": {"L": (0.20, 0.00, -0.04), "N": (0.30, 0.00, 0.00), "M": (0.40, 0.00, 0.04)},
    "chip": {"L": (0.15, 0.00, 0.00), "N": (0.35, 0.00, 0.00), "M": (0.55, 0.00, 0.00)},
    "chip_small": {"L": (0.10, 0.00, -0.05), "N": (0.20, 0.00, 0.00), "M": (0.30, 0.00, 0.05)},
}


def new_uuid() -> str:
    return str(_uuid.uuid4())


@dataclass
class PadSpec:
    number: str
    x: float
    y: float
    w: float
    h: float
    kind: str = "smd"          # smd | thru_hole | np_thru_hole
    shape: str = "roundrect"   # rect | roundrect | circle | oval
    drill: float | None = None
    rratio: float = 0.25
    layers: list[str] | None = None
    paste: bool = True
    thermal: bool = False       # exposed pad: split paste
    pintype: str | None = None


@dataclass
class FootprintSpec:
    name: str
    description: str
    tags: str
    pads: list[PadSpec]
    body_w: float               # nominal body size (X)
    body_h: float               # nominal body size (Y)
    smd: bool = True
    courtyard_offset: float = 0.25
    pin1_marker: bool = True
    model: str | None = None     # 3D model path, e.g. ${KIPRJMOD}/parts.3dshapes/X.step
    extra_lines: list[tuple[str, tuple[float, float], tuple[float, float], float]] = field(default_factory=list)
    body_polygon: list[tuple[float, float]] | None = None   # F.Fab outline override
    ref_y: float | None = None
    value_y: float | None = None


def _r(v: float) -> float:
    return round(v, 3)


# IPC-7351B tolerance assumptions (mm). F = fabrication, P = placement.
F_TOL = 0.05
P_TOL = 0.05


def _rss(*ranges: float) -> float:
    return math.sqrt(sum(r * r for r in ranges) + F_TOL ** 2 + P_TOL ** 2)


def ipc_land(l_nom: float, l_tol: float, t_nom: float, t_tol: float, w_nom: float, w_tol: float,
             toe: float, heel: float, side: float) -> tuple[float, float, float]:
    """IPC-7351B land calculation for a two-row terminal pattern.

    ``l`` = overall span tip-to-tip, ``t`` = terminal length along the span,
    ``w`` = terminal width. ``*_tol`` are +/- values. Returns
    (pad_length, pad_width, pad_center_offset_from_origin).
    """
    l_min, l_max = l_nom - l_tol, l_nom + l_tol
    t_min, t_max = t_nom - t_tol, t_nom + t_tol
    w_min = w_nom - w_tol
    s_min = l_min - 2 * t_max
    s_max = l_max - 2 * t_min
    z_max = l_min + 2 * toe + _rss(l_max - l_min)
    g_min = s_max - 2 * heel - _rss(s_max - s_min)
    x_max = w_min + 2 * side + _rss(2 * w_tol)
    pad_l = (z_max - g_min) / 2
    pad_w = x_max
    center = (z_max + g_min) / 4
    return (_r(pad_l), _r(pad_w), _r(center))


# --------------------------------------------------------------------------- #
# Generators
# --------------------------------------------------------------------------- #
def chip(name: str, body_l: float, body_w: float, term_l: float, height: float = 0.5, density: str = "N",
         description: str = "", tags: str = "", polarized: bool = False, model: str | None = None) -> FootprintSpec:
    """Two-terminal chip (0603 = body_l 1.6, body_w 0.8, term_l 0.3)."""
    table = FILLET["chip_small"] if body_l < 1.2 else FILLET["chip"]
    toe, heel, side = table[density]
    tol = 0.05 if body_l < 1.2 else 0.1
    pad_l, pad_w, cx = ipc_land(body_l, tol, term_l, tol / 2, body_w, tol, toe, heel, side)
    pads = [PadSpec("1", -cx, 0, pad_l, pad_w), PadSpec("2", cx, 0, pad_l, pad_w)]
    return FootprintSpec(name, description or f"{name}, chip package {body_l}x{body_w}mm",
                         tags or "chip", pads, body_l, body_w, courtyard_offset=COURTYARD[density],
                         pin1_marker=polarized, model=model)


def gullwing(name: str, pins: int, pitch: float, body_w: float, body_h: float, lead_span_x: float,
             lead_span_y: float | None = None, lead_w: float = 0.4, lead_l: float = 0.8, density: str = "N",
             sides: int = 2, description: str = "", tags: str = "", ep: tuple[float, float] | None = None,
             model: str | None = None, span_tol: float = 0.1, lead_w_tol: float = 0.05,
             lead_l_tol: float = 0.15, left_pins: list[str] | None = None,
             right_pins: list[str] | None = None) -> FootprintSpec:
    """SOIC/SSOP/TSSOP/SOT (sides=2, pins along the vertical edges, pin 1 top-left,
    counter-clockwise) or QFP (sides=4). ``lead_span_x`` is the tip-to-tip width.

    For asymmetric two-row packages (SOT-23-3: two pads left, one right) pass
    ``left_pins``/``right_pins`` as pad-number lists, top to bottom; each row is
    centred on the body. Use ``""`` for an empty slot (e.g. SOT-23-3 right row
    ``["", "3", ""]`` is not needed: a single pad is simply centred).
    """
    table = FILLET["gullwing_p<0.625"] if pitch < 0.625 else FILLET["gullwing"]
    toe, heel, side = table[density]
    pad_l, pad_w, x = ipc_land(lead_span_x, span_tol, lead_l, lead_l_tol, lead_w, lead_w_tol, toe, heel, side)
    pad_w = _r(min(pad_w, pitch - 0.2))  # keep the default 0.2 mm DRC clearance between pads
    pads: list[PadSpec] = []
    if left_pins is not None or right_pins is not None:
        left_pins = left_pins or []
        right_pins = right_pins or []
        for numbers, px in ((left_pins, -x), (right_pins, x)):
            n = len(numbers)
            for i, number in enumerate(numbers):
                if number == "":
                    continue
                y = _r((i - (n - 1) / 2) * pitch)
                pads.append(PadSpec(number, px, y, pad_l, pad_w))
        pads.sort(key=lambda p: (len(p.number), p.number))
    elif sides == 2:
        per_side = pins // 2
        ys = [_r((i - (per_side - 1) / 2) * pitch) for i in range(per_side)]
        n = 1
        for y in ys:                         # left side, top to bottom
            pads.append(PadSpec(str(n), -x, y, pad_l, pad_w)); n += 1
        for y in reversed(ys):               # right side, bottom to top
            pads.append(PadSpec(str(n), x, y, pad_l, pad_w)); n += 1
    else:
        per_side = pins // 4
        span_y = lead_span_y or lead_span_x
        _, _, y = ipc_land(span_y, span_tol, lead_l, lead_l_tol, lead_w, lead_w_tol, toe, heel, side)
        coords = [_r((i - (per_side - 1) / 2) * pitch) for i in range(per_side)]
        n = 1
        for c in coords:
            pads.append(PadSpec(str(n), -x, c, pad_l, pad_w)); n += 1
        for c in coords:
            pads.append(PadSpec(str(n), c, y, pad_w, pad_l)); n += 1
        for c in reversed(coords):
            pads.append(PadSpec(str(n), x, c, pad_l, pad_w)); n += 1
        for c in reversed(coords):
            pads.append(PadSpec(str(n), c, -y, pad_w, pad_l)); n += 1
    if ep:
        pads.append(PadSpec(str(pins + 1), 0, 0, ep[0], ep[1], shape="rect", thermal=True))
    return FootprintSpec(name, description or f"{name}, {pins} pins, {pitch}mm pitch", tags or "gullwing",
                         pads, body_w, body_h, courtyard_offset=COURTYARD[density], model=model)


def no_lead(name: str, pins: int, pitch: float, body: float, body_h: float | None = None, lead_w: float = 0.25,
            lead_l: float = 0.4, density: str = "N", ep: tuple[float, float] | None = None, sides: int = 4,
            description: str = "", tags: str = "", model: str | None = None, paste_split: int = 2) -> FootprintSpec:
    """QFN (sides=4) / DFN (sides=2). ``body`` is X size, ``body_h`` Y size (default square)."""
    toe, heel, side = FILLET["no_lead"][density]
    body_h = body_h or body
    pad_l, pad_w, x = ipc_land(body, 0.05, lead_l, 0.05, lead_w, 0.05, toe, heel, side)
    pad_w = _r(min(pad_w, pitch - 0.2))  # keep the default 0.2 mm DRC clearance between pads
    if ep:
        # keep >= 0.2 mm between the exposed pad and the perimeter pads
        for span, e in ((body, ep[0]), (body_h, ep[1])):
            _, _, cx = ipc_land(span, 0.05, lead_l, 0.05, lead_w, 0.05, toe, heel, side)
            inner = cx - pad_l / 2
            if inner - e / 2 < 0.21:
                shrink = 0.21 - (inner - e / 2)
                pad_l = _r(pad_l - shrink)
                x = _r(x + shrink / 2)
    pads: list[PadSpec] = []
    if sides == 4:
        per_side = pins // 4
        _, _, y = ipc_land(body_h, 0.05, lead_l, 0.05, lead_w, 0.05, toe, heel, side)
        coords = [_r((i - (per_side - 1) / 2) * pitch) for i in range(per_side)]
        n = 1
        for c in coords:
            pads.append(PadSpec(str(n), -x, c, pad_l, pad_w)); n += 1
        for c in coords:
            pads.append(PadSpec(str(n), c, y, pad_w, pad_l)); n += 1
        for c in reversed(coords):
            pads.append(PadSpec(str(n), x, c, pad_l, pad_w)); n += 1
        for c in reversed(coords):
            pads.append(PadSpec(str(n), c, -y, pad_w, pad_l)); n += 1
    else:
        per_side = pins // 2
        coords = [_r((i - (per_side - 1) / 2) * pitch) for i in range(per_side)]
        n = 1
        for c in coords:
            pads.append(PadSpec(str(n), -x, c, pad_l, pad_w)); n += 1
        for c in reversed(coords):
            pads.append(PadSpec(str(n), x, c, pad_l, pad_w)); n += 1
    if ep:
        pads.append(PadSpec(str(pins + 1), 0, 0, ep[0], ep[1], shape="rect", thermal=True))
    spec = FootprintSpec(name, description or f"{name}, {pins} pins, {pitch}mm pitch, {body}x{body_h}mm",
                         tags or "qfn dfn", pads, body, body_h, courtyard_offset=COURTYARD[density], model=model)
    spec.paste_split = paste_split  # type: ignore[attr-defined]
    return spec


def dip(name: str, pins: int, pitch: float = 2.54, row_spacing: float = 7.62, body_w: float | None = None,
        body_h: float | None = None, drill: float = 0.8, pad_d: float = 1.6, description: str = "",
        tags: str = "", model: str | None = None) -> FootprintSpec:
    """Through-hole DIP. Like the stock KiCad library, pad 1 sits at the origin."""
    per_side = pins // 2
    pads: list[PadSpec] = []
    ys = [_r(i * pitch) for i in range(per_side)]
    n = 1
    for y in ys:
        pads.append(PadSpec(str(n), 0, y, pad_d, pad_d, "thru_hole", "rect" if n == 1 else "oval", drill)); n += 1
    for y in reversed(ys):
        pads.append(PadSpec(str(n), row_spacing, y, pad_d, pad_d, "thru_hole", "oval", drill)); n += 1
    bw = body_w or (row_spacing - 1.27)
    bh = body_h or (per_side * pitch + 1.0)
    spec = FootprintSpec(name, description or f"{name}, DIP-{pins}, {row_spacing}mm row spacing", tags or "dip",
                         pads, bw, bh, smd=False, model=model)
    spec.origin_offset = (row_spacing / 2, (per_side - 1) * pitch / 2)  # type: ignore[attr-defined]
    return spec


def header(name: str, pins_per_row: int, rows: int = 1, pitch: float = 2.54, drill: float = 1.0, pad_d: float = 1.7,
           description: str = "", tags: str = "", model: str | None = None) -> FootprintSpec:
    pads: list[PadSpec] = []
    n = 1
    for i in range(pins_per_row):
        for r in range(rows):
            y = _r(i * pitch)
            x = _r(r * pitch)
            pads.append(PadSpec(str(n), x, y, pad_d, pad_d, "thru_hole", "rect" if n == 1 else "circle", drill)); n += 1
    bw = rows * pitch
    bh = pins_per_row * pitch
    spec = FootprintSpec(name, description or f"{name}, {rows}x{pins_per_row} pin header {pitch}mm", tags or "pin header",
                         pads, bw, bh, smd=False, model=model)
    spec.origin_offset = ((rows - 1) * pitch / 2, (pins_per_row - 1) * pitch / 2)  # type: ignore[attr-defined]
    return spec


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #
def _line(a: tuple[float, float], b: tuple[float, float], layer: str, width: float) -> list:
    return A("fp_line", A("start", num(a[0]), num(a[1])), A("end", num(b[0]), num(b[1])),
             A("stroke", A("width", num(width)), A("type", Atom("solid"))), A("layer", layer), A("uuid", new_uuid()))


def _rect(a: tuple[float, float], b: tuple[float, float], layer: str, width: float) -> list:
    return A("fp_rect", A("start", num(a[0]), num(a[1])), A("end", num(b[0]), num(b[1])),
             A("stroke", A("width", num(width)), A("type", Atom("solid"))), A("fill", Atom("no")),
             A("layer", layer), A("uuid", new_uuid()))


def _circle(c: tuple[float, float], r: float, layer: str, width: float, filled: bool = False) -> list:
    return A("fp_circle", A("center", num(c[0]), num(c[1])), A("end", num(c[0] + r), num(c[1])),
             A("stroke", A("width", num(width)), A("type", Atom("solid"))), A("fill", Atom("yes" if filled else "no")),
             A("layer", layer), A("uuid", new_uuid()))


def _text_prop(key: str, value: str, y: float, layer: str, hide: bool = False, size: float = 1.0) -> list:
    p = A("property", key, value, A("at", num(0), num(y), num(0)), A("layer", layer))
    if hide:
        p.append(A("hide", Atom("yes")))
    p.append(A("uuid", new_uuid()))
    p.append(A("effects", A("font", A("size", num(size), num(size)), A("thickness", num(0.15 if size >= 1 else 0.06)))))
    return p


def _pad_node(p: PadSpec, smd_fp: bool) -> list:
    if p.layers:
        layers = p.layers
    elif p.kind == "smd":
        layers = ["F.Cu", "F.Mask"] + (["F.Paste"] if p.paste and not p.thermal else [])
    elif p.kind == "np_thru_hole":
        layers = ["*.Cu", "*.Mask"]
    else:
        layers = ["*.Cu", "*.Mask"]
    node = A("pad", p.number, Atom(p.kind), Atom(p.shape), A("at", num(p.x), num(p.y)),
             A("size", num(p.w), num(p.h)))
    if p.kind != "smd":
        node.append(A("drill", num(p.drill or 0.8)))
    node.append(A("layers", *layers))
    if p.kind == "thru_hole":
        node.append(A("remove_unused_layers", Atom("no")))
    if p.shape == "roundrect":
        node.append(A("roundrect_rratio", num(p.rratio)))
    if p.pintype:
        node.append(A("pintype", p.pintype))
    node.append(A("uuid", new_uuid()))
    return node


def build_footprint(spec: FootprintSpec) -> list:
    fp = A("footprint", spec.name, A("version", num(FP_VERSION)), A("generator", GENERATOR),
           A("generator_version", GENERATOR_VERSION), A("layer", "F.Cu"),
           A("descr", spec.description), A("tags", spec.tags))
    hw, hh = spec.body_w / 2, spec.body_h / 2
    ox, oy = getattr(spec, "origin_offset", (0.0, 0.0))
    # extents including pads for courtyard/text placement
    xs = [p.x - p.w / 2 for p in spec.pads] + [p.x + p.w / 2 for p in spec.pads] + [ox - hw, ox + hw]
    ys = [p.y - p.h / 2 for p in spec.pads] + [p.y + p.h / 2 for p in spec.pads] + [oy - hh, oy + hh]
    ext = (min(xs), min(ys), max(xs), max(ys))
    ref_y = spec.ref_y if spec.ref_y is not None else _r(ext[1] - spec.courtyard_offset - 0.8)
    val_y = spec.value_y if spec.value_y is not None else _r(ext[3] + spec.courtyard_offset + 0.8)
    fp.append(_text_prop("Reference", "REF**", ref_y, "F.SilkS"))
    fp.append(_text_prop("Value", spec.name, val_y, "F.Fab"))
    fp.append(_text_prop("Datasheet", "", 0, "F.Fab", hide=True, size=1.27))
    fp.append(_text_prop("Description", spec.description, 0, "F.Fab", hide=True, size=1.27))
    fp.append(A("attr", Atom("smd" if spec.smd else "through_hole")))
    fp.append(A("duplicate_pad_numbers_are_jumpers", Atom("no")))
    # F.Fab body outline with pin-1 chamfer (KLC F5.2)
    if spec.body_polygon:
        pts = spec.body_polygon
        for a, b in zip(pts, pts[1:] + pts[:1]):
            fp.append(_line(a, b, "F.Fab", FAB_W))
    else:
        ch = min(1.0, spec.body_w / 4, spec.body_h / 4) if spec.pin1_marker else 0
        x0, y0, x1, y1 = ox - hw, oy - hh, ox + hw, oy + hh
        pts = [(x0 + ch, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0 + ch)]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            fp.append(_line(a, b, "F.Fab", FAB_W))
    # F.SilkS: body outline segments that stay clear of pads
    silk_off = SILK_W / 2 + 0.1
    sx0, sy0, sx1, sy1 = ox - hw - silk_off, oy - hh - silk_off, ox + hw + silk_off, oy + hh + silk_off

    def clear_of_pads(a: tuple[float, float], b: tuple[float, float]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Clip an axis-aligned silk segment against pad boxes (+clearance)."""
        segs = [(a, b)]
        for p in spec.pads:
            px0, py0 = p.x - p.w / 2 - SILK_CLEAR, p.y - p.h / 2 - SILK_CLEAR
            px1, py1 = p.x + p.w / 2 + SILK_CLEAR, p.y + p.h / 2 + SILK_CLEAR
            out = []
            for s, e in segs:
                if s[1] == e[1]:  # horizontal
                    y = s[1]
                    if not (py0 <= y <= py1):
                        out.append((s, e)); continue
                    lo, hi = min(s[0], e[0]), max(s[0], e[0])
                    if hi <= px0 or lo >= px1:
                        out.append((s, e)); continue
                    if lo < px0:
                        out.append(((lo, y), (px0, y)))
                    if hi > px1:
                        out.append(((px1, y), (hi, y)))
                else:
                    x = s[0]
                    if not (px0 <= x <= px1):
                        out.append((s, e)); continue
                    lo, hi = min(s[1], e[1]), max(s[1], e[1])
                    if hi <= py0 or lo >= py1:
                        out.append((s, e)); continue
                    if lo < py0:
                        out.append(((x, lo), (x, py0)))
                    if hi > py1:
                        out.append(((x, py1), (x, hi)))
            segs = out
        return [(s, e) for s, e in segs if abs(s[0] - e[0]) + abs(s[1] - e[1]) > 0.3]

    for a, b in (((sx0, sy0), (sx1, sy0)), ((sx1, sy0), (sx1, sy1)), ((sx1, sy1), (sx0, sy1)), ((sx0, sy1), (sx0, sy0))):
        for s, e in clear_of_pads((_r(a[0]), _r(a[1])), (_r(b[0]), _r(b[1]))):
            fp.append(_line((_r(s[0]), _r(s[1])), (_r(e[0]), _r(e[1])), "F.SilkS", SILK_W))
    # pin 1 marker on silk: small filled circle outside pad 1 (KLC F5.1)
    if spec.pin1_marker and spec.pads:
        p1 = spec.pads[0]
        mx = _r(p1.x - p1.w / 2 - 0.4) if p1.x <= ox else _r(p1.x + p1.w / 2 + 0.4)
        my = _r(p1.y - p1.h / 2 - 0.4) if abs(p1.x - ox) < 1e-6 or len(spec.pads) == 2 else _r(p1.y)
        if len(spec.pads) == 2:
            mx, my = _r(p1.x - p1.w / 2 - 0.4), _r(p1.y)
        fp.append(_circle((mx, my), 0.15, "F.SilkS", 0.12, filled=True))
    # courtyard
    co = spec.courtyard_offset
    cx0, cy0, cx1, cy1 = ext[0] - co, ext[1] - co, ext[2] - 0 + co, ext[3] + co
    # KLC F5.3: courtyard on 0.01 grid
    cx0, cy0, cx1, cy1 = (math.floor(cx0 * 100) / 100, math.floor(cy0 * 100) / 100,
                          math.ceil(cx1 * 100) / 100, math.ceil(cy1 * 100) / 100)
    fp.append(_rect((cx0, cy0), (cx1, cy1), "F.CrtYd", CRTYD_W))
    for layer, a, b, w in spec.extra_lines:
        fp.append(_line(a, b, layer, w))
    # reference on fab (KLC F5.2)
    fp.append(A("fp_text", Atom("user"), "${REFERENCE}", A("at", num(ox), num(oy), num(0)), A("layer", "F.Fab"),
                A("uuid", new_uuid()),
                A("effects", A("font", A("size", num(min(1.0, spec.body_w / 4)), num(min(1.0, spec.body_w / 4))),
                               A("thickness", num(0.15 if spec.body_w >= 4 else 0.06))))))
    # pads
    split = getattr(spec, "paste_split", 0)
    for p in spec.pads:
        fp.append(_pad_node(p, spec.smd))
        if p.thermal and split:
            # paste windows: split x split grid covering ~50-60% area
            n = split
            frac = 0.75
            cw, chh = p.w / n * frac, p.h / n * frac
            for i in range(n):
                for j in range(n):
                    px = p.x - p.w / 2 + p.w / n * (i + 0.5)
                    py = p.y - p.h / 2 + p.h / n * (j + 0.5)
                    fp.append(A("pad", "", Atom("smd"), Atom("rect"), A("at", num(_r(px)), num(_r(py))),
                                A("size", num(_r(cw)), num(_r(chh))), A("layers", "F.Paste"), A("uuid", new_uuid())))
    fp.append(A("embedded_fonts", Atom("no")))
    if spec.model:
        fp.append(A("model", spec.model, A("offset", A("xyz", num(0), num(0), num(0))),
                    A("scale", A("xyz", num(1), num(1), num(1))), A("rotate", A("xyz", num(0), num(0), num(0)))))
    return fp


def write_footprint(spec: FootprintSpec, pretty_dir: str | Path) -> Path:
    d = Path(pretty_dir)
    if d.suffix != ".pretty":
        raise ValueError("footprint libraries are directories named *.pretty")
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{spec.name}.kicad_mod"
    sexpr.dump(build_footprint(spec), path)
    return path


def check_footprint(fp: list) -> list[str]:
    """Cheap KLC checks on a footprint node."""
    problems: list[str] = []
    name = str(fp[1])
    layers = {str(sexpr.child(c, "layer")[1]) for c in fp if isinstance(c, list) and sexpr.child(c, "layer")}
    if "F.CrtYd" not in layers and "B.CrtYd" not in layers:
        problems.append(f"{name}: no courtyard (KLC F5.3)")
    if "F.Fab" not in layers:
        problems.append(f"{name}: no F.Fab outline (KLC F5.2)")
    pads = sexpr.children(fp, "pad")
    if not pads:
        problems.append(f"{name}: no pads")
    nums = [str(p[1]) for p in pads if str(p[1])]
    if nums and "1" not in nums and not any(n in ("A", "K") for n in nums):
        problems.append(f"{name}: no pad numbered 1")
    for p in pads:
        size = sexpr.floats(sexpr.child(p, "size"))
        if min(size) < 0.2:
            problems.append(f"{name}: pad {p[1]} smaller than 0.2 mm")
        if str(p[2]) == "thru_hole":
            drill = sexpr.child(p, "drill")
            dr = sexpr.floats(drill)[0] if drill else 0
            if dr and min(size) - dr < 0.3:
                problems.append(f"{name}: pad {p[1]} annular ring < 0.15 mm (KLC F7)")
    if not sexpr.child(fp, "descr") or not sexpr.child(fp, "descr")[1]:
        problems.append(f"{name}: empty description (KLC F9)")
    if not sexpr.child(fp, "model"):
        problems.append(f"{name}: no 3D model (KLC F9.3, informational)")
    return problems
