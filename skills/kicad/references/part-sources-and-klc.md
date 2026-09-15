# Obtaining or generating KiCad symbols, footprints and 3D models for a part (Windows, KiCad 10.0.6)

Research date: 2026-09-14. Target: KiCad 10.0.6 (tag dated 2026-08-28 in the KiCad source repo).

## 0. KiCad 10 facts every source below is measured against

### File-format version stamps (from KiCad 10.0 branch source)

| File | Constant (symbol name) | Value in 10.0 branch |
|---|---|---|
| `.kicad_mod` / `.kicad_pcb` | `SEXPR_BOARD_FILE_VERSION` in `pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr.h` | `20260206` |
| `.kicad_sym` | `SEXPR_SYMBOL_LIB_FILE_VERSION` in `eeschema/sch_file_versions.h` | `20251024` |
| `.kicad_sch` | `SEXPR_SCHEMATIC_FILE_VERSION` in `eeschema/sch_file_versions.h` | `20260306` |

KiCad 10 reads any older KiCad s-expression version (and the pre-v6 legacy `.lib` / `.mod` formats) and silently upgrades on load. So a vendor file stamped 2021-2024 still opens; the only cost is that KiCad rewrites it the first time you save. To normalise files before committing them to a library, use the official CLI:

```
kicad-cli sym upgrade [--output OUTPUT_FILE_OR_DIR] [--force] INPUT_FILE_OR_DIR
kicad-cli fp  upgrade [--output OUTPUT_DIR]        [--force] INPUT_FILE_OR_DIR
```

