"""Extract a *draft* pin table from a datasheet PDF.

Datasheet pin tables come in many layouts: one number column, several
package columns (TI: ``NAME | DQN | DBV | I/O | DESCRIPTION``), number before
name, name before number, multi-row headers. This module finds tables whose
header mentions pins (pdfplumber), maps the columns by header words, lets the
caller pick the package column, and normalises rows into a ``symgen`` pin
table with a guessed KiCad electrical type, symbol side and a confidence.
Pages without recognisable tables fall back to line-based text parsing only
when the page has a pin-description heading.

It is a transcription aid, not an oracle: the agent must show the result to
the user next to the datasheet page and fix it before generating a symbol.

Install: ``pip install pdfplumber`` (preferred) or ``pip install pypdf``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

TYPE_WORDS = {
    "no_connect": ["no connect", "not connected", "no internal connection", "do not connect", "not used", "n.c."],
    "power_out": ["regulated output", "output voltage", "ldo output", "power output"],
    "power_in": ["power supply", "supply voltage", "supply input", "positive supply", "ground pin", "ground",
                 "gnd", "supply pin", "power input", "input voltage", "input pin. for best transient",
                 "thermal pad", "exposed pad"],
    "output": ["output pin", "output.", "driver output", "clock output", "reset output", "power good",
               "interrupt output", "open-drain output", "open drain output", " output"],
    "input": ["input pin", "enable pin", "enable input", "reset input", "chip select", "clock input", "strobe",
              "shutdown", "adjust pin", "feedback pin", " input"],
    "bidirectional": ["i/o", "input/output", "bidirectional", "gpio", "general purpose", "data line"],
    "passive": ["crystal", "oscillator", "xtal", "external resistor", "external capacitor", "bootstrap"],
}
SHORT_TYPES = {
    "I": "input", "IN": "input", "INPUT": "input", "O": "output", "OUT": "output", "OUTPUT": "output",
    "I/O": "bidirectional", "IO": "bidirectional", "B": "bidirectional", "INPUT/OUTPUT": "bidirectional",
    "P": "power_in", "PWR": "power_in", "POWER": "power_in", "S": "power_in", "G": "power_in", "GND": "power_in",
    "NC": "no_connect", "N/C": "no_connect", "-": "passive", "—": "passive", "–": "passive", "A": "passive",
    "AI": "input", "AO": "output", "DI": "input", "DO": "output", "DIO": "bidirectional", "OD": "open_collector",
    "PI": "power_in", "PO": "power_out", "PU": "input", "PD": "input",
}
NAME_RE = re.compile(r"^[A-Za-z~\\/#][A-Za-z0-9_+\-/\.#~{}]*$")
PINNUM_RE = re.compile(r"^(?:[A-Z]{1,2}\d{1,3}|\d{1,3})(?:\s*[,/]\s*(?:[A-Z]{1,2}\d{1,3}|\d{1,3}))*$")
NUMBER_HEADERS = ("no.", "no", "number", "pin no", "pin number", "pin #", "#", "pins")
NAME_HEADERS = ("name", "symbol", "pin name", "signal", "function", "designation")
TYPE_HEADERS = ("i/o", "type", "io", "direction", "dir")
DESC_HEADERS = ("description", "function", "descriptions", "comment")


@dataclass
class DraftPin:
    number: str
    name: str
    etype: str
    side: str
    confidence: float
    source: str                 # "table p.N" / "text p.N"
    description: str = ""
    raw_type: str = ""

    def to_symgen(self) -> dict:
        d = {"number": self.number, "name": self.name, "type": self.etype, "side": self.side,
             "confidence": round(self.confidence, 2), "source": self.source}
        if self.description:
            d["description"] = " ".join(self.description.split())[:140]
        return d


@dataclass
class Extraction:
    pins: list[DraftPin] = field(default_factory=list)
    pages_scanned: list[int] = field(default_factory=list)
    method: str = ""
    warnings: list[str] = field(default_factory=list)
    package_columns: list[str] = field(default_factory=list)
    package_used: str = ""

    def to_json(self, name: str = "PART") -> dict:
        pins = sorted(self.pins, key=lambda p: _pin_sort_key(p.number))
        return {
            "name": name, "reference": "U", "value": name, "footprint": "", "datasheet": "", "description": "",
            "keywords": "", "fp_filters": "", "units": 1, "power": False,
            "_extraction": {"method": self.method, "pages": sorted(set(self.pages_scanned)),
                            "package_columns": self.package_columns, "package_used": self.package_used,
                            "warnings": self.warnings,
                            "review": "Every pin below is a DRAFT. Compare with the datasheet pin table, fix "
                                      "types/sides, then remove the _extraction and confidence keys before symgen."},
            "pins": [p.to_symgen() for p in pins],
        }


def _pin_sort_key(n: str):
    m = re.match(r"^([A-Za-z]*)(\d*)$", n)
    if m:
        return (m.group(1), int(m.group(2) or 0))
    return (n, 0)


def clean_name(name: str) -> str:
    name = " ".join(name.split())
    name = re.sub(r"\(\d+\)$", "", name).strip()      # footnote markers
    name = name.replace(" ", "")
    m = re.match(r"^(?:/|\\|!|#|n(?=[A-Z]{3,}))([A-Za-z][A-Za-z0-9_]*)$", name)
    if m:
        return "~{" + m.group(1) + "}"
    m = re.match(r"^([A-Za-z][A-Za-z0-9_]*?)(?:#|_N|_n|\\|_B)$", name)
    if m and not m.group(1).upper().endswith("EN"):
        return "~{" + m.group(1) + "}"
    return name


def guess_type(name: str, raw_type: str, description: str) -> tuple[str, float]:
    rt = " ".join(raw_type.split()).upper()
    rt = re.sub(r"\(\d+\)$", "", rt).strip()
    if rt in SHORT_TYPES:
        base = SHORT_TYPES[rt]
        # "—" for GND/NC rows means power/nc, not passive
        n = name.upper().strip("~{}")
        if base == "passive" and n.startswith(("GND", "VSS", "VDD", "VCC", "VIN", "VBAT")):
            return "power_in", 0.85
        if base == "passive" and n in ("NC", "N/C", "DNC"):
            return "no_connect", 0.95
        # regulators/converters call their supply pins "Input"/"Output"; KiCad wants power types
        if base == "input" and (n in ("IN", "VIN", "VI", "VCC", "VDD", "VBAT") or n.startswith(("VIN", "VDD", "VCC"))):
            return "power_in", 0.85
        if base == "output" and (n in ("OUT", "VOUT", "VO") or n.startswith("VOUT")):
            return "power_out", 0.85
        return base, 0.9
    n = name.upper().strip("~{}")
    if n in ("NC", "N/C", "N.C.", "DNC"):
        return "no_connect", 0.95
    if n in ("GND", "VSS", "VSSA", "AGND", "DGND", "PGND", "EP", "EPAD", "PAD", "GNDA", "GNDD", "THERMALPAD") or n.startswith(("GND", "VSS")):
        return "power_in", 0.9
    if n.startswith(("VDD", "VCC", "AVDD", "DVDD", "VBAT", "VIN", "VDDA", "VDDIO", "VBUS", "AVCC", "DVCC", "VPP")):
        return "power_in", 0.85
    if n in ("VOUT", "VO") or n.startswith("VOUT"):
        return "power_out", 0.7
    d = " " + description.lower()
    for etype, words in TYPE_WORDS.items():
        for w in words:
            if w in d:
                conf = 0.7
                if etype == "power_in" and n in ("IN", "OUT"):
                    etype = "power_in" if n == "IN" else "power_out"
                if etype == "output" and n == "OUT" and "regulated" in d:
                    etype = "power_out"
                return etype, conf
    if re.match(r"^P[A-Z]\d{1,2}$", n) or n.startswith(("GPIO", "IO", "PIO", "MT")):
        return "bidirectional", 0.8
    if n.startswith(("EN", "CS", "NRST", "RESET", "RST", "SHDN", "CLK", "SCK", "SCL", "MOSI", "SDI", "RX", "RXD", "BOOT", "ADJ", "FB")):
        return "input", 0.6
    if n.startswith(("INT", "IRQ", "MISO", "SDO", "TX", "TXD", "PG", "DRDY", "ALERT", "DOUT")):
        return "output", 0.6
    if n in ("SDA", "D+", "D-", "DP", "DM", "DQ") or n.startswith(("SDA", "DATA")):
        return "bidirectional", 0.5
    return "passive", 0.3


def guess_side(name: str, etype: str) -> str:
    n = name.upper().strip("~{}")
    if etype == "power_in" and (n.startswith(("GND", "VSS", "AGND", "DGND", "PGND", "EP", "PAD", "THERMAL")) or n in ("GNDA", "GNDD")):
        return "bottom"
    if etype == "power_in":
        return "top"
    if etype == "input":
        return "left"
    if etype in ("output", "power_out", "open_collector", "open_emitter", "no_connect", "bidirectional"):
        return "right"
    return "left"


# --------------------------------------------------------------------------- #
# Table handling
# --------------------------------------------------------------------------- #
@dataclass
class Columns:
    name: int
    numbers: dict[str, int]          # package label -> column index
    type: int | None
    desc: int | None


def _norm(cell) -> str:
    return " ".join(str(cell or "").replace("\n", " ").split()).strip()


def _map_columns(rows: list[list]) -> tuple[Columns | None, int]:
    """Look at the first three rows; return (columns, index of first data row).

    Candidate header depths are scored by how many roles (name, numbers,
    type, description) they identify; the best wins, so a two-row TI header
    (``PIN`` over ``NAME | DQN | DBV | I/O | DESCRIPTION``) beats the
    one-row guess."""
    best: tuple[int, Columns, int] | None = None
    for hdr_rows in (1, 2, 3):
        if len(rows) < hdr_rows + 1:
            break
        cand = _map_columns_depth(rows, hdr_rows)
        if cand is None:
            continue
        score = 1 + len(cand.numbers) + (cand.type is not None) + (cand.desc is not None)
        if best is None or score > best[0]:
            best = (score, cand, hdr_rows)
    if best is None:
        return None, 0
    return best[1], best[2]


def _map_columns_depth(rows: list[list], hdr_rows: int) -> Columns | None:
    if True:
        width = max(len(r) for r in rows[:hdr_rows])
        merged = []
        for ci in range(width):
            parts = [_norm(rows[ri][ci]) if ci < len(rows[ri]) else "" for ri in range(hdr_rows)]
            merged.append(" ".join(p for p in parts if p).lower())
        name_i = next((i for i, h in enumerate(merged) if any(h == k or h.endswith(" " + k) or h.startswith(k + " ") or h == "pin " + k for k in NAME_HEADERS)), None)
        type_i = next((i for i, h in enumerate(merged) if any(re.fullmatch(rf"(pin )?{re.escape(k)}(\(\d+\))?", h) for k in TYPE_HEADERS)), None)
        desc_i = next((i for i, h in enumerate(merged) if any(k in h for k in DESC_HEADERS) and i != name_i), None)
        numbers: dict[str, int] = {}
        for i, h in enumerate(merged):
            if i in (name_i, type_i, desc_i):
                continue
            if any(h == k or h == "pin " + k or h.endswith(" " + k) for k in NUMBER_HEADERS):
                numbers.setdefault("NO", i)
            elif h and (h.startswith("pin ") or hdr_rows > 1) and re.fullmatch(r"(pin )?[a-z0-9\-]{2,12}(\s*\(\d+\))?", h):
                # package code column like "pin dqn", "dbv", "ych", "lqfp48"
                label = h.replace("pin ", "").upper()
                if label not in ("PIN",):
                    numbers.setdefault(label, i)
        if name_i is None and merged and merged[0] == "pin" and len(merged) >= 2 and hdr_rows == 1 \
                and all(not m for m in merged[1:]):
            return None  # a spanning "PIN" banner row; the real header is deeper
        if name_i is None and merged and merged[0].startswith("pin") and len(merged) >= 2:
            # e.g. ["pin", "name", "description"] where pin = number
            numbers.setdefault("NO", 0)
            name_i = 1
        if name_i is not None and numbers:
            return Columns(name_i, numbers, type_i, desc_i)
    return None


def _rows_to_pins(rows: list[list], cols: Columns, package: str | None, page: int, source: str) -> list[DraftPin]:
    if package and package.upper() in cols.numbers:
        num_i = cols.numbers[package.upper()]
    else:
        num_i = next(iter(cols.numbers.values()))
    out: list[DraftPin] = []
    for row in rows:
        cells = [_norm(c) for c in row]
        if len(cells) <= max(cols.name, num_i):
            continue
        raw_nums = cells[num_i]
        name = cells[cols.name]
        if not name or not NAME_RE.match(name.replace(" ", "")):
            # multi-line rows may carry the name on the numbers side; swap if it looks reversed
            if PINNUM_RE.match(name) and NAME_RE.match(raw_nums.replace(" ", "")):
                name, raw_nums = raw_nums, name
            else:
                continue
        if raw_nums in ("", "—", "–", "-", "––", "n/a", "N/A"):
            continue
        if not PINNUM_RE.match(raw_nums):
            continue
        raw_type = cells[cols.type] if cols.type is not None and cols.type < len(cells) else ""
        desc = cells[cols.desc] if cols.desc is not None and cols.desc < len(cells) else ""
        for n in [x.strip() for x in re.split(r"[,/]\s*", raw_nums) if x.strip()]:
            nm = clean_name(name.split("/")[0] if "/" in name and len(name) > 12 else name)
            et, conf = guess_type(nm, raw_type, desc)
            out.append(DraftPin(n, nm, et, guess_side(nm, et), conf, f"{source} p.{page}", desc, raw_type))
    return out


def _text_rows(text: str, page: int) -> list[DraftPin]:
    """Line-based fallback for pages with a pin-description heading but no table."""
    low = text.lower()
    if not any(k in low for k in ("pin description", "pin functions", "pin function", "pin definition",
                                  "pin configuration", "pin assignment", "terminal functions", "pinout")):
        return []
    out: list[DraftPin] = []
    for line in text.splitlines():
        m = re.match(r"^\s*(\d{1,3}|[A-Z]\d{1,2})\s+([A-Za-z~/\\#][A-Za-z0-9_+\-/\.#]{0,20})\s+(I/O|I|O|P|PWR|GND|NC|S|B|Input|Output|Power)?\s*(.*)$", line)
        if not m:
            continue
        name = m.group(2)
        if name.lower() in ("the", "pin", "table", "note", "figure", "page", "of", "and", "to", "for", "in", "is"):
            continue
        if not (name.isupper() or "_" in name or any(ch.isdigit() for ch in name)):
            continue
        nm = clean_name(name)
        et, conf = guess_type(nm, m.group(3) or "", m.group(4))
        out.append(DraftPin(m.group(1), nm, et, guess_side(nm, et), min(conf, 0.6), f"text p.{page}", m.group(4), m.group(3) or ""))
    # need a run of at least three plausible rows to count as a table
    return out if len(out) >= 3 else []


def extract(pdf_path: str | Path, pages: list[int] | None = None, max_pages: int = 80,
            package: str | None = None) -> Extraction:
    pdf_path = Path(pdf_path)
    ex = Extraction()
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        pdfplumber = None
    if pdfplumber is None:
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise RuntimeError("install pdfplumber (preferred) or pypdf to read datasheets") from exc
        ex.method = "pypdf text"
        reader = PdfReader(str(pdf_path))
        page_numbers = pages or list(range(1, min(len(reader.pages), max_pages) + 1))
        for pno in page_numbers:
            got = _text_rows(reader.pages[pno - 1].extract_text() or "", pno)
            if got:
                ex.pins += got
                ex.pages_scanned.append(pno)
    else:
        ex.method = "pdfplumber tables"
        with pdfplumber.open(str(pdf_path)) as pdf:
            page_numbers = pages or list(range(1, min(len(pdf.pages), max_pages) + 1))
            for pno in page_numbers:
                if pno < 1 or pno > len(pdf.pages):
                    continue
                page = pdf.pages[pno - 1]
                text = page.extract_text() or ""
                if "pin" not in text.lower() and "terminal" not in text.lower():
                    continue
                try:
                    tables = page.extract_tables()
                except Exception as exc:  # pragma: no cover
                    ex.warnings.append(f"p.{pno}: table extraction failed: {exc}")
                    tables = []
                found_here = False
                for table in tables:
                    if not table or len(table) < 2:
                        continue
                    cols, first = _map_columns(table)
                    if cols is None:
                        continue
                    for label in cols.numbers:
                        if label not in ex.package_columns:
                            ex.package_columns.append(label)
                    if package and len(cols.numbers) and package.upper() not in cols.numbers \
                            and list(cols.numbers) != ["NO"]:
                        ex.warnings.append(f"p.{pno}: table for packages {list(cols.numbers)} skipped (wanted {package.upper()})")
                        found_here = True  # a real pin table exists here; do not fall back to text parsing
                        continue
                    pins = _rows_to_pins(table[first:], cols, package, pno, "table")
                    if pins:
                        ex.pins += pins
                        found_here = True
                        if not ex.package_used:
                            ex.package_used = (package.upper() if package and package.upper() in cols.numbers
                                               else next(iter(cols.numbers)))
                if not found_here:
                    got = _text_rows(text, pno)
                    if got:
                        ex.pins += got
                        found_here = True
                if found_here:
                    ex.pages_scanned.append(pno)
    ex.pins = _dedupe(ex.pins)
    if package and ex.package_columns and package.upper() not in [c.upper() for c in ex.package_columns]:
        ex.warnings.append(f"package column {package!r} not found; columns seen: {ex.package_columns}")
    if not ex.pins:
        ex.warnings.append("no pin table recognised; pass --pages with the pin-description pages, or transcribe manually")
    else:
        ints = sorted({int(p.number) for p in ex.pins if p.number.isdigit()})
        if ints:
            missing = [i for i in range(1, ints[-1] + 1) if i not in ints]
            if missing:
                ex.warnings.append(f"pin numbers missing from the draft: {missing[:20]}")
        low = [p for p in ex.pins if p.confidence < 0.5]
        if low:
            ex.warnings.append(f"{len(low)} pins have low-confidence types; check them first: "
                               + ", ".join(f"{p.number}({p.name})" for p in low[:10]))
    return ex


def _dedupe(pins: list[DraftPin]) -> list[DraftPin]:
    best: dict[str, DraftPin] = {}
    for p in pins:
        cur = best.get(p.number)
        if cur is None or p.confidence > cur.confidence or (p.confidence == cur.confidence and len(p.description) > len(cur.description)):
            best[p.number] = p
    return list(best.values())
