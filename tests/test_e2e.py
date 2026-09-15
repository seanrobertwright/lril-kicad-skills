import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "kicad" / "scripts"))
SCRATCH = Path(tempfile.mkdtemp(prefix="kcs-test-"))
import json
from kcslib import build
spec = build.load_spec(ROOT / "examples" / "stm32node" / "design.json")
res = build.build(spec, SCRATCH / "stm32node")
print(res.summary())
assert res.netlist_check["ok"], res.netlist_check
assert not [v for v in res.erc["violations"] if v["severity"] == "error"], "ERC errors"
assert not [v for v in res.drc["violations"] if v["severity"] == "error"], "DRC errors"
print("E2E OK")
