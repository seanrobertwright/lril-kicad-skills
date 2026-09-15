import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "kicad" / "scripts"))
SCRATCH = Path(tempfile.mkdtemp(prefix="kcs-test-"))
import json
from kcslib import env as kenv, fp, libs, sexpr, check, pcb

d = SCRATCH / "fptest"
d.mkdir(exist_ok=True)
pretty = d / "Test.pretty"

def compare(spec, stock_id):
    path = fp.write_footprint(spec, pretty)
    mine = libs.footprint_pads(sexpr.load(path))
    stock = libs.footprint_pads(libs.load_footprint(stock_id))
    sm = {p["number"]: p for p in stock}
    worst = 0
    for p in mine:
        if p["number"] not in sm or not p["number"]:
            continue
        s = sm[p["number"]]
        dpos = max(abs(p["at"][0] - s["at"][0]), abs(p["at"][1] - s["at"][1]))
        dsz = max(abs(p["size"][0] - s["size"][0]), abs(p["size"][1] - s["size"][1]))
        worst = max(worst, dpos, dsz)
    print(f"{spec.name:28s} vs {stock_id:60s} max pos/size delta {worst:.3f} mm; pads {len(mine)}/{len(stock)}; klc: {fp.check_footprint(sexpr.load(path))}")

compare(fp.chip("R_0603", 1.6, 0.8, 0.3), "Resistor_SMD:R_0603_1608Metric")
compare(fp.chip("C_0402", 1.0, 0.5, 0.25), "Capacitor_SMD:C_0402_1005Metric")
compare(fp.chip("C_0805", 2.0, 1.25, 0.4), "Capacitor_SMD:C_0805_2012Metric")
compare(fp.gullwing("SOIC8", 8, 1.27, 3.9, 4.9, 6.0, lead_w=0.42, lead_l=0.83), "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")
compare(fp.gullwing("TSSOP16", 16, 0.65, 4.4, 5.0, 6.4, lead_w=0.25, lead_l=0.6), "Package_SO:TSSOP-16_4.4x5mm_P0.65mm")
compare(fp.gullwing("SOT23", 3, 0.95, 1.3, 2.9, 2.5, lead_w=0.4, lead_l=0.5, left_pins=["1","2"], right_pins=["3"]), "Package_TO_SOT_SMD:SOT-23")
compare(fp.gullwing("LQFP32", 32, 0.8, 7.0, 7.0, 9.0, lead_w=0.37, lead_l=0.6, sides=4), "Package_QFP:LQFP-32_7x7mm_P0.8mm")
compare(fp.no_lead("QFN16", 16, 0.5, 3.0, lead_w=0.25, lead_l=0.4, ep=(1.7, 1.7)), "Package_DFN_QFN:QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm")
compare(fp.dip("DIP8", 8), "Package_DIP:DIP-8_W7.62mm")
compare(fp.header("PinHeader_1x04", 4), "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical")
# board-level check: DRC on a board using the generated footprints
from kcslib import project
project.write_lib_table(d, "fp", [("Test", "${KIPRJMOD}/Test.pretty", "generated")])
b = pcb.Board(project_dir=d, title="fp test")
b.outline_rect(0, 0, 50, 40)
x = 6
for name in ["R_0603", "C_0402", "C_0805", "SOIC8", "TSSOP16", "SOT23", "LQFP32", "QFN16", "DIP8", "PinHeader_1x04"]:
    b.add_footprint(f"Test:{name}", f"X{x}", name, (x, 20 if x < 30 else 12 + (x - 30) * 0.0), 0)
    x += 8 if name not in ("LQFP32", "DIP8", "TSSOP16") else 12
p = b.save(d / "fptest.kicad_pcb")
project.write_pro(d, "fptest")
r = check.drc(p)
import collections
print("DRC:", collections.Counter((v["severity"], v["type"]) for v in r["violations"]))
check.render_board(p, d / "fptest.png", side="top", zoom=1.4)
