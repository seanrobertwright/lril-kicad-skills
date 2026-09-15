# Design interview question bank

Ask in this order. For each question: say why it matters (one line), give a
recommendation with a reason, then ask. Record the answer and its source in
DESIGN.md before the next question. "Look up" means: fetch the datasheet or
run `kcs sym info` / `kcs fp info` and confirm instead of asking.

Do-not-default list (always ask, never silently choose): MCU family, USB
connector type, layer count, passive package size, fab house, assembly method,
board dimensions, every unused IC pin, connector shell grounding, test points,
regulator topology (LDO vs buck), reverse-polarity/ESD protection, silkscreen
content, mounting.

## 1. Purpose and constraints

1. What does the board do, in one paragraph? What is the single must-work function?
2. Where will it live (bench, enclosure, vehicle, outdoors, wearable)? Temperature range?
3. How many will be built (1, 10, 100, 10k)? This drives package choice and assembly.
4. Budget per board and for the project? Deadline?
5. Who assembles it: you by hand (limits: 0603 and up, no QFN/BGA without tools), a fab's assembly service, or a contract manufacturer?
6. Your comfort level with hand soldering, rework, firmware, and RF?
7. Is there an existing design, reference design, dev board, or schematic to start from? (Ask for the link/PDF.)
8. Any parts already chosen or on hand that must be used?
9. Any hard "must not" (no lead-free reflow, no Chinese sourcing, no BGA, no fine-pitch)?

## 2. Power

1. Every power input: source (USB, barrel, battery, PoE, external supply), voltage range min/max, max current available.
2. Rails needed: list each (e.g. 3.3 V, 5 V, 1.8 V, analog 3.3 V), and the load on each. Look up IC supply currents from datasheets and sum them; add 30% margin. Present the budget table.
3. For each rail: LDO or switcher? Rule: LDO when (Vin - Vout) * I < ~0.5 W and noise matters; otherwise buck. Show the dissipation number.
4. Regulator part: fixed or adjustable; dropout margin; enable pin use; soft start; PG output. Look up input/output capacitor requirements (value, ESR type) from the datasheet and record page numbers.
5. Battery? Chemistry, cell count, charger IC, fuel gauge, protection, charge current, charge source, low-battery behaviour, connector type (JST-PH 2.0 is the default recommendation).
6. Reverse-polarity protection (P-MOSFET ideal diode, Schottky, or none because the connector is keyed)?
7. Overcurrent: fuse (PTC/resettable or not), current limit in the regulator, or none?
8. Power sequencing or holdup requirements? Any rail that must come up first?
9. Power-good/indicator LED on which rail? Current per LED (2 mA recommended for indicators).
10. Bulk capacitance at the input connector and at each regulator output (value, voltage rating >= 2x rail, X7R/X5R, package).
11. Ground scheme: single ground, split analog/digital, chassis ground via the connector shell (tie through 1 M || 1 nF or direct)?

## 3. Core parts

1. MCU/SoC/FPGA: family, exact part number, package (LQFP/QFN/BGA), flash/RAM, pin count, availability now and in 12 months, price. Recommend based on interfaces and assembly method.
2. For each major IC (sensors, drivers, PHYs, memory): exact MPN, package, second source, lifecycle status (active/NRND/EOL).
3. For each IC: is the pinout confirmed from the datasheet? Record the datasheet URL and revision.
4. Passive sizes: 0603 default for hand assembly, 0402 for dense automated; tolerances (1% resistors, 10% X7R caps); voltage ratings.
5. Are there any parts needing custom symbol/footprint (not in the KiCad library)? Mark them for kicad-parts / kicad-symbol / kicad-footprint.

## 4. Interfaces and connectors

For every external connection (power in, USB, UART, I2C, SPI, CAN, Ethernet, analog, motor, sensor, display, buttons):

1. Connector type and exact MPN (USB-C receptacle 16-pin, JST-PH, 2.54 mm header, terminal block, M.2, ...). Orientation: vertical/right angle, top/bottom side, board edge.
2. Pinout, pin 1 position, and mating cable/plug.
3. Signal levels and direction; level shifting needed?
4. Protection: ESD diodes (which package), series resistors, TVS on power, common-mode chokes on USB/Ethernet.
5. USB: speed (FS/HS), which pins are used, CC pull-downs (5.1 k for sink), VBUS sense, shield grounding, D+/D- series resistors if the MCU datasheet asks.
6. Programming/debug connector: SWD (which pinout: 10-pin Cortex 1.27 mm, 4-pin header), JTAG, UART bootloader, USB DFU; boot-mode pin handling (button, jumper, resistor).
7. Mechanical retention (locking connectors, screw terminals) and keying.

## 5. Peripherals per function block

For each block (sensor, driver, memory, RF, display, audio, motor, relay, LED):

