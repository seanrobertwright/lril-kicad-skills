import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "kicad" / "scripts"))
SCRATCH = Path(tempfile.mkdtemp(prefix="kcs-test-"))
import json
from kcslib import build, check, sexpr

spec = build.load_spec(ROOT / "examples" / "stm32node" / "design.json")
assert spec.get("sheets"), "example must use hierarchical sheets for this test"
res = build.build(spec, SCRATCH / "hier", render=False)
print(res.summary())
assert res.netlist_check["ok"], res.netlist_check
assert not [v for v in res.erc["violations"] if v["severity"] == "error"], "ERC errors"
assert len(res.sheet_paths) == len(spec["sheets"]), "one file per sheet"
root = sexpr.load(res.sch_path)
sheets = sexpr.children(root, "sheet")
assert len(sheets) == len(spec["sheets"]), "root holds one sheet symbol per sheet"
# every crossing net appears as a sheet pin on at least two sheet symbols
pins_by_net = {}
for sh in sheets:
    for p in sexpr.children(sh, "pin"):
        pins_by_net.setdefault(str(p[1]), 0)
        pins_by_net[str(p[1])] += 1
assert all(n >= 2 for n in pins_by_net.values()), pins_by_net
# board footprints carry the hierarchical sheet path
board = sexpr.load(res.pcb_path)
paths = [str(sexpr.child(f, "path")[1]) for f in sexpr.children(board, "footprint") if sexpr.child(f, "path")]
assert any(p.count("/") == 3 for p in paths), "sub-sheet symbols get /root/sheet/symbol paths"
# hints honoured: J1 on the left edge, U2 near the centre
fps = {sexpr.get_property(f, "Reference"): sexpr.floats(sexpr.child(f, "at")) for f in sexpr.children(board, "footprint")}
ox, oy = spec["board"].get("origin", [50, 50])
w, h = spec["board"]["width"], spec["board"]["height"]
assert fps["J1"][0] < ox + w * 0.25, fps["J1"]
assert abs(fps["U2"][0] - (ox + w / 2)) < 6 and abs(fps["U2"][1] - (oy + h / 2)) < 6, fps["U2"]
print("HIER OK")
