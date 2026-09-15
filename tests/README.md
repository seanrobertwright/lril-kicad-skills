# Tests

These scripts run against a real KiCad 10 install (they call `kicad-cli`
and the bundled `pcbnew` Python). Run each with any Python 3.10+:

- `test_geom.py` - schematic pin transform for every rotation/mirror, verified by netlist export
- `test_pcb.py` - board writer; pad positions cross-checked with pcbnew, DRC, renders
- `test_sym.py` - symbol generator, project library, ERC/netlist round trip
- `test_fp.py` - footprint generator vs. stock KiCad footprints (pad deltas), DRC
- `test_e2e.py` - full build of `examples/stm32node/design.json`
