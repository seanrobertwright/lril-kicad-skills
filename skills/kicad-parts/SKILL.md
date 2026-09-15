---
name: kicad-parts
description: Resolve every component of a KiCad design to a concrete symbol, footprint, manufacturer part number and datasheet, and obtain symbols/footprints/3D models from manufacturer websites, LCSC/JLCPCB (easyeda2kicad), SnapEDA, Ultra Librarian, SamacSys, Digi-Key or Mouser when the stock library lacks them. Use when the user gives a part number, a product page URL, an LCSC number, a datasheet, or says "find the footprint for", "which part should I use", "source this part", "get me the KiCad library for". Also fills BOM fields (MPN, Manufacturer, LCSC, Datasheet).
---

# KiCad parts and sourcing

Goal: every row in DESIGN.md's parts table has symbol, footprint, MPN,
datasheet and (if assembly is planned) a distributor number, each with a
source. The order of attempts is fixed; stop at the first that yields a
verified result.

`KCS = python <skills>/kicad/scripts/kcs.py`

## Resolution order

1. **Stock KiCad 10 libraries** (`KCS sym search`, `KCS fp search`). Check
   the symbol's `fp_filters` and description; confirm the package variant
   (e.g. SOT-223-3 vs SOT-223-3_TabPin2) against the datasheet.
2. **Manufacturer-published KiCad libraries**: Espressif (PCM/GitHub),
   Würth (GitHub), a few others. Check the manufacturer page for
   "KiCad", "ECAD", "CAD models", "Design resources".
3. **LCSC part number known** (or JLCPCB assembly planned): first
   `KCS jlc C12345` for price, stock, package, manufacturer, basic vs
   extended class and whether EasyEDA has a symbol/footprint (no login, no
   key). For a bare MPN, `KCS jlc <MPN>` explains the fallback: web-search
   the MPN with "LCSC", take the `C<number>` from the result URL, then look
   it up. Then `easyeda2kicad`
   (`pip install easyeda2kicad`, then
   `easyeda2kicad --full --lcsc_id C2040 --output <project>/parts --project-relative`)
   produces `.kicad_sym`, `.pretty`, `.3dshapes`. Then `KCS upgrade` the
   footprint (it is written in an older format) and verify as below.
4. **SnapEDA / Ultra Librarian / SamacSys (Component Search Engine)**: all
   need an account and a browser download. Ask the user to download the
   KiCad zip and give you the path (or drive the browser with the
   claude-in-chrome tools if the user prefers). Unzip, `KCS upgrade`, verify.
5. **Generate** with **kicad-symbol** and **kicad-footprint** from the
   datasheet. This is the normal path for new or niche parts and takes
   minutes with the generators.

Never accept a symbol or footprint without: `KCS sym info` / `KCS fp info`
compared against the datasheet pin table and package drawing, and a
`KCS klc` pass.

## When the user gives a URL

Fetch the product page (WebFetch). Extract: MPN and orderable variants,
package, datasheet link, CAD/model links, lifecycle status, price/stock if
shown. Fetch the datasheet. Then follow the resolution order. Report what
each source offered and which you used.

## Choosing parts (when the user has not)

Recommend one part, with reasons and one alternative, using these criteria
in order: meets the electrical spec with margin; package matches the
assembly method (no QFN for hand soldering unless the user accepts); in
stock at the chosen distributor (JLCPCB basic parts avoid the extended fee);
active lifecycle; has a stock KiCad symbol/footprint; price. Ask the user to
confirm before recording.

Typical defaults to propose (always confirm): 0603 passives (0402 for
automated dense boards); X7R/X5R ceramics rated >= 2x rail; AMS1117 or
richer (ME6211, AP2112, TLV1117, XC6206) LDOs; JST-PH battery; USB-C 16-pin
receptacle (HRO TYPE-C-31-M-12) with 5.1 k CC pull-downs; PTS645 tactile
switches; 3225 crystals.

## BOM fields

Add to each component's `props` in design.json: `MPN`, `Manufacturer`,
`LCSC` (if JLCPCB), `Digikey`/`Mouser` when known, `Datasheet` on the
symbol. `kicad-export` maps them into fab-specific BOM columns.

Reference: `../kicad/references/part-sources-and-klc.md` (what each source
provides, login needs, tools, KLC rules).
