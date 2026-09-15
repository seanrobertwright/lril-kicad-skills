import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "kicad" / "scripts"))
SCRATCH = Path(tempfile.mkdtemp(prefix="kcs-test-"))
import json
from kcslib import env as kenv, sch, check, project

d = SCRATCH / "geomtest"
d.mkdir(exist_ok=True)
s = sch.Schematic("geomtest", title="geometry test")
expected = {}
x = 25.4
cases = [(0, None), (90, None), (180, None), (270, None), (0, "x"), (0, "y"), (90, "x"), (90, "y")]
for i, (rot, mir) in enumerate(cases):
    ref = f"R{i+1}"
    r = s.add_symbol("Device:R", ref, "1k", at=(x, 50.8), rot=rot, mirror=mir, footprint="Resistor_SMD:R_0603_1608Metric")
    na, nb = f"A{i}", f"B{i}"
    s.connect_label(r, "1", na)
    s.connect_label(r, "2", nb)
    expected[na] = [(ref, "1")]
    expected[nb] = [(ref, "2")]
    x += 25.4
# a 3-pin asymmetric symbol, rotated, to catch x/y swaps
x = 25.4
for i, (rot, mir) in enumerate(cases):
    ref = f"U{i+1}"
    u = s.add_symbol("Regulator_Linear:AMS1117-3.3", ref, "AMS1117-3.3", at=(x, 101.6), rot=rot, mirror=mir)
    for pin, net in (("1", f"G{i}"), ("2", f"O{i}"), ("3", f"I{i}")):
        s.connect_label(u, pin, net)
        expected[net] = [(ref, pin)]
    x += 30.48
# power symbols + wire_pins
r = s.add_symbol("Device:R", "R20", "4k7", at=(25.4, 152.4), rot=0)
c = s.add_symbol("Device:C", "C20", "100n", at=(50.8, 152.4), rot=0)
s.connect_power(r, "1", "+3V3")
s.connect_power(c, "2", "GND")
s.connect_power(r, "2", "GND")
s.wire_pins(r, "1", c, "1")
expected["+3V3"] = [("C20", "1"), ("R20", "1")]
expected["GND"] = [("C20", "2"), ("R20", "2")]
p = s.save(d / "geomtest.kicad_sch")
project.write_pro(d, "geomtest", root_sheet_uuid=s.uuid)
nl = check.netlist(p)
cmp = check.compare_nets(expected, nl["nets"])
print("NETLIST COMPARE:", json.dumps(cmp, indent=1))
bad = {k: v for k, v in nl["nets"].items() if k.startswith("unconnected") or k.startswith("Net-")}
print("unconnected/anon nets:", bad)
e = check.erc(p)
print("ERC ok:", e["ok"], "violations:", len(e["violations"]))
for v in e["violations"][:12]:
    print("  ", v["severity"], v["type"], v["description"], [i["description"] for i in v["items"]])
check.export_pdf(p, d / "geomtest.pdf")
print("pdf written")
