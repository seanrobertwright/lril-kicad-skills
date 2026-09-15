"""Write KiCad 10 schematics (.kicad_sch) from Python.

The builder keeps a flat list of S-expression nodes and knows enough
geometry to tell you where every pin of a placed symbol ends up, so wires,
labels and power symbols can be attached exactly on the pin ends.

Typical use::

    sch = Schematic(project_name="blinky", title="Blinky")
    r1 = sch.add_symbol("Device:R", "R1", "10k", at=(50, 50), rot=90,
                        footprint="Resistor_SMD:R_0603_1608Metric")
    sch.connect_label(r1, "1", "VIN")          # stub wire + local label
    sch.connect_power(r1, "2", "GND")          # stub wire + GND symbol
    sch.save("blinky.kicad_sch")

All coordinates are millimetres, Y down, and should sit on the 1.27 mm grid.
"""
from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field
from pathlib import Path

from . import geom, libs, sexpr
from .sexpr import A, Atom, num, yn

SCH_VERSION = 20260306
GENERATOR = "eeschema"
GENERATOR_VERSION = "10.0"

POWER_LIB = "power"
PWR_FLAG = "power:PWR_FLAG"

# Net names that are conventionally drawn with power symbols.
POWER_SYMBOL_FOR_NET = {
    "GND": "power:GND", "GNDA": "power:GNDA", "GNDD": "power:GNDD", "GNDPWR": "power:GNDPWR",
    "AGND": "power:GNDA", "DGND": "power:GNDD", "EARTH": "power:Earth",
    "+3V3": "power:+3V3", "+3.3V": "power:+3V3", "3V3": "power:+3V3",
    "+5V": "power:+5V", "5V": "power:+5V", "+12V": "power:+12V", "+1V8": "power:+1V8",
    "+1V2": "power:+1V2", "+2V5": "power:+2V5", "+9V": "power:+9V", "+24V": "power:+24V",
    "-5V": "power:-5V", "-12V": "power:-12V", "VBUS": "power:VBUS", "VCC": "power:VCC",
    "VDD": "power:VDD", "VBAT": "power:VBAT", "VDDA": "power:VDDA", "VIN": "power:VIN",
    "VEE": "power:VEE", "VSS": "power:VSS", "+BATT": "power:+BATT",
}


def new_uuid() -> str:
    return str(_uuid.uuid4())


def _effects(size: float = 1.27, hide: bool = False, justify: list[str] | None = None) -> list:
    eff = A("effects", A("font", A("size", num(size), num(size))))
    if justify:
        eff.append(A("justify", *[Atom(j) for j in justify]))
    if hide:
        eff.append(A("hide", Atom("yes")))
    return eff


def _prop(key: str, value: str, x: float, y: float, rot: float = 0, hide: bool = False,
          size: float = 1.27, justify: list[str] | None = None) -> list:
    p = A("property", key, value, A("at", num(x), num(y), num(rot)))
    if hide:
        p.append(A("hide", Atom("yes")))
    p.append(A("show_name", Atom("no")))
    p.append(A("do_not_autoplace", Atom("no")))
    p.append(_effects(size, justify=justify))
    return p


@dataclass
class PlacedSymbol:
    ref: str
    lib_id: str
    value: str
    x: float
    y: float
    rot: float
    mirror: str | None
    unit: int
    uuid: str
    lib_node: list
    pins: list[libs.Pin]
    node: list
    footprint: str = ""

    def pin(self, number: str) -> libs.Pin:
        for p in self.pins:
            if p.number == str(number) and p.unit in (0, self.unit):
                return p
        for p in self.pins:
            if p.name == str(number) and p.unit in (0, self.unit):
                return p
        raise KeyError(f"{self.ref}: no pin {number!r} in unit {self.unit}. "
                       f"Have: {[p.number for p in self.pins if p.unit in (0, self.unit)]}")

    def pin_pos(self, number: str) -> tuple[float, float]:
        p = self.pin(number)
        dx, dy = geom.lib_to_sch(p.x, p.y, self.rot, self.mirror)
        return (round(self.x + dx, 4), round(self.y + dy, 4))

    def pin_dir(self, number: str) -> tuple[float, float]:
        p = self.pin(number)
        return geom.pin_direction(p.angle, self.rot, self.mirror)

    def visible_pins(self) -> list[libs.Pin]:
        return [p for p in self.pins if p.unit in (0, self.unit) and not p.hidden]

    def bbox(self) -> tuple[float, float, float, float]:
        x0, y0, x1, y1 = libs.symbol_bbox(self.lib_node, self.unit)
        pts = [geom.lib_to_sch(px, py, self.rot, self.mirror) for px, py in
               ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]
        xs = [self.x + p[0] for p in pts]
        ys = [self.y + p[1] for p in pts]
        return (min(xs), min(ys), max(xs), max(ys))


