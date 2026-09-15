"""Write KiCad 10 boards (.kicad_pcb) from Python.

Footprints are copied verbatim from their library file and given the board
specific extras (position, layer, reference/value, net names on pads, the
schematic ``path`` so "Update PCB from Schematic" recognises them).

KiCad 10 boards carry net *names* on pads/tracks/zones; there is no
numbered net table anymore.
"""
from __future__ import annotations

import copy
import math
import uuid as _uuid
from dataclasses import dataclass
from pathlib import Path

from . import geom, libs, sexpr
from .sexpr import A, Atom, num, yn

PCB_VERSION = 20260206
GENERATOR = "pcbnew"
GENERATOR_VERSION = "10.0"

STD_LAYERS_2 = [
    (0, "F.Cu", "signal"), (2, "B.Cu", "signal"),
    (9, "F.Adhes", "user", "F.Adhesive"), (11, "B.Adhes", "user", "B.Adhesive"),
    (13, "F.Paste", "user"), (15, "B.Paste", "user"),
    (5, "F.SilkS", "user", "F.Silkscreen"), (7, "B.SilkS", "user", "B.Silkscreen"),
    (1, "F.Mask", "user"), (3, "B.Mask", "user"),
    (17, "Dwgs.User", "user", "User.Drawings"), (19, "Cmts.User", "user", "User.Comments"),
    (21, "Eco1.User", "user", "User.Eco1"), (23, "Eco2.User", "user", "User.Eco2"),
    (25, "Edge.Cuts", "user"), (27, "Margin", "user"),
    (31, "F.CrtYd", "user", "F.Courtyard"), (29, "B.CrtYd", "user", "B.Courtyard"),
    (35, "F.Fab", "user"), (33, "B.Fab", "user"),
]


def new_uuid() -> str:
    return str(_uuid.uuid4())


def _inner_layers(count: int) -> list[tuple]:
    """Copper layer ids for inner layers (In1.Cu = 4, In2.Cu = 6, ...)."""
    return [(4 + 2 * i, f"In{i+1}.Cu", "signal") for i in range(count - 2)]


def _stackup(copper: int, thickness: float, mask_color: str = "Green", silk_color: str = "White") -> list:
    st = A("stackup")
    st.append(A("layer", "F.SilkS", A("type", "Top Silk Screen"), A("color", silk_color)))
    st.append(A("layer", "F.Paste", A("type", "Top Solder Paste")))
    st.append(A("layer", "F.Mask", A("type", "Top Solder Mask"), A("color", mask_color), A("thickness", num(0.01))))
    cu_t = 0.035
    n_diel = copper - 1
    diel_total = thickness - copper * cu_t - 0.02
    diel_each = round(diel_total / n_diel, 4)
    names = ["F.Cu"] + [f"In{i+1}.Cu" for i in range(copper - 2)] + ["B.Cu"]
    for i, nm in enumerate(names):
        st.append(A("layer", nm, A("type", "copper"), A("thickness", num(cu_t))))
        if i < n_diel:
            kind = "core" if (copper == 2 or i % 2 == 1) else "prepreg"
            st.append(A("layer", f"dielectric {i+1}", A("type", kind), A("thickness", num(diel_each)),
                        A("material", "FR4"), A("epsilon_r", num(4.5)), A("loss_tangent", num(0.02))))
    st.append(A("layer", "B.Mask", A("type", "Bottom Solder Mask"), A("color", mask_color), A("thickness", num(0.01))))
    st.append(A("layer", "B.Paste", A("type", "Bottom Solder Paste")))
    st.append(A("layer", "B.SilkS", A("type", "Bottom Silk Screen"), A("color", silk_color)))
    st.append(A("copper_finish", "None"))
    st.append(A("dielectric_constraints", Atom("no")))
    return st


