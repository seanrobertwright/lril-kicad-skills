import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills" / "kicad" / "scripts"))
SCRATCH = Path(tempfile.mkdtemp(prefix="kcs-test-"))
import json
from kcslib import env as kenv, sym, sch, check, project, libs

d = SCRATCH / "symtest"
d.mkdir(exist_ok=True)
spec = sym.SymbolSpec(
    name="TPS7A0233", reference="U", footprint="Package_TO_SOT_SMD:SOT-23-5",
    datasheet="https://www.ti.com/lit/ds/symlink/tps7a02.pdf",
    description="200mA ultra-low-IQ LDO, 3.3V fixed, SOT-23-5", keywords="ldo regulator",
    fp_filters="SOT?23*",
    pins=[
        sym.PinSpec("1", "IN", "power_in", "left"),
        sym.PinSpec("2", "GND", "power_in", "bottom"),
        sym.PinSpec("3", "EN", "input", "left", gap_before=1),
        sym.PinSpec("4", "NC", "no_connect", "right"),
        sym.PinSpec("5", "OUT", "power_out", "right"),
    ])
mcu = sym.SymbolSpec(
    name="MyMCU", reference="U", footprint="Package_QFP:LQFP-32_7x7mm_P0.8mm", datasheet="https://x", description="test mcu",
    pins=[sym.PinSpec(str(i), f"PA{i}", "bidirectional", "right") for i in range(1, 13)] +
         [sym.PinSpec("13", "VDD", "power_in", "top"), sym.PinSpec("14", "VDDA", "power_in", "top"),
          sym.PinSpec("15", "VSS", "power_in", "bottom"), sym.PinSpec("16", "~{RESET}", "input", "left", shape="inverted"),
          sym.PinSpec("17", "BOOT0", "input", "left", gap_before=1), sym.PinSpec("18", "OSC_IN", "input", "left", gap_before=1),
          sym.PinSpec("19", "OSC_OUT", "output", "left"), sym.PinSpec("20", "NC", "no_connect", "right")])
libpath = sym.write_library([spec, mcu], d / "MyParts.kicad_sym", merge=False)
lib = libs._load_symbol_file(str(libpath))
for s in libs.children(lib, "symbol"):
    print(s[1], "problems:", sym.check_symbol(s))
project.write_lib_table(d, "sym", [("MyParts", "${KIPRJMOD}/MyParts.kicad_sym", "project parts")])
libs._load_symbol_file.cache_clear()
s = sch.Schematic("symtest", title="symbol test", project_dir=d)
u1 = s.add_symbol("MyParts:TPS7A0233", "U1", "TPS7A0233", at=(50.8, 50.8))
u2 = s.add_symbol("MyParts:MyMCU", "U2", "MyMCU", at=(127, 63.5))
s.connect_power(u1, "1", "VBUS"); s.connect_power(u1, "2", "GND"); s.connect_power(u1, "5", "+3V3")
s.connect_label(u1, "3", "EN")
for p in ("13", "14"): s.connect_power(u2, p, "+3V3")
s.connect_power(u2, "15", "GND")
s.connect_label(u2, "1", "LED"); s.connect_label(u2, "16", "~{RESET}")
p = s.save(d / "symtest.kicad_sch")
project.write_pro(d, "symtest", root_sheet_uuid=s.uuid)
nl = check.netlist(p)
print(json.dumps(nl["nets"], indent=0)[:600])
e = check.erc(p)
import collections
print(collections.Counter((v["severity"], v["type"]) for v in e["violations"]))
check.export_pdf(p, d / "symtest.pdf")
