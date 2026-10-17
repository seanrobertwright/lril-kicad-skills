# KiCad Skills — Spec-Driven Development (SDD) Specification

## Geometry & Coordinate Helpers (kcslib.geom)
- [x] Validate positive grid step (grid <= 0 raises ValueError) in snap()
- [x] Implement pt_on_grid(pt, grid, tol) and bbox_pts(pts) bounding-box helpers
- [x] Reject non-cardinal pin angles (angle % 90 != 0) in pin_direction()
- [x] Add dist(a, b), manhattan(a, b), and fmt_pt(pt) helpers to skills/kicad/scripts/kcslib/geom.py with unit tests in tests/test_geom_unit.py and mark this task [x] in SPEC.md

## S-Expression AST & DRC Governance (kcslib.sexpr)
- [x] Preserve bare Atom tokens on lossless KiCad S-expression round-trip
- [ ] Add set_property_value(node, key, value) in-place mutation helper to kcslib.sexpr