@dataclass
class PlacedFootprint:
    ref: str
    fp_id: str
    x: float
    y: float
    rot: float
    layer: str          # "F.Cu" or "B.Cu"
    node: list
    pads: dict[str, dict]

    @property
    def back(self) -> bool:
        return self.layer == "B.Cu"

    def pad_pos(self, number: str) -> tuple[float, float]:
        p = self.pads[str(number)]
        px, py = p["at"][0], p["at"][1]
        if self.back:
            py = -py
        dx, dy = geom.rot_ccw(px, py, self.rot)
        return (round(self.x + dx, 4), round(self.y + dy, 4))

    def bbox(self) -> tuple[float, float, float, float]:
        """Courtyard bounding box in board coordinates (falls back to pads)."""
        pts: list[tuple[float, float]] = []
        for c in self.node:
            if isinstance(c, list) and str(c[0]) in ("fp_line", "fp_rect", "fp_poly", "fp_circle", "fp_arc"):
                layer = sexpr.child(c, "layer")
                if layer is None or not str(layer[1]).endswith("CrtYd"):
                    continue
                if str(c[0]) == "fp_circle":
                    ctr = sexpr.floats(sexpr.child(c, "center"))
                    end = sexpr.floats(sexpr.child(c, "end"))
                    r = math.hypot(end[0] - ctr[0], end[1] - ctr[1])
                    pts += [(ctr[0] - r, ctr[1] - r), (ctr[0] + r, ctr[1] + r)]
                    continue
                for tok in ("start", "mid", "end"):
                    n = sexpr.child(c, tok)
                    if n:
                        pts.append(tuple(sexpr.floats(n)[:2]))
                for xy in sexpr.find_all(c, "xy"):
                    pts.append(tuple(sexpr.floats(xy)[:2]))
        if not pts:
            for p in self.pads.values():
                w, h = p["size"][0] / 2, p["size"][1] / 2
                pts += [(p["at"][0] - w, p["at"][1] - h), (p["at"][0] + w, p["at"][1] + h)]
        out = []
        for px, py in pts:
            if self.back:
                py = -py
            dx, dy = geom.rot_ccw(px, py, self.rot)
            out.append((self.x + dx, self.y + dy))
        xs = [p[0] for p in out]; ys = [p[1] for p in out]
        return (min(xs), min(ys), max(xs), max(ys))