Per the KiCad 10.0 CLI documentation, `sym upgrade` accepts `.kicad_sym`, pre-6 `.lib`, Altium `.SchLib`/`.IntLib`, CADSTAR `.lib`, EAGLE `.lbr`, and EasyEDA Std `.json` / Pro `.elibz`/`.epro`/`.zip`. `fp upgrade` accepts `.pretty`, pre-5 `.mod`/`.emp`, Altium `.PcbLib`/`.IntLib`, CADSTAR `.cpa`, EAGLE `.lbr`, EasyEDA Std/Pro, and gEDA `.fp` folders. This means **any vendor zip in Altium or EAGLE format is also usable** on Windows via `kicad-cli.exe` (installed under `C:\Program Files\KiCad\10.0\bin\`).

### Path variables (KiCad 10.0 manual, "Configure Paths")

Confirmed names:

- `KICAD10_SYMBOL_DIR` - base path of the standard symbol libraries
- `KICAD10_FOOTPRINT_DIR` - base path of the standard footprint libraries
- `KICAD10_3DMODEL_DIR` - base path of the standard 3D model libraries
- `KICAD10_3RD_PARTY` - where the Plugin and Content Manager installs plugins, libraries and themes
- `KICAD10_TEMPLATE_DIR` - standard project templates
- `KICAD_USER_TEMPLATE_DIR` - personal templates
- `SPICE_LIB_DIR` - personal SPICE model libraries (not defined by default)
- `KIPRJMOD` - absolute path of the current project; set automatically, cannot be redefined
- Advanced OS-level only: `KICAD_CONFIG_HOME`, `KICAD_DOCUMENTS_HOME`, `KICAD_STOCK_DATA_HOME`

Windows config location for 10.0: `%APPDATA%\kicad\10.0` (contains `sym-lib-table`, `fp-lib-table`, `kicad_common.json` with the env-var overrides). Custom variables (e.g. `EASYEDA2KICAD`, `KICAD_3RD_PARTY` as used by the Import-LIB plugin) are user-defined in the same dialog / JSON.

Gotcha: the KLC text for F9.3 still says `${KICAD9_3DMODEL_DIR}/`; for a KiCad 10 install the equivalent is `${KICAD10_3DMODEL_DIR}/`. Official-library footprints shipped with KiCad 10 use the 10 variable. Private libraries should use their own variable (or `${KIPRJMOD}`) rather than the KICAD10 one, because that directory is overwritten by the installer.

---

## 1. easyeda2kicad (pip) - LCSC part number -> symbol + footprint + 3D

- Repo: <https://github.com/uPesy/easyeda2kicad.py>; PyPI `easyeda2kicad`.
- **Current version: 1.0.1** (PyPI upload 2026-04-06; GitHub release v1.0.1 the same day). Previous release 0.8.0 was 2024-06-17, so this is an active project again. Last commit on `master` 2026-04-08. Requires Python >= 3.9.
- Fork on PyPI: `atopile-easyeda2kicad` (0.9.x, atopile's variant) - ignore unless using atopile.
- Login/API key: **none**. It talks to EasyEDA's public component API using the LCSC `Cxxxx` id.
- Install (Windows): `pip install easyeda2kicad` in any Python 3.9+, or in the *KiCad Command Prompt* (KiCad-bundled Python), then run as `python -m easyeda2kicad ...` because KiCad's Scripts folder is not on PATH.

CLI (from `easyeda2kicad/__main__.py` argparse):

```
easyeda2kicad --full      --lcsc_id C2040            # symbol + footprint + 3D
easyeda2kicad --symbol    --lcsc_id C2040
easyeda2kicad --footprint --lcsc_id C2040
easyeda2kicad --3d        --lcsc_id C2040
easyeda2kicad --full --lcsc_id C2040 C20197 C163691  # several parts, one call
easyeda2kicad --full --lcsc_id C2040 --output D:/libs/my_lib          # lib base name
easyeda2kicad --full --lcsc_id C2040 --output ./libs/my_lib --project-relative
easyeda2kicad --full --lcsc_id C2040 --overwrite --use-cache --debug
easyeda2kicad --svg  --lcsc_id C2040 --output out   # SVG preview only
easyeda2kicad --full --lcsc_id C2040 --custom-field "Key=Value"
```

Output structure (default base `~/Documents/Kicad/easyeda2kicad/`, i.e. `C:\Users\<you>\Documents\Kicad\easyeda2kicad\`):

- `<base>.kicad_sym` - one library file; each converted part is appended (or replaced with `--overwrite`)
- `<base>.pretty/<name>.kicad_mod`
- `<base>.3dshapes/<name>.wrl` and `<name>.step` (both are written; WRL is generated with colour from EasyEDA's OBJ, STEP downloaded from EasyEDA)
- Footprint `(model ...)` path is `${EASYEDA2KICAD}/easyeda2kicad.3dshapes/...` when no `--output`, `${KIPRJMOD}/<relative>.3dshapes/...` with `--project-relative`, otherwise the absolute output path. So with the default you must add an `EASYEDA2KICAD` path variable in *Preferences > Configure Paths* and register `${EASYEDA2KICAD}/easyeda2kicad.kicad_sym` and `${EASYEDA2KICAD}/easyeda2kicad.pretty` as global libraries.
- Symbol fields written: standard ones plus `LCSC Part`, `Manufacturer`, `MPN` properties.

KiCad 9/10 compatibility - verified against source on `master`:

- **Symbols**: `KICAD_SYM_VERSIONS_SORTED` in `easyeda2kicad/kicad/parameters_kicad_symbol.py` lists 20211014 ... 20241209, **20251024** (the exact KiCad 10 symbol version). `read_symbol_lib_version` in `export_kicad_symbol.py` chooses the version to emit: if the target `.kicad_sym` already exists it matches that file's version, if the file is new it writes the *oldest* known version (20211014). Either way KiCad 10 opens it; run `kicad-cli sym upgrade` if you want the modern stamp. Bezier curves need >= 20220914 and fall back on older versions.
- **Footprints**: `KI_MODULE_INFO` in `easyeda2kicad/kicad/parameters_kicad_footprint.py` is still the **legacy `(module <lib>:<name> (layer F.Cu) (tedit ...)` header with `fp_text` elements** (KiCad 5.1/6 style). KiCad 10 loads it via the compatibility parser and upgrades in memory, but the file on disk is old-format. PR/issue #187 "Update KiCad footprint format to v20240108 (KiCad 10 support)" (opened by a fork author, closed 2026-03-31) was **closed without being merged**. Practical fix: after conversion run `kicad-cli fp upgrade <base>.pretty` (rewrites in place; add `--output` to write elsewhere).
- README on `master` claims "supports KiCad v6 and newer" - true in the sense that the files load; not true in the sense that it emits current-format files.
- Open issues (none about KiCad 10 format): symbol naming/rendering, GUI requests. Closed history shows older KiCad 6 parse problems were fixed in 2022-2025.

Other gotchas:

- The README itself warns: "The correctness of the symbols and footprints converted ... can't be guaranteed." EasyEDA community parts vary in quality; pad sizes and pin 1 orientation must be checked, and pin electrical types are usually all "unspecified"/"passive" - not KLC S4.4 compliant.
- The 3D model comes from EasyEDA (user-uploaded); alignment errors ("floating 3D parts", issue #91, closed) still occur for some parts.
- Multi-part appends into one `.kicad_sym` had corruption bugs (issue #178, fixed 2026-01) - use v1.0.1.
- Alternative that wraps easyeda2kicad and also imports vendor zips: `Steffen-W/Import-LIB-KiCad-Plugin` (see section 11).

---

## 2. SnapEDA / SnapMagic Search

- Site: <https://www.snapeda.com/> (rebranded SnapMagic Search; help centre at support.snapmagic.com). KiCad landing page: <https://www.snapeda.com/kicad/>.
- Provides: symbol, footprint, 3D model (STEP) per part, in ~15 CAD formats including KiCad. Parts not in the library can be requested ("InstaPart", ~1 business day).
- **Login: yes.** Free account (email/LinkedIn/X sign-up) is required to download. No documented daily limit for KiCad.
- KiCad download contents (help article "How to import into KiCad (V6 and later)" and forum reports): a zip with `<part>.kicad_sym`, `<part>.kicad_mod` (loose, not inside a `.pretty`; you point KiCad at the folder), a `.step` (sometimes named `.kicad_step` in older exports) and a how-to text. Format is the v6+ `.kicad_sym` s-expression; footprints are v6-era stamps - fine for KiCad 10 after auto-upgrade.
- KiCad plugin: the official SnapEDA KiCad plugin only targets KiCad **5.1.x** (help article says "compatibility for versions up to v5.1.10") - do not use it. The "SnapMagic Desktop App" (Windows/macOS) supports up to **KiCad v7** per the changelog - it auto-places downloads into libraries; nothing newer documented.
- **API: exists** (<https://www.snapeda.com/get-api/>): HTTP API returning symbols/footprints/3D for distributors, manufacturers and assemblers. "Free and Premium versions" but access is by request form/email; no self-serve key, no public rate-limit docs. Not practical for an ad-hoc agent.
- CLI/pip/npm: none official. Community: `Steffen-W/Import-LIB-KiCad-Plugin` imports SnapEDA zips (v4 and v6 formats) and has a CLI.
- Gotchas: many SnapEDA footprints are auto-generated from IPC-7351 and use `_HandSoldering`-style large pads; silkscreen and courtyard are often not KLC compliant (silk over pads, no F.Fab outline). Symbols frequently have pins in physical rather than functional order (S4.2) and "passive" electrical types. 3D model is not always linked in the footprint - check the `(model ...)` path.

---

## 3. Ultra Librarian

- Site: <https://www.ultralibrarian.com/>, app at <https://app.ultralibrarian.com/>. KiCad page: <https://www.ultralibrarian.com/cad-vendors/kicad/>. KiCad help: <https://app.ultralibrarian.com/content/help/kicad-6_0.htm>.
- Provides: symbol, footprint, 3D STEP in 20+ CAD formats; large manufacturer-verified catalogue (TI, Microchip, ST, ADI, Molex, TE, Würth, Samtec, Hirose ...).
- **Login: yes.** Free account ("Free Reader" tier) required at download time. The "Ultra Librarian Reader" desktop tool (Windows) converts `.bxl` vendor files; the web app exports directly.
- KiCad export: choose **"KiCad v6+"** (there is still a "KiCad v5" legacy option). Zip contains `<part>.kicad_sym`, `<part>.kicad_mod` (inside a `footprints.pretty`-style folder or loose depending on export), and `<part>.stp`. The UL help page for 6.0+ is out of date (still mentions a `[date].lib`), but actual v6+ exports are `.kicad_sym`.
- **API: not public.** UL is reachable through partner APIs (Nexar/Octopart, SiliconExpert), each needing its own key. Not usable directly.
- CLI/pip/npm: none official. `Import-LIB-KiCad-Plugin` handles UL zips; `kicad-libsync` (PyPI) merges vendor zips into a project.
- Gotchas: UL 3D models are separate `.stp` files whose path is not always written into the `.kicad_mod`; footprint silkscreen/courtyard often non-KLC (courtyard sometimes missing); pin names may be truncated; multi-unit symbols are rare (everything in one big box). Line-ending and `(tedit)` stamps trigger a rewrite on first save in KiCad 10.

---

## 4. SamacSys / Component Search Engine (Mouser, RS "DesignSpark", Farnell embeds)

- Site: <https://componentsearchengine.com/> (Supplyframe). Mouser product pages ("ECAD Model") and RS/DesignSpark "PCB Part Library" embed it.
- Provides: symbol, footprint, 3D (STEP) in 24+ CAD formats including KiCad. Free.
- **Login: yes**, free account. Downloads are per-part zips.
- Zip layout for KiCad: a `KiCad/` folder with `<part>.kicad_sym` (recent) or `<part>.lib` (older exports), `<part>.kicad_mod`, and a `3D/<part>.stp` folder. Older SamacSys KiCad exports also carried `.dcm`. Format targets "KiCad 5 or later"; loads in 10.
- "Library Loader": a **Windows-only** helper that watches the Downloads folder and merges parts into `SamacSys_Parts.kicad_sym` / `SamacSys_Parts.pretty` (one-time setup per SamacSys instructions). Unofficial cross-platform Rust clone: `olback/library-loader` (needs your CSE login in a TOML file).
- API: none public for individuals.
- CLI/pip/npm: none official; community `ulikoehler/KiCADSamacSysImporter` (Python) and `Import-LIB-KiCad-Plugin` both parse the zips.
- Gotchas: same class of quality issues as UL/SnapEDA (IPC-generated, thin on silkscreen, no F.Fab bevel). Symbol pin ordering is usually physical. The Library Loader writes absolute Windows paths for 3D models unless configured.

---

## 5. Digi-Key

- `Digi-Key/digikey-kicad-library` (GitHub): an **atomic** library (1:1 symbol-to-footprint, Digi-Key metadata fields). README warns it "should be considered **unmaintained**"; last push 2024-03-16. Targets KiCad 5.0+; symbol files are legacy `.lib`/`.dcm` in `digikey-symbols/`, footprints in `digikey-footprints.pretty/`; no 3D models. Licence CC-BY-SA 4.0 with exception. Usable in KiCad 10 only after `kicad-cli sym upgrade digikey-symbols/*.lib`. No resistors/capacitors. Also `digikey-partner-kicad-library` (manufacturer-contributed, same status).
- Digi-Key product pages: the "EDA / CAD Models" row links to **Ultra Librarian** (unlimited free access since 2018) and **SnapEDA** downloads for that part; both open the vendor site and need that vendor's login. There is no Digi-Key-hosted KiCad file. Digi-Key's product API (needs key) returns part data but not CAD files.
- KiCad's own "third party libraries" page lists Digi-Key, Espressif, etc. and PCM-installable packages.

---

## 6. Manufacturer sites - what they actually host

Legend: "UL embed" = the product page opens Ultra Librarian's web reader; "CSE" = SamacSys. "Direct STEP" = a downloadable STEP without leaving the manufacturer site.

| Manufacturer | KiCad-native library? | Symbol/footprint route | 3D STEP | Login for STEP |
|---|---|---|---|---|
| Texas Instruments | No | `webench.ti.com/cad/` "CAD/CAE Symbols" -> UL (BXL or web export). SnapEDA also carries TI. | Package STEP via UL, TraceParts; product page "Design & development" links to UL 3D | UL account |
| Microchip | No | Product page "Symbols" link -> embedded UL reader; download zip includes STEP | via UL | UL account |
| STMicroelectronics | No | Product page "CAD Resources" -> UL and SamacSys; community `piit79/Kicad-STM32` on GitHub. Official KiCad libs already contain most STM32 (symbol generator from ST XML). | via UL / CSE | UL/CSE account |
| Analog Devices (incl. LTC, Maxim) | No | Product page "Design Resources > Symbols & Footprints"; ADI hosts direct downloads (UL BXL + SamacSys) and vendor-neutral 2D symbols; wiki page describes UL Reader flow | ADI hosts `.stp` links on many product pages (direct) | Usually none for ADI-hosted files |
| Espressif | **Yes** - `espressif/kicad-libraries` (targets **KiCad 10**, PCM package `espressif-kicad-addon.zip`, legacy branches for 6/7/8/9). Symbols, `.pretty`, 3D | GitHub / PCM | STEP in repo | none |
| Würth Elektronik | **Yes** - `WurthElektronik/KiCad-Library` (GitHub, pushed 2026-09-10): `symbols/`, `footprints/`, `3dmodels/`, ready `sym-lib-table`/`fp-lib-table`, user manual PDF. Also we-online.com product pages host STEP/IGES/3D-PDF | GitHub | STEP on product page | none (site download free) |
| Molex | No | UL and CSE carry Molex; `molex.com` product page "3D Models / Drawings" requires a **Molex account** for STEP; TraceParts/3Dfindit mirrors | product page (login) or TraceParts | Molex login |
| JST | No | Official KiCad libs (`Connector_JST.pretty`, `Connector_JST.3dshapes`) cover most series. `jst-mfg.com` product page "2D/3D data" offers IGES/STEP/3D-PDF after **registration** (name + company + licence agreement) | product page | JST registration |
| TE Connectivity | No | UL/CSE; `te.com` product page "CAD files" hands off to PARTcommunity/3Dfindit (free account) | PARTcommunity | free account |
| Samtec | No | SnapEDA (200k Samtec models), UL; `samtec.com` "3D Models" page gives STEP **with no login** | product page, direct | none |
| Hirose | No | UL/CSE; `hirose.com` product page links to **TraceParts** (10k models, STEP, free after registering) | TraceParts | TraceParts account |

Summary: only **Espressif** and **Würth** publish KiCad-native libraries themselves; everyone else outsources to UL/SnapEDA/CSE. Direct, login-free STEP is available from Samtec, Würth, ADI (most), and the official `kicad-packages3D` repo. Molex, JST, Hirose, TE require some registration.

Also note the official KiCad libraries (`gitlab.com/kicad/libraries/kicad-symbols`, `kicad-footprints`, `kicad-packages3D`, installed under `KICAD10_*`) already include large manufacturer-specific sets (MCU_ST_STM32*, MCU_Microchip_*, RF_Module (Espressif), Connector_JST/Molex/Hirose/Samtec/Wurth footprints). **Search these first** - `kicad-cli sym export`/`fp export` are not search tools, but a plain `Select-String -Path "$env:ProgramFiles\KiCad\10.0\share\kicad\symbols\*.kicad_sym" -Pattern '\(symbol "STM32F103C8T'` works.

---

## 7. Official generators: kicad-library-tools (formerly kicad-footprint-generator) and symbol generators

### Where it lives now

- `gitlab.com/kicad/libraries/kicad-footprint-generator` **has been merged into** `gitlab.com/kicad/libraries/kicad-library-tools` (default branch `main`, active daily in 2026). `kicad-library-utils` (the symbol tools and KLC checkers) has also been merged into it as the `library_utils/` subdirectory and its old repo is archived/redirecting.
- Package metadata (`pyproject.toml`): name `kicad-library-generators`, version 1.1.3, deps `asteval typing_extensions pyyaml future tabulate pyclipper colorlog`; optional `3d` extra pins `cadquery==2.6.1`, `cadquery-ocp>=7.8.1,<7.9`, `nlopt`, `numpy`.
- **Not on PyPI.** (`pip install KicadModTree` on PyPI gives pointhi's 2020 v1.1.2 - obsolete, do not use.) Install from git in a venv (Windows PowerShell):

```
git clone https://gitlab.com/kicad/libraries/kicad-library-tools.git
cd kicad-library-tools
python -m venv .venv
.\.venv\Scripts\Activate
pip install -e .          # footprints only (wiki: ./manage.sh update_dev_packages does this + dev deps)
pip install -e ".[3d]"    # add CadQuery for 3D model generation (big download)
```

Layout: `KicadModTree/` (node-tree footprint framework), `src/kilibs/` (geometry, `config/ipc_configs/ipc_7351b.yaml`, `ipc7351B_2terminal.yaml`, `ipc7352_ball.yaml`, `config/global_configs/config_KLCv3.0.yaml`, `ipc_rules.py`), `src/generators/<family>/` (YAML-driven generators, e.g. `package/gullwing`, `package/no_lead`, `package/grid_array`, `package/DIP`, `package/TO_SOT`, `connector`, `inductor`, `crystal_resonator_oscillator` ...), `src/generators/generate.py` (runner), `library_utils/klc-check/check_symbol.py`, `check_footprint.py`, `library_utils/common/kicad_sym.py`, `kicad_mod.py`, `library_utils/symbol-generators/from_csv_generator.py`, `example-generator.py`.

### Running the IPC generators (wiki "Run a generator" and "IPC gullwing generator")

```
cd src\generators
python generate.py -l                                  # list generators
python generate.py -f OUT_DIR -g package/gullwing      # run one family
python generate.py -p package/gullwing -h              # generator-specific help
   --ipc-density {L,N,M}   (default N)   --ipc-rules ipc_7351b   --global-config config_KLCv3.0
```

Generators read YAML size definitions. Minimal SOIC-8 definition (gullwing generator keys, from the wiki):

```yaml
FileHeader:
  library_Suffix: 'SO'          # -> Package_SO.pretty
  device_type: 'SOIC'
SOIC-8_3.9x4.9mm_P1.27mm:
  size_source: 'https://www.ti.com/lit/ml/msoi002j/msoi002j.pdf'
  body_size_x: 3.9
  body_size_y: 4.9
  overall_size_x: {minimum: 5.8, maximum: 6.2}
  lead_width: {minimum: 0.31, maximum: 0.51}
  lead_len: {minimum: 0.4, maximum: 1.27}
  pitch: 1.27
  num_pins_x: 0
  num_pins_y: 4
```

Dimensions accept a scalar, `{minimum, maximum}`, or `{nominal, tolerance}`. `num_pins_x: 0` makes a two-row (SOIC-like) part; give both for QFP. Exposed pads via `EP_size_x/y`, `EP_num_paste_pads`, `EP_paste_coverage`. Output is KLC-compliant (F.Fab outline with pin-1 bevel, F.CrtYd 0.05 mm on 0.01 grid, 0.12 mm silk, `${KICAD10_3DMODEL_DIR}`-style model path from the global config, rounded-rect pads, IPC-7351B fillets from `ipc_7351b.yaml`, name like `SOIC-8_3.9x4.9mm_P1.27mm`). `no_lead` covers QFN/DFN/LGA, `grid_array` covers BGA/CSP (uses `ipc7352_ball.yaml`), `DIP`/`SIP`/`TO_SOT` cover THT.

### Writing a footprint directly with KicadModTree

From `src/generators/example_kicadmodtree_script.py` (trimmed):

```python
from KicadModTree import Footprint, FootprintType, Property, Rectangle, Pad, Model, KicadFileHandler
fp = Footprint("MyPart_SOT-23", FootprintType.SMD)
fp.setDescription("SOT-23 example")
fp.setTags("sot23")
fp.append(Property(name=Property.REFERENCE, text="REF**", at=[0, -3], layer="F.SilkS"))
fp.append(Property(name=Property.VALUE, text="MyPart_SOT-23", at=[0, 3], layer="F.Fab"))
fp.append(Rectangle(start=[-1.5, -0.7], end=[1.5, 0.7], layer="F.Fab", width=0.10))
fp.append(Rectangle(start=[-1.75, -1.6], end=[1.75, 1.6], layer="F.CrtYd", width=0.05))
for n, (x, y) in enumerate([(-0.95, 1.0), (0.95, 1.0), (0, -1.0)], start=1):
    fp.append(Pad(number=n, type=Pad.TYPE_SMT, shape=Pad.SHAPE_ROUNDRECT,
                  at=[x, y], size=[0.6, 1.2], layers=Pad.LAYERS_SMT))
fp.append(Model(filename="${MY3D}/MyLib.3dshapes/MyPart_SOT-23.step"))
KicadFileHandler(fp).writeFile("MyPart_SOT-23.kicad_mod")
```

(The in-repo example uses `generators.tools.footprint.save_footprint.write_footprint` and `kilibs.config.global_config` to pick up the KLC config; `KicadFileHandler` is the low-level writer.)

### Symbol generation

- `library_utils/symbol-generators/from_csv_generator.py pinout.csv --output NAME.kicad_sym` - CSV columns per `template.csv` (pin number, name, electrical type, side, etc.); documented on the wiki "Spreadsheet-driven symbol generator". Uses `library_utils/common/kicad_sym.py` (load/edit/save `.kicad_sym`; `KicadSymbol`, `Pin`, `Property` classes). There is no separate "kicad-symbol-generator" repo; the STM32/AVR/connector generators live under `symbol-generators/`.
- `library_utils/klc-check/check_symbol.py <lib.kicad_sym> [-c SYMBOL] -vv` and `check_footprint.py <fp.kicad_mod> -vv` - the same KLC checkers the official CI runs. **Run these on anything downloaded from a vendor.**
- Alternatives on PyPI: `kipart` 2.8.0 (2026-08-08; CSV/Excel -> `.kicad_sym`, includes `kilib2csv`, README has an "Using KiPart from an AI agent" section), `kicad-sym` 0.5.3 (2026-08-14, s-expression helper), `kiutils` 1.4.8 (2024, parser for KiCad 6+ files - older stamps), `kicad-tools` (rjwalters, `pip install kicad-tools`; `SymbolLibrary.create()` API, parametric footprint generators with IPC-7351 names, and `kct datasheet search/download`).

---

## 8. Datasheet-driven generation

Tools that read a PDF:

- **uConfig** (`Robotips/uConfig`, Qt/C++, Windows binaries via AppVeyor, pushed 2026-02): Poppler text extraction + rule files (`.kss`) to find pin number/name pairs; `uconfig datasheet.pdf -o lib.lib -r microchip.kss`. Outputs **legacy `.lib`** - run `kicad-cli sym upgrade lib.lib -o lib.kicad_sym`. Works well for large pin-count MCUs; needs a tidy pinout table.
- **ProtoFlow** (protoflow.ai) - commercial browser tool: part number / datasheet PDF / image -> symbol + IPC-7351B footprint for KiCad. Login, no CLI.
- **kicad-tools** (rjwalters): `kct datasheet download MPN` fetches PDFs; symbol/footprint builders are then driven by code, not by parsing the drawing.
- **Agent approach** (recommended when no library exists): extract the pinout table with `pdfplumber` (`page.extract_tables()`) or `camelot`, normalise to the `from_csv_generator.py` / `kipart` CSV columns (number, name, type, side/unit), generate the symbol; read the package drawing's body/lead dimensions into a gullwing/no_lead/grid_array YAML and run `generate.py`; then `check_symbol.py`/`check_footprint.py`. A KiCad forum thread ("LLM prompt to generate symbol pin table from datasheet") reports this works even with local models. Note pdfplumber cannot read dimension drawings that are vector art with detached numbers - fall back to reading the "Recommended land pattern" table or the JEDEC outline code (MS-012 etc.) and let the IPC generator compute pads.

IPC-7351B essentials to encode:

- Land pattern name suffix = density: **M** (Most, level A: max fillets, hand solder/rework), **N** (Nominal, level B: default), **L** (Least, level C: HDI). Toe/heel/side goals (Jt/Jh/Js) and courtyard excess per level are encoded in `src/kilibs/config/ipc_configs/ipc_7351b.yaml` (`ipc_spec_gw_large_pitch`, IPC-7351B table 3-2, gull-wing pitch > 0.625 mm): L: toe 0.15, heel 0.25, side 0.01, courtyard 0.10 mm; N: 0.35 / 0.35 / 0.03 / 0.25 mm; M: 0.55 / 0.45 / 0.05 / 0.50 mm, all rounded to 0.05. For pitch <= 0.625 mm (`ipc_spec_gw_small_pitch`, table 3-3) the side goals become -0.04 / -0.02 / 0.01. The same file sets `min_ep_to_pad_clearance: 0.2`.
- Pad length = (Lmax - Lmin lead span math) + 2 x fillet + RSS tolerance; KiCad generators do this in `kilibs/config/ipc_rules.py`.
- Naming per IPC-7351B, e.g. `SOIC127P600X175-8N`, is *not* what KLC uses; KLC names are `SOIC-8_3.9x4.9mm_P1.27mm` (F2.x). Keep IPC naming only in the description/keywords.
- Free web IPC calculator without login: `pcbeditor.com/tools/footprint-generator` (SOIC/SOP/SSOP/TSSOP/QFP dual-row gullwing only; outputs a `.kicad_mod` with pads, pin-1 silk dot and F.Fab outline; no QFN/BGA). KiCad's built-in *Footprint Wizard* (Footprint Editor > New footprint using wizard) has Python wizards for QFP, QFN, BGA, DIP, SOIC etc. using IPC-style parameters; scriptable via the KiCad Python API but only inside KiCad.

---

## 9. KiCad Library Conventions (KLC)

- Site: <https://klc.kicad.org/> (Cloudflare-gated for scripts; source is `gitlab.com/kicad/libraries/klc`, `content/<section>/<rule>.adoc`, active 2026-09).
- Rule families: G1-G3 general, S1-S7 symbols, F1-F9 footprints, M1-M2 3D models.

Most important rules (numbers and wording from the source `.adoc` files):

**Symbols**

1. **S1.1** Library names by function: `Function_SubFunction_Manufacturer_Series` (e.g. `MCU_Microchip_PIC32`, `Sensor_Temperature`).
2. **S2.1 / S2.2** Fully specified symbols are named by MPN; non-functional MPN suffixes (temp grade, reel) replaced by lowercase `x` wildcard or dropped when trailing; manufacturer name first only if the same name exists from several makers.
3. **S2.3** One symbol per package; pin-compatible packages use "derive from existing symbol".
4. **S3.1** Origin centred on the symbol (or as close as possible while keeping pins on the 100 mil grid).
5. **S3.2** Text size 50 mil (1.27 mm) for all fields; pin name/number may go down to 20 mil.
6. **S3.3** Body line width 10 mil (0.254 mm); black-box ICs filled with background colour, discretes unfilled.
7. **S3.6** Pin name offset 20 mil preferred (min 20, max 50 mil).
8. **S3.7** Exposed pad number = pin count + 1; shield pins `SH`; mechanical pads `MP`; NPTH get no pin.
9. **S4.1** 100 mil (2.54 mm) grid; pin origin on a grid node; length >= 100 mil, in 50 mil steps, <= 300 mil; two-character pin numbers -> 100 mil, three -> 150 mil; all pins same length; unique numbers; names as datasheet; multi-function pins use alternate pin functions.
10. **S4.2** Group by function: power in at top, GND at bottom, inputs left, outputs right; ports top-to-bottom.
11. **S4.3** Use KiCad 10 native pin stacks (the old "same-position duplicate pins" workaround is now forbidden); never stack `No Connect`; stack power/GND.
12. **S4.4** Electrical types: power pins `Power Input`/`Power Output`; MCU I/O `Bidirectional`; no double inversion (bar + inverting graphic).
13. **S4.6** Hidden pins forbidden except NC pins (invisible, type `Not Connected`, pin end inside the outline) and power-symbol pins.
14. **S4.7** Active-low names as `~{RESET}`, dropping the vendor `n`/`#`/`/` prefix.
15. **S5.1 / S5.2** Footprint field `Lib:Footprint` for fully specified symbols (blank for generic); footprint filters end with `*`, escape `-`/`_` as `?`, include pin count only when the symbol omits pins, include `1EP`/`SH`/`MP` specifiers.
16. **S6.2** Reference visible, Value visible (= symbol name), Footprint and Datasheet filled but invisible (`~` datasheet for generic), Description comma-separated ending with package (e.g. `SOIC-8`), Keywords space-separated with no words already in the description, no other custom fields (except `KLC_*` after librarian discussion). (S6.1 provides the RefDes table.)

**Footprints**

1. **F1.1** Library names by function: `Conn_USB_SMD`, `Capacitor_Tantalum_SMD`, `Conn_Molex_MicroFit`.
2. **F2.1 / F2.2** Name = package, `-` pin count (`-1EP`, `-1SH`, `-1MP` suffixes), `_` separated fields: body `LxW[xH]mm`, `P<pitch>mm`, `Drill`, `Pad`, `Horizontal|Vertical`, modifiers `_HandSoldering`, `_ThermalVias`, `_CircularHoles`. Examples `SOIC-8_3.9x4.9mm_P1.27mm`, `QFN-16-1EP_3x3mm_P0.5mm_EP1.8x1.8mm`, `LQFP-32_4x4x1.1mm_P1.65mm`.
3. **F3.1** SMD chip naming `R_0603_1608Metric`, `C_0402_1005Metric`, `CP_...`, `D_...`; metric code carries the `Metric` suffix (F3.3 for capacitor variants).
4. **F2.3** Manufacturer-specific footprints are prefixed `Manufacturer_MPN_` (e.g. `Texas_S-PVQFN-N48_`).
5. **F4.1** Datasheet beats KLC when they conflict. **F4.2** Pin 1 top-left (inline/2-pin parts: pin 1 left). **F4.3** Connected copper shares the pad number (thermal vias = EP number). **F4.4** Thermal vias: same number as EP, 0.2-0.3 mm hole, no paste over vias >= 0.3 mm, B.Cu relief pad, `_ThermalVias` suffix plus a plain variant. **F4.6** Local clearances 0.
6. **F5.1** Silkscreen: RefDes on F.SilkS 1.0 mm text, 0.15 mm thickness; line width 0.12 mm nominal (0.10-0.15 allowed); no silk over pads or under SMD bodies; 0.2 mm recommended clearance to copper; pin-1/polarity marker on silk (filled chevron preferred; 0.25 mm dot for tiny parts; `+` for caps); 0.5 mm from board edge for edge connectors.
7. **F5.2** F.Fab: simplified body outline at nominal size, 0.10 mm line (0.10-0.15); pin-1 bevel = min(1 mm, 25 % of body); Value text on F.Fab 1.0 mm (0.5-1.0) below the part; a second RefDes `${REFERENCE}` centred in the body, scaled to fit 4 characters, 0.5-1.0 mm.
8. **F5.3** Courtyard on F.CrtYd, 0.05 mm line, all points on a 0.01 mm grid; clearance 0.25 mm default, 0.15 mm for parts < 1.5 mm in any dimension, 0.5 mm connectors/canned caps/crystals, 1.0 mm BGA/WLCSP; polygon courtyards allowed.
9. **F6.1** SMD footprints set type `SMD` (so they appear in .pos); **F6.2** anchor at body centroid; **F6.3** SMD pad layers `F.Cu F.Mask F.Paste` only, rounded-rectangle pads (radius 25 % of the short edge, max 0.25 mm), EP paste 50-80 % (65 %) via numberless aperture pads, >= 0.2 mm EP-to-pad clearance, heatsink/BGA/mechanical pad fabrication properties, heatsink pads zone connection `solid`.
10. **F7.1-F7.4** THT footprints: type `Through Hole`, anchor at pin 1, pin 1 rect/rounded-rect and others round/oval, pads on all copper + F.Mask + B.Mask, never silk layers.
11. **F7.5 / F7.6 / F7.7** Annular ring >= 0.15 mm; finished hole = max lead + 0.2 mm; slots need 0.2 mm all round and lead aspect ratio > 2, with a `_CircularHoles` alternative.
12. **F8.1** Non-SMD/THT (fiducials, holes, logos, test points): type `Other`, exclude from position file, usually exclude from BOM.
13. **F9.1** Reference = `REF**`, Value = footprint name = filename, Description comma-separated with datasheet URL, Keywords space-separated. **F9.2** Move/Place `Free`, local clearances 0.
14. **F9.3** Every real footprint has a 3D model reference even if the file does not exist yet; model dir named `<library>.3dshapes`, file named as the footprint, `.step` only, scale 1:1:1, offset and rotation 0, path prefixed `${KICAD9_3DMODEL_DIR}/` in the KLC text (use `${KICAD10_3DMODEL_DIR}/` for KiCad 10 official libs; your own variable for private libs).
15. **M2.1 / M2.2** 3D contributions are STEP, aligned and rotated so the footprint needs offset (0,0,0), scale (1,1,1), rotation 0. **M1.1** You must own the rights - vendor-downloaded STEP files cannot be contributed to the official library (fine for private use). **G1.1** Names use only `A-Z a-z 0-9 _ - . , +`, no spaces. **G1.7** LF line endings.

---

## 10. Other useful tooling discovered

- **`Steffen-W/Import-LIB-KiCad-Plugin`** (PCM-installable, pushed 2026-05-01, badges say KiCad 6-9 but it is plain Python and the CLI is KiCad-independent): imports zips from **SnapEDA, Ultra Librarian, SamacSys/CSE, Octopart, and LCSC/EasyEDA** into per-source libraries (`Snapeda.kicad_sym`, `UltraLibrarian.pretty`, ...) under a `${KICAD_3RD_PARTY}` variable, relinking 3D models. CLI from the `plugins` dir: `python -m KiCadImport --download-file part.zip --lib-folder D:\libs\KiCad [--prefer-step] [--path-variable '${KIPRJMOD}'] [--lib-name X]`, or `--easyeda C2040`. This is the single best "normalise whatever the vendor gave me" step for an agent.
- `kicad-libsync` (PyPI) - merges vendor zips into a project's libraries.
- `ulikoehler/KiCADSamacSysImporter`, `embedism/samacsys-kicad-extractor` - SamacSys-specific.
- Official 3D model library online index: <https://kicad.github.io/packages3d/> and footprints <https://kicad.github.io/footprints/> (browse before generating anything).
- TraceParts / 3Dfindit / PARTcommunity / GrabCAD - STEP mirrors for connectors (accounts needed on TraceParts and PARTcommunity; GrabCAD models are user-contributed and unverified).

---

## 11. Recommendation: order of attack per input type

Common first steps for every case:

1. Search the **official KiCad 10 libraries** installed under `KICAD10_SYMBOL_DIR` / `KICAD10_FOOTPRINT_DIR` / `KICAD10_3DMODEL_DIR` for the MPN, its package (`SOIC-8_3.9x4.9mm_P1.27mm`), and the manufacturer series. If both symbol and footprint exist, stop.
2. Whatever you obtain from outside, run `kicad-cli sym upgrade` / `kicad-cli fp upgrade`, then `library_utils/klc-check/check_symbol.py -vv` and `check_footprint.py -vv`, and fix the usual vendor defects (courtyard, F.Fab outline + bevel, silk width 0.12, pin electrical types, 3D model path with a path variable).

**(a) LCSC number (`C12345`)** - `pip install easyeda2kicad` then `easyeda2kicad --full --lcsc_id C12345 --output <projlib> --project-relative`; no login, gives symbol + footprint + WRL/STEP in one shot. Then `kicad-cli fp upgrade <projlib>.pretty` (files are written in the legacy `(module ...)` format), KLC-check, set pin types. If EasyEDA has no model or it is poor, fall back to (b) using the MPN printed on the LCSC page.

**(b) Manufacturer part number** - (1) official libraries; (2) if the maker is Espressif or Würth, clone their GitHub KiCad library (KiCad-10 native, no login); (3) SnapEDA -> Ultra Librarian -> Component Search Engine, in that order (all need a free account; SnapEDA's KiCad zip is the cleanest, UL has the widest manufacturer-verified coverage, CSE is the Mouser/RS path). Feed the zip to `Import-LIB-KiCad-Plugin`'s `KiCadImport` CLI. (4) If none has it, try the LCSC search for the MPN and use (a). (5) Otherwise generate: pinout CSV -> `from_csv_generator.py`/`kipart`; package dims -> `kicad-library-tools` gullwing/no_lead/grid_array YAML -> `generate.py`; STEP from the official `kicad-packages3D` generic package model or the vendor's STEP.

**(c) Manufacturer product-page URL** - Fetch the page and look for, in order: a KiCad/"ECAD models"/"Symbols & footprints" link (ADI hosts direct files; TI/Microchip/ST/Molex/TE/Samtec/Hirose link out to UL/SnapEDA/CSE - follow it, it lands on the vendor's page for that exact MPN); a "3D model"/"CAD" link (Samtec, Würth, ADI direct; Molex/JST/Hirose/TE via account or TraceParts); the datasheet PDF link. Extract the MPN and package code from the page and continue with (b); if the page only yields a datasheet, continue with (d). Keep any manufacturer-hosted STEP as the 3D model even when the symbol/footprint come from elsewhere.

**(d) Only a datasheet PDF** - (1) Read the ordering-information table to get the MPN(s) and package, then try (b) - a datasheet-only start usually still means the part exists on SnapEDA/UL. (2) If not: `pdfplumber` the pinout table -> CSV -> symbol (`from_csv_generator.py` or `kipart`), or uConfig for large MCUs (then `kicad-cli sym upgrade`); read the package outline (JEDEC code or body/lead dims) -> IPC generator YAML -> `generate.py -f out -g package/<family>` with `--ipc-density N` (use `L` for hand-solder variants named `_HandSoldering`); pick a matching generic STEP from `kicad-packages3D` (`Package_SO.3dshapes/SOIC-8_3.9x4.9mm_P1.27mm.step`) or generate one via the `[3d]` CadQuery extra. (3) KLC-check and add F9.1 metadata (datasheet URL in Description).

Login-free paths only: official libs, Espressif/Würth GitHub, easyeda2kicad/LCSC, Samtec/ADI/Würth STEP, `kicad-library-tools` generation, pcbeditor.com IPC calculator. Everything else (SnapEDA, UL, CSE, Digi-Key/Mouser embeds, Molex, JST, Hirose/TraceParts, TE/PARTcommunity) needs a free account that the agent cannot create on the user's behalf - ask the user to download the zip and hand it over, then import with `KiCadImport`.

## Sources (fetched 2026-09-14)

- easyeda2kicad README, `__main__.py`, `kicad/parameters_kicad_footprint.py`, `kicad/parameters_kicad_symbol.py`, `kicad/export_kicad_symbol.py`, PR #187 (github.com/uPesy/easyeda2kicad.py); PyPI JSON for `easyeda2kicad`
- snapeda.com/kicad, snapeda.com/get-api, support.snapmagic.com articles 3804094 and 5995733, changelog.snapmagic.com (desktop app v7)
- ultralibrarian.com/faq, app.ultralibrarian.com/content/help/kicad-6_0.htm, docs.tscircuit.com Ultra Librarian import guide
- componentsearchengine.com/learn-more, supplyframe.com/samacsys, rs-online DesignSpark Library Loader article
- github.com/Digi-Key/digikey-kicad-library README; Digi-Key press releases on Ultra Librarian / SnapEDA
- github.com/espressif/kicad-libraries README; github.com/WurthElektronik/KiCad-Library
- webench.ti.com/cad, microchip.com CAD/CAE symbols page, analog.com symbols-and-footprints page and wiki.analog.com Ultra Librarian page, jst-mfg.com, hirose.com TraceParts release, blog.samtec.com 3D models, TE PARTcommunity
- gitlab.com/kicad/libraries/kicad-library-tools (`pyproject.toml`, README, `src/generators/example_kicadmodtree_script.py`, `src/kilibs/config/ipc_configs`, `library_utils/README.md`), group wiki pages Generators, Generators/Setup, Generators/Run-a-generator, Footprint-Generators/Gullwing
- gitlab.com/kicad/libraries/klc `content/**/*.adoc`
- gitlab.com/kicad/code/kicad branch 10.0: `pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr.h`, `eeschema/sch_file_versions.h`; docs.kicad.org/10.0 kicad manual (path variables) and cli manual (sym/fp upgrade)
- github.com/Robotips/uConfig, github.com/Steffen-W/Import-LIB-KiCad-Plugin, github.com/devbisme/KiPart, github.com/rjwalters/kicad-tools, pcbeditor.com/tools/footprint-generator, PyPI JSON for kipart, kicad-sym, kiutils, KicadModTree
