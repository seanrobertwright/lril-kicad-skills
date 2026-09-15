"""Create a minimal KiCad 10 project file (.kicad_pro) and local lib tables."""
from __future__ import annotations

import json
from pathlib import Path


FAB_RULES = {
    # conservative "standard service" capabilities; override per fab in the spec
    "generic": {"min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.5,
                "min_via_annular_width": 0.1, "min_through_hole_diameter": 0.3, "min_hole_to_hole": 0.25,
                "min_hole_clearance": 0.25, "min_copper_edge_clearance": 0.3, "min_silk_clearance": 0.0,
                "min_text_height": 0.8, "min_text_thickness": 0.08},
    "jlcpcb": {"min_clearance": 0.127, "min_track_width": 0.127, "min_via_diameter": 0.45,
               "min_via_annular_width": 0.075, "min_through_hole_diameter": 0.3, "min_hole_to_hole": 0.25,
               "min_hole_clearance": 0.25, "min_copper_edge_clearance": 0.3, "min_silk_clearance": 0.0,
               "min_text_height": 0.8, "min_text_thickness": 0.1},
    "pcbway": {"min_clearance": 0.15, "min_track_width": 0.15, "min_via_diameter": 0.45,
               "min_via_annular_width": 0.075, "min_through_hole_diameter": 0.3, "min_hole_to_hole": 0.25,
               "min_hole_clearance": 0.25, "min_copper_edge_clearance": 0.3, "min_silk_clearance": 0.0,
               "min_text_height": 0.8, "min_text_thickness": 0.1},
    "oshpark": {"min_clearance": 0.152, "min_track_width": 0.152, "min_via_diameter": 0.508,
                "min_via_annular_width": 0.127, "min_through_hole_diameter": 0.254, "min_hole_to_hole": 0.25,
                "min_hole_clearance": 0.25, "min_copper_edge_clearance": 0.381, "min_silk_clearance": 0.0,
                "min_text_height": 0.8, "min_text_thickness": 0.1},
}


def default_design_settings(fab: str = "generic") -> dict:
    rules = dict(FAB_RULES.get(fab, FAB_RULES["generic"]))
    rules.update({"allow_blind_buried_vias": False, "allow_microvias": False, "max_error": 0.005,
                  "min_connection": 0.0, "min_groove_width": 0.0, "min_microvia_diameter": 0.2,
                  "min_microvia_drill": 0.1, "min_resolved_spokes": 2, "solder_mask_to_copper_clearance": 0.0,
                  "use_height_for_length_calcs": True})
    return {
        "defaults": {"board_outline_line_width": 0.05, "copper_line_width": 0.2, "copper_text_size_h": 1.5,
                     "copper_text_size_v": 1.5, "copper_text_thickness": 0.3, "other_line_width": 0.1,
                     "silk_line_width": 0.12, "silk_text_size_h": 1.0, "silk_text_size_v": 1.0,
                     "silk_text_thickness": 0.15},
        "rules": rules,
        "track_widths": [0.0, 0.2, 0.25, 0.3, 0.5, 0.8, 1.0],
        "via_dimensions": [{"diameter": 0.0, "drill": 0.0}, {"diameter": 0.6, "drill": 0.3},
                           {"diameter": 0.8, "drill": 0.4}],
    }


def minimal_pro(name: str, board_design_settings: dict | None = None, fab: str = "generic") -> dict:
    ds = default_design_settings(fab)
    for k, v in (board_design_settings or {}).items():
        if isinstance(v, dict) and isinstance(ds.get(k), dict):
            ds[k].update(v)
        else:
            ds[k] = v
    pro = {
        "board": {
            "3dviewports": [],
            "design_settings": ds,
            "ipc2581": {"dist": "", "distpn": "", "internal_id": "", "mfg": "", "mpn": ""},
            "layer_pairs": [],
            "layer_presets": [],
            "viewports": [],
        },
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{name}.kicad_pro", "version": 3},
        "net_settings": {
            "classes": [
                {
                    "bus_width": 12, "clearance": 0.2, "diff_pair_gap": 0.25,
                    "diff_pair_via_gap": 0.25, "diff_pair_width": 0.2, "line_style": 0,
                    "microvia_diameter": 0.3, "microvia_drill": 0.1, "name": "Default",
                    "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": 2147483647,
                    "schematic_color": "rgba(0, 0, 0, 0.000)", "track_width": 0.25,
                    "via_diameter": 0.6, "via_drill": 0.3, "wire_width": 6,
                }
            ],
            "meta": {"version": 4},
            "net_colors": None, "netclass_assignments": None, "netclass_patterns": [],
        },
        "pcbnew": {"last_paths": {"gencad": "", "idf": "", "netlist": "", "plot": "", "pos_files": "",
                                  "specctra_dsn": "", "step": "", "svg": "", "vrml": ""},
                   "page_layout_descr_file": ""},
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
        "sheets": [],
        "text_variables": {},
    }
    return pro


def write_pro(dir_: Path, name: str, board_design_settings: dict | None = None,
              root_sheet_uuid: str | None = None, fab: str = "generic") -> Path:
    path = Path(dir_) / f"{name}.kicad_pro"
    if path.exists():
        pro = json.loads(path.read_text(encoding="utf-8"))
        if board_design_settings:
            pro.setdefault("board", {}).setdefault("design_settings", {}).update(board_design_settings)
    else:
        pro = minimal_pro(name, board_design_settings, fab)
    if root_sheet_uuid:
        pro["sheets"] = [[root_sheet_uuid, "Root"]]
    path.write_text(json.dumps(pro, indent=2) + "\n", encoding="utf-8")
    return path


def write_lib_table(dir_: Path, kind: str, entries: list[tuple[str, str, str]]) -> Path:
    """kind = 'sym' or 'fp'. entries = [(name, uri, descr)]. Merges into existing table."""
    from . import sexpr
    from .sexpr import A

    if kind not in ("sym", "fp"):
        raise ValueError("kind must be 'sym' (symbol libraries) or 'fp' (footprint libraries)")
    fname = "sym-lib-table" if kind == "sym" else "fp-lib-table"
    path = Path(dir_) / fname
    head = "sym_lib_table" if kind == "sym" else "fp_lib_table"
    if path.exists():
        tree = sexpr.load(path)
    else:
        tree = A(head, A("version", sexpr.num(7)))
    existing = {str(sexpr.child(l, "name")[1]) for l in sexpr.children(tree, "lib")}
    for name, uri, descr in entries:
        if name in existing:
            continue
        tree.append(A("lib", A("name", name), A("type", "KiCad"), A("uri", uri),
                      A("options", ""), A("descr", descr)))
    sexpr.dump(tree, path)
    return path