class Board:
    def __init__(self, copper_layers: int = 2, thickness: float = 1.6, paper: str = "A4",
                 title: str = "", rev: str = "", company: str = "", project_dir: Path | None = None,
                 mask_color: str = "Green", silk_color: str = "White"):
        if copper_layers not in (2, 4, 6, 8):
            raise ValueError("copper_layers must be 2, 4, 6 or 8")
        self.copper_layers = copper_layers
        self.thickness = thickness
        self.paper = paper
        self.title_block = {"title": title, "rev": rev, "company": company}
        self.project_dir = Path(project_dir) if project_dir else None
        self.mask_color = mask_color
        self.silk_color = silk_color
        self.footprints: dict[str, PlacedFootprint] = {}
        self.items: list[list] = []
        self.nets: set[str] = set()
        self.aux_origin: tuple[float, float] | None = None
        self.design_rules: dict = {}
        self.notes: list[str] = []

    # ------------------------------------------------------------------ #
    def copper_layer_names(self) -> list[str]:
        return ["F.Cu"] + [f"In{i+1}.Cu" for i in range(self.copper_layers - 2)] + ["B.Cu"]

    def add_net(self, name: str) -> None:
        if name:
            self.nets.add(name)

    # ------------------------------------------------------------------ #
    # footprints
    # ------------------------------------------------------------------ #
    def add_footprint(self, fp_id: str, ref: str, value: str, at: tuple[float, float], rot: float = 0,
                      layer: str = "F.Cu", pad_nets: dict[str, str] | None = None,
                      sch_path: str | None = None, sheetname: str = "/", sheetfile: str = "",
                      pin_types: dict[str, str] | None = None, dnp: bool = False,
                      exclude_from_bom: bool = False, exclude_from_pos: bool = False,
                      props: dict[str, str] | None = None, fp_node: list | None = None) -> PlacedFootprint:
        if ref in self.footprints:
            raise ValueError(f"{ref} already on board")
        node = copy.deepcopy(fp_node) if fp_node is not None else libs.load_footprint(fp_id, self.project_dir)
        node[1] = fp_id
        # strip library-only header items
        node[:] = [c for c in node if not (isinstance(c, list) and str(c[0]) in
                                           ("version", "generator", "generator_version", "layer", "uuid", "at",
                                            "path", "sheetname", "sheetfile", "embedded_fonts"))]
        node.append(A("embedded_fonts", Atom("no")))
        back = layer == "B.Cu"
        x, y = at
        head = [A("layer", layer), A("uuid", new_uuid()), A("at", num(x), num(y), num(rot))]
        # insert after the name
        node[2:2] = head
        # properties: replace Reference/Value; keep others; ensure Datasheet/Description exist
        ref_prop = val_prop = None
        for c in sexpr.children(node, "property"):
            if c[1] == "Reference":
                ref_prop = c
            elif c[1] == "Value":
                val_prop = c
        if ref_prop is None:
            ref_prop = A("property", "Reference", "REF**", A("at", num(0), num(-2), num(0)), A("layer", "F.SilkS"))
            node.append(ref_prop)
        if val_prop is None:
            val_prop = A("property", "Value", value, A("at", num(0), num(2), num(0)), A("layer", "F.Fab"))
            node.append(val_prop)
        ref_prop[2] = ref
        val_prop[2] = value
        have = {str(p[1]) for p in sexpr.children(node, "property")}
        for key in ("Datasheet", "Description"):
            if key not in have:
                idx = node.index(val_prop) + 1
                node.insert(idx, A("property", key, "", A("at", num(0), num(0), num(0)), A("layer", "F.Fab"),
                                   A("hide", Atom("yes")), A("uuid", new_uuid()),
                                   A("effects", A("font", A("size", num(1.27), num(1.27))))))
        for p in sexpr.children(node, "property"):
            if sexpr.child(p, "uuid") is None:
                p.append(A("uuid", new_uuid()))
        for k, v in (props or {}).items():
            node.append(A("property", k, v, A("at", num(0), num(0), num(0)), A("layer", "F.Fab"),
                          A("hide", Atom("yes")), A("uuid", new_uuid()),
                          A("effects", A("font", A("size", num(1.27), num(1.27))))))
        if sch_path:
            node.append(A("path", sch_path))
            node.append(A("sheetname", sheetname))
            node.append(A("sheetfile", sheetfile))
        attr = sexpr.child(node, "attr")
        if attr is None:
            attr = A("attr", Atom("smd"))
            node.append(attr)
        for flag, on in (("dnp", dnp), ("exclude_from_bom", exclude_from_bom), ("exclude_from_pos_files", exclude_from_pos)):
            if on and Atom(flag) not in attr:
                attr.append(Atom(flag))
        # pads: nets and pin types
        pads: dict[str, dict] = {}
        for pad in sexpr.children(node, "pad"):
            number = str(pad[1])
            at_ = sexpr.child(pad, "at")
            size = sexpr.child(pad, "size")
            pads[number] = {"at": sexpr.floats(at_)[:2] if at_ else [0, 0],
                            "size": sexpr.floats(size) if size else [0, 0], "type": str(pad[2])}
            net = (pad_nets or {}).get(number)
            sexpr.remove_children(pad, "net")
            sexpr.remove_children(pad, "pintype")
            if net:
                self.add_net(net)
                pad.append(A("net", net))
            if pin_types and number in pin_types:
                pad.append(A("pintype", pin_types[number]))
            if sexpr.child(pad, "uuid") is None:
                pad.append(A("uuid", new_uuid()))
        if back:
            self._flip_node(node)
        # Pads and text carry the footprint's rotation in their own (at x y rot);
        # positions stay relative and unrotated. On the back side KiCad stores
        # text angles as rotation + 180 (verified against pcbnew 10.0.6).
        for c in node:
            if isinstance(c, list) and str(c[0]) in ("pad", "property", "fp_text"):
                at_ = sexpr.child(c, "at")
                if at_ is None:
                    continue
                v = sexpr.floats(at_)
                own = v[2] if len(v) > 2 else 0.0
                ang = own + rot + (180 if (back and str(c[0]) != "pad") else 0)
                ang = ang % 360
                if ang == 0:
                    at_[1:] = [num(v[0]), num(v[1])]
                else:
                    at_[1:] = [num(v[0]), num(v[1]), num(ang)]
        # every graphic item needs a uuid
        for c in node:
            if isinstance(c, list) and str(c[0]).startswith("fp_") and sexpr.child(c, "uuid") is None:
                c.append(A("uuid", new_uuid()))
        # KiCad order: ... pads, embedded_fonts, model(s)
        ef = sexpr.child(node, "embedded_fonts")
        models = sexpr.children(node, "model")
        for m in models:
            node.remove(m)
        if ef is not None:
            node.remove(ef)
            node.append(ef)
        node.extend(models)
        placed = PlacedFootprint(ref, fp_id, x, y, rot, layer, node, pads)
        self.footprints[ref] = placed
        self.items.append(node)
        return placed

    @staticmethod
    def _flip_node(node: list) -> None:
        """Mirror a footprint to the back: swap F./B. layers and negate Y."""
        def swap(layer: str) -> str:
            if layer.startswith("F."):
                return "B." + layer[2:]
            if layer.startswith("B."):
                return "F." + layer[2:]
            return layer

        for lay in sexpr.find_all(node, "layer"):
            if lay is node[2]:
                continue  # the footprint's own side is set by the caller
            if len(lay) > 1 and isinstance(lay[1], str):
                lay[1] = swap(lay[1])
        for lays in sexpr.find_all(node, "layers"):
            lays[1:] = [swap(str(v)) if not str(v).startswith("*") else v for v in lays[1:]]
        for tok in ("start", "end", "center", "mid", "xy"):
            for n in sexpr.find_all(node, tok):
                if len(n) >= 3:
                    n[2] = num(-float(n[2]))
        fp_at = node[4]
        for c in node:
            if not isinstance(c, list) or str(c[0]) not in ("pad", "property", "fp_text", "model"):
                continue
            at_ = sexpr.child(c, "at")
            if at_ is None or at_ is fp_at:
                continue
            v = sexpr.floats(at_)
            if len(v) >= 2:
                at_[2] = num(-v[1])
            if str(c[0]) in ("property", "fp_text"):
                eff = sexpr.child(c, "effects")
                if eff is None:
                    eff = A("effects", A("font", A("size", num(1), num(1)), A("thickness", num(0.15))))
                    c.append(eff)
                j = sexpr.child(eff, "justify")
                if j is None:
                    eff.append(A("justify", Atom("mirror")))
                elif Atom("mirror") not in j:
                    j.append(Atom("mirror"))

    # ------------------------------------------------------------------ #
    # outline & graphics
    # ------------------------------------------------------------------ #
    def outline_rect(self, x0: float, y0: float, w: float, h: float, radius: float = 0.0) -> None:
        if radius <= 0:
            self.items.append(A("gr_rect", A("start", num(x0), num(y0)), A("end", num(x0 + w), num(y0 + h)),
                                A("stroke", A("width", num(0.05)), A("type", Atom("default"))),
                                A("fill", Atom("no")), A("layer", "Edge.Cuts"), A("uuid", new_uuid())))
            return
        r = radius
        x1, y1 = x0 + w, y0 + h
        lines = [((x0 + r, y0), (x1 - r, y0)), ((x1, y0 + r), (x1, y1 - r)),
                 ((x1 - r, y1), (x0 + r, y1)), ((x0, y1 - r), (x0, y0 + r))]
        for a, b in lines:
            self.gr_line(a, b, "Edge.Cuts", 0.05)
        # arcs: (start, mid, end) counter-clockwise in Y-down = clockwise visually; KiCad only needs the 3 points
        k = r * (1 - math.sqrt(0.5))
        arcs = [((x1 - r, y0), (x1 - k, y0 + k), (x1, y0 + r)),
                ((x1, y1 - r), (x1 - k, y1 - k), (x1 - r, y1)),
                ((x0 + r, y1), (x0 + k, y1 - k), (x0, y1 - r)),
                ((x0, y0 + r), (x0 + k, y0 + k), (x0 + r, y0))]
        for s, m, e in arcs:
            self.items.append(A("gr_arc", A("start", num(s[0]), num(s[1])), A("mid", num(m[0]), num(m[1])),
                                A("end", num(e[0]), num(e[1])),
                                A("stroke", A("width", num(0.05)), A("type", Atom("default"))),
                                A("layer", "Edge.Cuts"), A("uuid", new_uuid())))

    def outline_polygon(self, pts: list[tuple[float, float]]) -> None:
        for a, b in zip(pts, pts[1:] + pts[:1]):
            self.gr_line(a, b, "Edge.Cuts", 0.05)

    def gr_line(self, a: tuple[float, float], b: tuple[float, float], layer: str, width: float = 0.15) -> None:
        self.items.append(A("gr_line", A("start", num(a[0]), num(a[1])), A("end", num(b[0]), num(b[1])),
                            A("stroke", A("width", num(width)), A("type", Atom("default"))),
                            A("layer", layer), A("uuid", new_uuid())))

    def gr_circle(self, center: tuple[float, float], radius: float, layer: str, width: float = 0.15) -> None:
        self.items.append(A("gr_circle", A("center", num(center[0]), num(center[1])),
                            A("end", num(center[0] + radius), num(center[1])),
                            A("stroke", A("width", num(width)), A("type", Atom("default"))),
                            A("fill", Atom("no")), A("layer", layer), A("uuid", new_uuid())))

    def gr_text(self, text: str, at: tuple[float, float], layer: str = "F.SilkS", size: float = 1.0,
                thickness: float = 0.15, rot: float = 0, mirror: bool = False) -> None:
        eff = A("effects", A("font", A("size", num(size), num(size)), A("thickness", num(thickness))))
        if mirror or layer.startswith("B."):
            eff.append(A("justify", Atom("mirror")))
        self.items.append(A("gr_text", text, A("at", num(at[0]), num(at[1]), num(rot)), A("layer", layer),
                            A("uuid", new_uuid()), eff))

    def mounting_hole(self, ref: str, at: tuple[float, float], fp_id: str = "MountingHole:MountingHole_3.2mm_M3") -> PlacedFootprint:
        f = self.add_footprint(fp_id, ref, "MountingHole", at, exclude_from_bom=True, exclude_from_pos=True)
        # no silkscreen reference on holes: it only ends up off the board edge
        for p in sexpr.children(f.node, "property"):
            if p[1] == "Reference" and sexpr.child(p, "hide") is None:
                p.insert(4, A("hide", Atom("yes")))
        return f

    # ------------------------------------------------------------------ #
    # copper
    # ------------------------------------------------------------------ #
    def track(self, a: tuple[float, float], b: tuple[float, float], net: str, width: float = 0.25,
              layer: str = "F.Cu") -> None:
        self.add_net(net)
        self.items.append(A("segment", A("start", num(a[0]), num(a[1])), A("end", num(b[0]), num(b[1])),
                            A("width", num(width)), A("layer", layer), A("net", net), A("uuid", new_uuid())))

    def route(self, pts: list[tuple[float, float]], net: str, width: float = 0.25, layer: str = "F.Cu") -> None:
        for a, b in zip(pts, pts[1:]):
            if a != b:
                self.track(a, b, net, width, layer)

    def via(self, at: tuple[float, float], net: str, size: float = 0.6, drill: float = 0.3,
            layers: tuple[str, str] = ("F.Cu", "B.Cu")) -> None:
        self.add_net(net)
        self.items.append(A("via", A("at", num(at[0]), num(at[1])), A("size", num(size)), A("drill", num(drill)),
                            A("layers", layers[0], layers[1]), A("net", net), A("uuid", new_uuid())))

    def zone(self, net: str, layer: str, pts: list[tuple[float, float]], priority: int = 0,
             clearance: float = 0.3, min_thickness: float = 0.25, thermal_gap: float = 0.3,
             thermal_bridge: float = 0.4, connect: str = "thermal", name: str = "") -> None:
        """Unfilled zone polygon. Fill happens in KiCad (or via fill_zones())."""
        self.add_net(net)
        z = A("zone", A("net", net), A("layer", layer), A("uuid", new_uuid()))
        if name:
            z.append(A("name", name))
        z.append(A("hatch", Atom("edge"), num(0.5)))
        if priority:
            z.append(A("priority", num(priority)))
        cp = A("connect_pads", A("clearance", num(clearance)))
        if connect != "thermal":
            cp.insert(1, Atom({"solid": "yes", "none": "no", "thru_hole_only": "thru_hole_only"}[connect]))
        z.append(cp)
        z.append(A("min_thickness", num(min_thickness)))
        z.append(A("fill", Atom("yes"), A("thermal_gap", num(thermal_gap)), A("thermal_bridge_width", num(thermal_bridge)),
                   A("island_removal_mode", num(0))))
        poly = A("polygon", A("pts", *[A("xy", num(p[0]), num(p[1])) for p in pts]))
        z.append(poly)
        self.items.append(z)

    def keepout(self, layer_list: list[str], pts: list[tuple[float, float]], tracks: bool = True,
                vias: bool = True, copperpour: bool = True, footprints: bool = False) -> None:
        z = A("zone", A("net", ""), A("layers", *layer_list), A("uuid", new_uuid()), A("hatch", Atom("edge"), num(0.5)),
              A("connect_pads", A("clearance", num(0))), A("min_thickness", num(0.25)),
              A("keepout", A("tracks", Atom("not_allowed" if tracks else "allowed")),
                A("vias", Atom("not_allowed" if vias else "allowed")), A("pads", Atom("allowed")),
                A("copperpour", Atom("not_allowed" if copperpour else "allowed")),
                A("footprints", Atom("not_allowed" if footprints else "allowed"))),
              A("fill", A("thermal_gap", num(0.5)), A("thermal_bridge_width", num(0.5))),
              A("polygon", A("pts", *[A("xy", num(p[0]), num(p[1])) for p in pts])))
        self.items.append(z)

    # ------------------------------------------------------------------ #
    # output
    # ------------------------------------------------------------------ #
    def _layers_node(self) -> list:
        n = A("layers")
        layers = [STD_LAYERS_2[0]] + _inner_layers(self.copper_layers) + [STD_LAYERS_2[1]] + STD_LAYERS_2[2:]
        for entry in layers:
            row = A(str(entry[0]), entry[1], Atom(entry[2]))
            row[0] = Atom(str(entry[0]))
            if len(entry) > 3:
                row.append(entry[3])
            n.append(row)
        return n

    def _setup_node(self) -> list:
        s = A("setup", _stackup(self.copper_layers, self.thickness, self.mask_color, self.silk_color),
              A("pad_to_mask_clearance", num(0)), A("allow_soldermask_bridges_in_footprints", Atom("no")),
              A("tenting", A("front", Atom("yes")), A("back", Atom("yes"))),
              A("covering", A("front", Atom("no")), A("back", Atom("no"))),
              A("plugging", A("front", Atom("no")), A("back", Atom("no"))),
              A("capping", Atom("no")), A("filling", Atom("no")))
        if self.aux_origin:
            s.append(A("aux_axis_origin", num(self.aux_origin[0]), num(self.aux_origin[1])))
        s.append(A("pcbplotparams", A("layerselection", Atom("0x00000000_00000000_00000030_80000001")),
                   A("plot_on_all_layers_selection", Atom("0x00000000_00000000_00000000_00000000")),
                   A("disableapertmacros", Atom("no")), A("usegerberextensions", Atom("no")),
                   A("usegerberattributes", Atom("yes")), A("usegerberadvancedattributes", Atom("yes")),
                   A("creategerberjobfile", Atom("yes")), A("dashed_line_dash_ratio", num(12)),
                   A("dashed_line_gap_ratio", num(3)), A("svgprecision", num(4)), A("plotframeref", Atom("no")),
                   A("mode", num(1)), A("useauxorigin", Atom("no")), A("pdf_front_fp_property_popups", Atom("yes")),
                   A("pdf_back_fp_property_popups", Atom("yes")), A("pdf_metadata", Atom("yes")),
                   A("pdf_single_document", Atom("no")), A("dxfpolygonmode", Atom("yes")),
                   A("dxfimperialunits", Atom("yes")), A("dxfusepcbnewfont", Atom("yes")),
                   A("psnegative", Atom("no")), A("psa4output", Atom("no")), A("plot_black_and_white", Atom("yes")),
                   A("sketchpadsonfab", Atom("no")), A("plotpadnumbers", Atom("no")), A("hidednponfab", Atom("no")),
                   A("sketchdnponfab", Atom("yes")), A("crossoutdnponfab", Atom("yes")),
                   A("subtractmaskfromsilk", Atom("no")), A("outputformat", num(1)), A("mirror", Atom("no")),
                   A("drillshape", num(1)), A("scaleselection", num(1)), A("outputdirectory", "")))
        return s

    def to_sexpr(self) -> list:
        root = A("kicad_pcb", A("version", num(PCB_VERSION)), A("generator", GENERATOR),
                 A("generator_version", GENERATOR_VERSION),
                 A("general", A("thickness", num(self.thickness)), A("legacy_teardrops", Atom("no"))),
                 A("paper", self.paper))
        tb = A("title_block")
        for k in ("title", "rev", "company"):
            if self.title_block.get(k):
                tb.append(A(k, self.title_block[k]))
        if len(tb) > 1:
            root.append(tb)
        root.append(self._layers_node())
        root.append(self._setup_node())
        order = {"footprint": 0, "gr_line": 1, "gr_arc": 1, "gr_rect": 1, "gr_circle": 1, "gr_poly": 1,
                 "gr_text": 2, "segment": 3, "via": 4, "zone": 5}
        for item in sorted(self.items, key=lambda n: order.get(str(n[0]), 99)):
            root.append(item)
        root.append(A("embedded_fonts", Atom("no")))
        return root

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        sexpr.dump(self.to_sexpr(), path)
        return path