class Schematic:
    def __init__(self, project_name: str, title: str = "", paper: str = "A4",
                 rev: str = "", company: str = "", date: str = "",
                 project_dir: Path | None = None, root_uuid: str | None = None,
                 sheet_path: str | None = None, page: str = "1"):
        self.project_name = project_name
        self.project_dir = Path(project_dir) if project_dir else None
        self.uuid = root_uuid or new_uuid()
        # instance path for symbols on this sheet: "/root" for the root sheet,
        # "/root/sheet-uuid" for a sub-sheet
        self.sheet_path = sheet_path or f"/{self.uuid}"
        self.page = page
        self.paper = paper
        self.title_block = {"title": title, "rev": rev, "company": company, "date": date}
        self.lib_symbols: dict[str, list] = {}
        self.items: list[list] = []
        self.symbols: dict[str, PlacedSymbol] = {}
        self.sheets: list[list] = []
        self._pwr_counter = 0
        self._flag_counter = 0

    # ------------------------------------------------------------------ #
    # symbols
    # ------------------------------------------------------------------ #
    def _ensure_lib_symbol(self, lib_id: str) -> list:
        if lib_id not in self.lib_symbols:
            self.lib_symbols[lib_id] = libs.resolve_symbol(lib_id, self.project_dir)
        return self.lib_symbols[lib_id]

    def add_symbol(self, lib_id: str, ref: str, value: str, at: tuple[float, float],
                   rot: float = 0, mirror: str | None = None, unit: int = 1,
                   footprint: str | None = None, datasheet: str = "", description: str | None = None,
                   props: dict[str, str] | None = None, dnp: bool = False, in_bom: bool = True,
                   on_board: bool = True, exclude_from_sim: bool = False,
                   in_pos_files: bool = True, ref_offset: tuple[float, float] | None = None,
                   value_offset: tuple[float, float] | None = None, hide_value: bool = False,
                   sym_uuid: str | None = None) -> PlacedSymbol:
        if ref in self.symbols and self.symbols[ref].unit == unit:
            raise ValueError(f"reference {ref} unit {unit} already placed")
        x, y = geom.snap_pt(at)
        if abs(x - at[0]) > 1e-3 or abs(y - at[1]) > 1e-3:
            raise ValueError(f"{ref}: position {at} is not on the 1.27 mm grid (nearest {x},{y})")
        lib_node = self._ensure_lib_symbol(lib_id)
        pins = libs.symbol_pins(lib_node)
        fp = footprint if footprint is not None else (sexpr.get_property(lib_node, "Footprint") or "")
        desc = description if description is not None else (sexpr.get_property(lib_node, "Description") or "")
        ds = datasheet or (sexpr.get_property(lib_node, "Datasheet") or "")
        uid = sym_uuid or new_uuid()

        node = A("symbol", A("lib_id", lib_id), A("at", num(x), num(y), num(rot)))
        if mirror:
            node.append(A("mirror", Atom(mirror)))
        node += [A("unit", num(unit)), A("body_style", num(1)),
                 A("exclude_from_sim", yn(exclude_from_sim)), A("in_bom", yn(in_bom)),
                 A("on_board", yn(on_board)), A("in_pos_files", yn(in_pos_files)),
                 A("dnp", yn(dnp)), A("uuid", uid)]
        # field placement, computed from the *placed* bounding box:
        #  - small parts (passives): reference/value stacked to the right
        #  - larger parts (ICs, connectors): reference above, value below
        is_power = libs.is_power_symbol(lib_node)
        tmp = PlacedSymbol(ref, lib_id, value, x, y, rot, mirror, unit, uid, lib_node, pins, node, fp)
        bx0, by0, bx1, by1 = tmp.bbox()
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        if is_power:
            # value (net name) sits beyond the graphic, away from the pin
            is_gnd = by1 > y + 0.5  # graphic extends below the pin for grounds at rot 0
            if ref_offset is None:
                ref_offset = (0, 0)
            if value_offset is None:
                d = (bx1 + 0.5 - x, 0) if rot % 180 == 90 else (0, (by1 + 1.27 - y) if is_gnd else (by0 - 1.27 - y))
                value_offset = d
            rjust = None  # centred (KiCad has no 'center' token; omit justify)
        elif (by1 - by0) <= 7.7 and (bx1 - bx0) <= 7.7:
            if ref_offset is None:
                ref_offset = (bx1 + 0.635 - x, cy - 1.27 - y)
            if value_offset is None:
                value_offset = (bx1 + 0.635 - x, cy + 1.27 - y)
            rjust = ["left"]
        else:
            # both above the body, left aligned: the space below is used by
            # pin stubs, labels and power symbols
            if ref_offset is None:
                ref_offset = (bx0 - x, by0 - 4.445 - y)
            if value_offset is None:
                value_offset = (bx0 - x, by0 - 1.905 - y)
            rjust = ["left"]
        rx, ry = ref_offset
        vx, vy = value_offset
        node.append(_prop("Reference", ref, x + rx, y + ry, hide=is_power, justify=rjust))
        node.append(_prop("Value", value, x + vx, y + vy, hide=hide_value, justify=rjust))
        node.append(_prop("Footprint", fp, x, y, hide=True))
        node.append(_prop("Datasheet", ds, x, y, hide=True))
        node.append(_prop("Description", desc, x, y, hide=True))
        for k, v in (props or {}).items():
            node.append(_prop(k, v, x, y, hide=True))
        for p in pins:
            if p.unit in (0, unit):
                node.append(A("pin", p.number, A("uuid", new_uuid())))
        node.append(A("instances", A("project", self.project_name,
                                     A("path", self.sheet_path, A("reference", ref), A("unit", num(unit))))))
        placed = PlacedSymbol(ref, lib_id, value, x, y, rot, mirror, unit, uid, lib_node, pins, node, fp)
        self.items.append(node)
        self.symbols[ref if unit == 1 or ref not in self.symbols else f"{ref}#{unit}"] = placed
        return placed

    # ------------------------------------------------------------------ #
    # power / flags
    # ------------------------------------------------------------------ #
    def add_power(self, net: str, at: tuple[float, float], rot: float = 0,
                  lib_id: str | None = None, value: str | None = None) -> PlacedSymbol:
        """Place a power symbol whose pin end is exactly at ``at``.

        Power symbols have their single pin at the library origin, so the
        symbol origin *is* the connection point.
        """
        lid = lib_id or POWER_SYMBOL_FOR_NET.get(net.upper(), None)
        if lid is None:
            # generic: use the +3V3 graphic (bar) but rename value to the net
            lid = "power:VCC" if not net.upper().startswith(("GND", "VSS", "-")) else "power:GND"
        self._pwr_counter += 1
        ref = f"#PWR{self._pwr_counter:03d}"
        val = value if value is not None else net
        return self.add_symbol(lid, ref, val, at, rot=rot, footprint="", in_bom=False,
                               on_board=False, in_pos_files=False)

    def add_pwr_flag(self, at: tuple[float, float], rot: float = 0) -> PlacedSymbol:
        self._flag_counter += 1
        return self.add_symbol(PWR_FLAG, f"#FLG{self._flag_counter:03d}", "PWR_FLAG", at, rot=rot,
                               footprint="", in_bom=False, on_board=False, in_pos_files=False)

    # ------------------------------------------------------------------ #
    # wires, labels, junctions
    # ------------------------------------------------------------------ #
    def add_wire(self, *pts: tuple[float, float]) -> None:
        if len(pts) < 2:
            raise ValueError("a wire needs at least two points")
        for p in pts:
            if not (geom.on_grid(p[0]) and geom.on_grid(p[1])):
                raise ValueError(f"wire point {p} is off the 1.27 mm grid")
        for a, b in zip(pts, pts[1:]):
            if a == b:
                continue
            self.items.append(A("wire", A("pts", A("xy", num(a[0]), num(a[1])), A("xy", num(b[0]), num(b[1]))),
                                A("stroke", A("width", num(0)), A("type", Atom("default"))),
                                A("uuid", new_uuid())))

    def add_bus(self, *pts: tuple[float, float]) -> None:
        for a, b in zip(pts, pts[1:]):
            self.items.append(A("bus", A("pts", A("xy", num(a[0]), num(a[1])), A("xy", num(b[0]), num(b[1]))),
                                A("stroke", A("width", num(0)), A("type", Atom("default"))),
                                A("uuid", new_uuid())))

    def add_junction(self, at: tuple[float, float]) -> None:
        self.items.append(A("junction", A("at", num(at[0]), num(at[1])), A("diameter", num(0)),
                            A("color", num(0), num(0), num(0), num(0)), A("uuid", new_uuid())))

    def add_no_connect(self, at: tuple[float, float]) -> None:
        self.items.append(A("no_connect", A("at", num(at[0]), num(at[1])), A("uuid", new_uuid())))

    def _label(self, kind: str, text: str, at: tuple[float, float], rot: float,
               shape: str | None, size: float) -> None:
        # justification follows the text direction so the label hangs off the wire end
        just = {0: ["left", "bottom"], 90: ["left", "bottom"], 180: ["right", "bottom"], 270: ["right", "bottom"]}[int(rot) % 360]
        node = A(kind, text)
        if shape:
            node.append(A("shape", Atom(shape)))
        node.append(A("at", num(at[0]), num(at[1]), num(rot)))
        node.append(_effects(size, justify=just))
        node.append(A("uuid", new_uuid()))
        if kind == "global_label":
            node.append(A("property", "Intersheetrefs", "${INTERSHEET_REFS}",
                          A("at", num(at[0]), num(at[1]), num(0)), A("hide", Atom("yes")),
                          A("show_name", Atom("no")), A("do_not_autoplace", Atom("no")), _effects(size)))
        self.items.append(node)

    def add_label(self, text: str, at: tuple[float, float], rot: float = 0, size: float = 1.27) -> None:
        self._label("label", text, at, rot, None, size)

    def add_global_label(self, text: str, at: tuple[float, float], rot: float = 0,
                         shape: str = "bidirectional", size: float = 1.27) -> None:
        self._label("global_label", text, at, rot, shape, size)

    def add_hier_label(self, text: str, at: tuple[float, float], rot: float = 0,
                       shape: str = "bidirectional", size: float = 1.27) -> None:
        self._label("hierarchical_label", text, at, rot, shape, size)

    def add_text(self, text: str, at: tuple[float, float], size: float = 1.27, rot: float = 0) -> None:
        self.items.append(A("text", text, A("exclude_from_sim", Atom("no")),
                            A("at", num(at[0]), num(at[1]), num(rot)),
                            _effects(size, justify=["left", "bottom"]), A("uuid", new_uuid())))

    def add_rect(self, start: tuple[float, float], end: tuple[float, float], width: float = 0.254,
                 dashed: bool = True) -> None:
        self.items.append(A("rectangle", A("start", num(start[0]), num(start[1])),
                            A("end", num(end[0]), num(end[1])),
                            A("stroke", A("width", num(width)), A("type", Atom("dash" if dashed else "solid"))),
                            A("fill", A("type", Atom("none"))), A("uuid", new_uuid())))

    # ------------------------------------------------------------------ #
    # convenience connections
    # ------------------------------------------------------------------ #
    @staticmethod
    def _stub_end(pos: tuple[float, float], d: tuple[float, float], length: float) -> tuple[float, float]:
        return (round(pos[0] + d[0] * length, 4), round(pos[1] + d[1] * length, 4))

    @staticmethod
    def _rot_for_dir(d: tuple[float, float]) -> float:
        """Label rotation so text reads away from the symbol."""
        if d[0] > 0:
            return 0
        if d[0] < 0:
            return 180
        return 90 if d[1] < 0 else 270

    def connect_label(self, sym: PlacedSymbol, pin: str, net: str, stub: float = 2.54,
                      global_: bool = False) -> tuple[float, float]:
        """Short wire out of the pin, then a label at its end. Returns the end."""
        pos = sym.pin_pos(pin)
        d = sym.pin_dir(pin)
        end = self._stub_end(pos, d, stub) if stub else pos
        if stub:
            self.add_wire(pos, end)
        rot = self._rot_for_dir(d)
        if global_:
            self.add_global_label(net, end, rot)
        else:
            self.add_label(net, end, rot)
        return end

    def connect_power(self, sym: PlacedSymbol, pin: str, net: str, stub: float = 2.54,
                      lib_id: str | None = None) -> PlacedSymbol:
        """Short wire out of the pin, then a power symbol at its end pointing away."""
        pos = sym.pin_pos(pin)
        d = sym.pin_dir(pin)
        end = self._stub_end(pos, d, stub) if stub else pos
        lid = lib_id or POWER_SYMBOL_FOR_NET.get(net.upper(), None)
        is_gnd = (lid or "").endswith(("GND", "GNDA", "GNDD", "GNDPWR", "GNDREF", "Earth", "VSS", "VEE")) or \
            net.upper().startswith(("GND", "VSS", "-"))
        if d[1] == 0:
            # horizontal pin: run the stub out, then turn up (supply) or down
            # (ground) so the power symbol stays upright and readable
            tail = (end[0], round(end[1] + (2.54 if is_gnd else -2.54), 4))
            self.add_wire(pos, end, tail)
            return self.add_power(net, tail, rot=0, lib_id=lid)
        if stub:
            self.add_wire(pos, end)
        # vertical pin: symbol points away from the part; grounds hang down at
        # rot 0, supplies stand up at rot 0, so flip when the pin faces the other way
        rot = 0 if (d[1] > 0) == is_gnd else 180
        return self.add_power(net, end, rot=rot, lib_id=lid)

    def connect_nc(self, sym: PlacedSymbol, pin: str) -> None:
        self.add_no_connect(sym.pin_pos(pin))

    def wire_pins(self, a: PlacedSymbol, pin_a: str, b: PlacedSymbol, pin_b: str,
                  style: str = "auto") -> None:
        """Wire two pins with an L/Z-shaped Manhattan path (no obstacle avoidance)."""
        p = a.pin_pos(pin_a)
        q = b.pin_pos(pin_b)
        if p[0] == q[0] or p[1] == q[1]:
            self.add_wire(p, q)
            return
        da = a.pin_dir(pin_a)
        if style == "auto":
            style = "hv" if abs(da[0]) > 0 else "vh"
        if style == "hv":
            mid = (q[0], p[1])
            self.add_wire(p, mid, q)
        elif style == "vh":
            mid = (p[0], q[1])
            self.add_wire(p, mid, q)
        else:  # z: horizontal, vertical, horizontal
            mx = geom.snap((p[0] + q[0]) / 2)
            self.add_wire(p, (mx, p[1]), (mx, q[1]), q)

    # ------------------------------------------------------------------ #
    # hierarchical sheets
    # ------------------------------------------------------------------ #
    def add_sheet(self, name: str, filename: str, at: tuple[float, float], size: tuple[float, float],
                  pins: list[tuple[str, str, str]] | None = None, sheet_uuid: str | None = None,
                  page: str | None = None) -> str:
        """Add a hierarchical sheet symbol. ``pins`` = [(name, shape, side)] where side
        is 'left'|'right'|'top'|'bottom'; pins are spaced 2.54 mm. Returns sheet uuid."""
        uid = sheet_uuid or new_uuid()
        x, y = geom.snap_pt(at)
        w, h = size
        node = A("sheet", A("at", num(x), num(y)), A("size", num(w), num(h)),
                 A("exclude_from_sim", Atom("no")), A("in_bom", Atom("yes")), A("on_board", Atom("yes")),
                 A("dnp", Atom("no")), A("fields_autoplaced", Atom("yes")),
                 A("stroke", A("width", num(0.1524)), A("type", Atom("solid"))),
                 A("fill", A("color", num(0), num(0), num(0), num(0))), A("uuid", uid),
                 _prop("Sheetname", name, x, y - 0.7116, justify=["left", "bottom"]),
                 _prop("Sheetfile", filename, x, y + h + 0.5846, justify=["left", "top"]))
        counters = {"left": 0, "right": 0, "top": 0, "bottom": 0}
        for pname, shape, side in (pins or []):
            i = counters[side]
            counters[side] += 1
            if side == "left":
                px, py, rot, just = x, y + 2.54 * (i + 1), 180, ["left"]
            elif side == "right":
                px, py, rot, just = x + w, y + 2.54 * (i + 1), 0, ["right"]
            elif side == "top":
                px, py, rot, just = x + 2.54 * (i + 1), y, 90, ["left"]
            else:
                px, py, rot, just = x + 2.54 * (i + 1), y + h, 270, ["right"]
            node.append(A("pin", pname, Atom(shape), A("at", num(px), num(py), num(rot)),
                          A("uuid", new_uuid()), _effects(1.27, justify=just)))
        pg = page or str(len(self.sheets) + 2)
        node.append(A("instances", A("project", self.project_name,
                                     A("path", self.sheet_path, A("page", pg)))))
        self.sheets.append(node)
        self.items.append(node)
        return uid

    def sheet_pin_pos(self, sheet_uuid: str, pin_name: str) -> tuple[float, float, float]:
        for s in self.sheets:
            if sexpr.child(s, "uuid")[1] == sheet_uuid:
                for p in sexpr.children(s, "pin"):
                    if p[1] == pin_name:
                        at = sexpr.floats(sexpr.child(p, "at"))
                        return (at[0], at[1], at[2])
        raise KeyError(f"sheet pin {pin_name} not found")

    # ------------------------------------------------------------------ #
    # output
    # ------------------------------------------------------------------ #
    def to_sexpr(self) -> list:
        root = A("kicad_sch", A("version", num(SCH_VERSION)), A("generator", GENERATOR),
                 A("generator_version", GENERATOR_VERSION), A("uuid", self.uuid), A("paper", self.paper))
        tb = A("title_block")
        for k in ("title", "date", "rev", "company"):
            if self.title_block.get(k):
                tb.append(A(k, self.title_block[k]))
        if len(tb) > 1:
            root.append(tb)
        ls = A("lib_symbols")
        for lid in sorted(self.lib_symbols):
            ls.append(self.lib_symbols[lid])
        root.append(ls)
        order = {"junction": 0, "no_connect": 1, "bus_entry": 2, "wire": 3, "bus": 3, "polyline": 4,
                 "rectangle": 4, "text": 5, "label": 6, "global_label": 7, "hierarchical_label": 8,
                 "symbol": 9, "sheet": 10}
        for item in sorted(self.items, key=lambda n: order.get(str(n[0]), 99)):
            root.append(item)
        if self.sheet_path == f"/{self.uuid}":
            root.append(A("sheet_instances", A("path", "/", A("page", self.page))))
        return root

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        sexpr.dump(self.to_sexpr(), path)
        return path

    # ------------------------------------------------------------------ #
    # placement helpers
    # ------------------------------------------------------------------ #
    def symbol_footprint_size(self, lib_id: str, unit: int = 1) -> tuple[float, float]:
        node = self._ensure_lib_symbol(lib_id)
        x0, y0, x1, y1 = libs.symbol_bbox(node, unit)
        return (x1 - x0, y1 - y0)
