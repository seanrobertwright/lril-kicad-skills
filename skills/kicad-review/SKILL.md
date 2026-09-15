---
name: kicad-review
description: Independent design review of a KiCad 10 schematic and PCB before fabrication. Use when the user asks to review, check, audit, sanity-check, or "look over" a schematic or board, before ordering boards, or after kicad-schematic/kicad-pcb finish. Runs ERC/DRC, exports the netlist and renders, then walks a checklist of common hardware mistakes (decoupling, pull-ups, boot pins, USB, regulators, crystals, connectors, silkscreen, DFM) and produces a findings report with severity and evidence.
---

# KiCad design review

Review as a second engineer who did not draw the board. Evidence, not
opinion: every finding cites the net/ref, the datasheet page or rule, and
what to change.

`KCS = python <skills>/kicad/scripts/kcs.py`

## Inputs

1. `KCS erc <sch>` and `KCS drc <pcb> --parity` (JSON). Zero errors is the
   entry ticket; list every warning with a disposition.
2. `KCS netlist <sch>` - the connectivity you review from.
3. `KCS pdf <sch>` and `KCS render <pcb>` - look at them with Read.
4. `design/DESIGN.md` - the contract; the review checks the design against
   it and flags anything not written down.

## Checklist

**Power**
- Every IC supply pin has decoupling (100 nF per pin plus bulk); datasheet-
  specific values respected (LDO output cap type/ESR, switcher input cap).
- Regulator: input range, dropout at min input, dissipation at max load,
  enable pin tied, feedback divider values (compute), output rated caps.
- Reverse polarity / overcurrent / inrush handled or explicitly waived.
- Rail voltages match every consumer's absolute maximum; level shifting
  where 5 V meets 3.3 V.
- PWR_FLAG only where a passive source drives a rail (connector).

**MCU / digital**
- Reset pull-up and cap; boot/strap pins in a defined state (STM32 BOOT0,
  ESP32 GPIO0/2/12/15, nRF SWD); debug connector pinout matches the probe.
- Crystal: load caps computed, ESR/drive level ok, RTC crystal if needed.
- Unused pins per datasheet (floating allowed? ADC inputs? oscillator pins).
- I2C pull-ups present exactly once per bus; addresses unique.
- UART TX/RX crossed correctly; SPI CS per device; CAN termination.
- USB: CC pull-downs, D+/D- polarity, series resistors if required, ESD,
  VBUS sense divider on 5 V-intolerant pins.

**Analog / sensors / drivers**
- Reference voltages, input filtering, anti-aliasing, sense resistor power.
- Motor/relay/inductive loads: flyback diodes, gate resistors, bootstrap caps.
- LED currents computed; polarity marked.

**Connectors / mechanical**
- Pin 1 marked; pinout table in DESIGN.md matches the schematic; mating
  connector orientation on the board edge; shell grounding decided.
- Mounting holes: size, clearance, grounding; keep-outs honoured.

**PCB**
- DRC clean at the fab's rules; net classes applied; power trace widths
  computed for current; thermal relief on hand-soldered pads.
- Return paths: ground pour/plane continuity under signals; no slots
  under diff pairs; stitching vias.
- Decoupling within 2 mm; crystal guard; switcher loop tight; antenna
  keep-out; test points accessible; fiducials if machine assembled.
- Silkscreen: name, revision, pin 1, polarity, connector labels, no silk on
  pads; date/rev matches DESIGN.md.
- Every footprint matches its symbol pin count (`schematic_parity` clean),
  and every footprint has a 3D model (STEP export for enclosure fit).

**DFM / sourcing**
- Every BOM row has MPN and (if assembling) distributor number; packages
  fit the assembly method; no EOL parts; alternates noted for risky parts.

## Report

Write `design/REVIEW-<date>.md`:

```
# Review <project> rev <A> <date>
## Summary: <n> blockers, <n> majors, <n> minors, <n> notes
## Findings
| id | severity | area | finding | evidence | fix |
## Verified OK
- ... (what was checked and found fine, so the user knows coverage)
## Not checked
- ... (and why)
```

Severity: **blocker** (board will not work or is unsafe), **major** (will
likely need a respin), **minor** (works, should fix), **note**.

Then walk the blockers with the user one at a time, and update DESIGN.md's
decision log with the outcomes.
