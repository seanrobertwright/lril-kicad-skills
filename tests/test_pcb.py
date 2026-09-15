import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "kicad" / "scripts"))
SCRATCH = Path(tempfile.mkdtemp(prefix="kcs-test-"))
import json, subprocess
from kcslib import env as kenv, pcb, check

d = SCRATCH / "pcbtest"
d.mkdir(exist_ok=True)
b = pcb.Board(copper_layers=2, title="pcb test")
b.outline_rect(0, 0, 40, 30, radius=2)
cases = [("R1", (10, 10), 0, "F.Cu"), ("R2", (10, 15), 90, "F.Cu"), ("R3", (10, 20), 45, "F.Cu"),
         ("R4", (20, 10), 0, "B.Cu"), ("R5", (20, 15), 90, "B.Cu"), ("R6", (20, 20), 180, "F.Cu")]
for ref, at, rot, layer in cases:
    b.add_footprint("Resistor_SMD:R_0603_1608Metric", ref, "10k", at, rot, layer,
                    pad_nets={"1": "VCC", "2": f"N_{ref}"}, sch_path=f"/{ref}-uuid")
u = b.add_footprint("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "U1", "LM358", (30, 15), 90, "F.Cu",
                    pad_nets={"1": "OUT", "4": "GND", "8": "VCC"})
j = b.add_footprint("Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical", "J1", "Conn", (5, 5), 0, "B.Cu",
                    pad_nets={"1": "VCC", "2": "GND"})
b.mounting_hole("H1", (36, 4))
b.track(b.footprints["R1"].pad_pos("1"), b.footprints["R2"].pad_pos("1"), "VCC", 0.25)
b.via((15, 12), "VCC")
b.zone("GND", "B.Cu", [(0, 0), (40, 0), (40, 30), (0, 30)])
b.gr_text("pcb test", (20, 27), "F.SilkS")
p = b.save(d / "pcbtest.kicad_pcb")

# cross-check pad positions with pcbnew SWIG
script = d / "swig_check.py"
script.write_text(f'''
import pcbnew, json
b = pcbnew.LoadBoard(r"{p}")
out = {{}}
for fp in b.GetFootprints():
    for pad in fp.Pads():
        pos = pad.GetPosition()
        out[fp.GetReference() + ":" + pad.GetNumber()] = [pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), pad.GetNetname(), fp.GetLayerName()]
print(json.dumps(out))
''')
r = subprocess.run([str(kenv.get().python), str(script)], capture_output=True, text=True)
if r.returncode != 0:
    print("SWIG FAILED", r.stdout, r.stderr[-2000:])
else:
    swig = json.loads(r.stdout.strip().splitlines()[-1])
    bad = 0
    for ref, fp in b.footprints.items():
        for n in fp.pads:
            mine = fp.pad_pos(n)
            theirs = swig[f"{ref}:{n}"]
            if abs(mine[0] - theirs[0]) > 1e-3 or abs(mine[1] - theirs[1]) > 1e-3:
                bad += 1
                print("MISMATCH", ref, n, mine, theirs)
    print("pad position mismatches:", bad, "of", len(swig))
res = check.drc(p)
print("DRC ok:", res["ok"], "violations:", len(res["violations"]), "unconnected:", len(res["unconnected"]))
for v in res["violations"][:15]:
    print("  ", v["severity"], v["type"], v["description"], [i["description"] for i in v["items"]][:2])
check.render_board(p, d / "top.png", side="top")
check.render_board(p, d / "bottom.png", side="bottom")
print("rendered")
