# 2. Enforce 50-mil (1.27mm) Schematic Grid & Orthogonal Pin Validation
Date: 2026-10-16
Status: Accepted

All schematic pin endpoints and wire routing coordinates in kcslib.geom must snap to a positive grid step (default 1.27mm / 50 mil), validate orthogonal pin orientation angles (multiples of 90 deg), and provide deterministic Euclidean/Manhattan distance and fmt_pt() formatting helpers.