1. Exact part and its interface pins; address pins for I2C (which address; conflicts on the same bus?).
2. Required support parts from the datasheet's typical application (decoupling, pull-ups, crystals, matching networks, bootstrap caps, sense resistors). Record values and page.
3. Any thermal need (exposed pad, vias, copper area)? Any keep-out (antenna, MEMS microphone port, light sensor window)?
4. Current draw and its rail.
5. Output/inputs to the outside: routed to which connector pins?

## 6. Clocks, reset, boot

1. Crystal or internal oscillator per IC? Frequency, load capacitance CL, package (3225 is the default recommendation), computed load caps with stray assumption.
2. 32.768 kHz RTC crystal needed? Backup battery/supercap?
3. Reset: pull-up value, reset button, supervisor/brown-out IC, reset from the debug connector.
4. Boot/strap pins: every one listed with the required state and how it is set (resistor, button, jumper). ESP32 and STM32 both have traps here.

## 7. Every pin of every IC

Run `kcs sym info Lib:Part` and walk the pin list. For each pin: net name, or
"no connect" with the datasheet's guidance for unused pins (some must be
grounded or pulled, not left floating: unused ADC inputs, oscillator pins, NC
pins with internal connections, exposed pads). Write the result into
`design.json` nets / no_connect / unused_pins_nc. Do not proceed until the
validator passes.

## 8. Mechanical

1. Board dimensions (max/exact), shape, corner radius; or does the board define the enclosure?
2. Mounting: hole count, diameter (M2.5 = 2.7 mm, M3 = 3.2 mm), positions, plated or not, grounded or isolated.
3. Height limits top and bottom; tallest component; connector overhang.
4. Keep-outs: antenna, screws, standoffs, cable paths, heat sources.
5. Enclosure: existing (which one, link), 3D-printed, none. Need a STEP export?
6. Panelisation needed? Mouse bites vs V-score; rails.
7. Placement hints (recorded as `board.hints`): which edge each connector
   sits on and its orientation; which part is the centre of the board (the
   MCU/SoC); which small parts must sit next to which IC (decoupling,
   crystal, USB ESD at the connector); anything on the back side; anything
   that must line up with an enclosure feature (LEDs, buttons, displays).
   Ask per connector; propose the obvious answer.

## 9. PCB technology

1. Layer count: 2 for simple boards; 4 (SIG-GND-PWR-SIG) recommended for any MCU above ~50 MHz, USB HS, RF, or dense QFN. Show why.
2. Thickness (1.6 mm default; 0.8/1.0 for small boards or USB-A plug boards), copper weight (1 oz default), surface finish (HASL default, ENIG for fine pitch/BGA/gold fingers), solder mask and silkscreen colours.
3. Minimum track/space and via (fab capability). Defaults for JLCPCB/PCBWay standard: 0.127 mm track/space, 0.3 mm drill / 0.6 mm via. Set the DRC rules from these.
4. Controlled impedance: which nets (USB 90 ohm diff, RF 50 ohm), stackup from the fab.
5. Net classes: power widths (compute from current), signal widths, clearances, diff pairs.
6. Via strategy: tented or not; via-in-pad (no, unless filled); stitching.

## 10. Manufacturing and assembly

1. Fab house (JLCPCB, PCBWay, OSH Park, Aisler, Eurocircuits, other) and quantity. This sets the export preset.
2. Assembly service? If JLCPCB: parts must be in their catalogue; record LCSC numbers (`kcs jlc C12345` returns price, stock, basic vs extended); basic vs extended parts fee. Which side(s) assembled?
3. Single-sided assembly to save cost? Then all SMD on top.
4. Fiducials (3 per side for automated assembly), tooling holes, panel rails.
5. Hand-solder rules if applicable: no QFN/DFN/BGA, 0.65 mm pitch min, hand-solder pad variants (`_HandSolder` footprints).
6. Silkscreen content: reference designators (all, or only connectors), board name, revision, date, pin-1 marks, connector pinouts, polarity marks, logo, warnings.

## 11. Test, bring-up, indicators

1. Test points (which nets: every rail, ground, key signals); style (SMD pad, loop, pogo).
2. Status LEDs: which, colour, rail, current, GPIO.
3. Jumpers/solder bridges for options (boot mode, power source select, address).
4. Current-measurement jumper on the main rail?
5. Bring-up plan: what is checked first when the board arrives (rails, then clock, then debug connection)?

## 12. Compliance and environment

1. ESD on every user-touchable connector; TVS rating vs. signal voltage.
2. EMC: shielding cans, filters on I/O, ferrites on power entry.
3. Operating/storage temperature; conformal coating; humidity/IP rating.
4. Safety: mains? isolation? creepage/clearance; fusing; certifications needed (CE/FCC/UL)?
5. RoHS/REACH; lead-free process.

## Closing

Print the DESIGN.md summary: purpose, power tree, part table, connector table,
board stack, fab, open risks. Ask for "approved". Then run
`kcs spec validate design/design.json` and hand off.
