"""Part lookups for sourcing decisions.

* LCSC / JLCPCB: the EasyEDA component API answers for an LCSC number
  (``C8734``) with price, stock, package, manufacturer, JLCPCB part class
  (basic/extended) and the datasheet link. No key needed.
* Keyword / MPN search: LCSC and JLCPCB search endpoints are bot-protected;
  ``search`` therefore returns instructions for the agent (web search the
  MPN plus "LCSC" or "site:lcsc.com") rather than pretending.
"""
from __future__ import annotations

import json
import re
import urllib.request

EASYEDA_COMPONENT = "https://easyeda.com/api/products/{lcsc}/components"
LCSC_RE = re.compile(r"^C\d{2,9}$", re.IGNORECASE)


def _get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 kicad-skills", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        return json.load(resp)


def lcsc_lookup(lcsc: str) -> dict:
    """Return a normalised record for an LCSC part number, or {'found': False}."""
    lcsc = lcsc.strip().upper()
    if not LCSC_RE.match(lcsc):
        raise ValueError(f"{lcsc!r} is not an LCSC number (expected like C8734)")
    try:
        data = _get_json(EASYEDA_COMPONENT.format(lcsc=lcsc))
    except Exception as exc:
        return {"found": False, "lcsc": lcsc, "error": str(exc)}
    if not data.get("success") or not data.get("result"):
        return {"found": False, "lcsc": lcsc}
    r = data["result"]
    para = (r.get("dataStr") or {}).get("head", {}).get("c_para", {})
    lc = r.get("lcsc") or {}
    pkg = (r.get("packageDetail") or {}).get("title") or para.get("package", "")
    rec = {
        "found": True,
        "lcsc": lcsc,
        "title": r.get("title"),
        "description": r.get("description"),
        "manufacturer": para.get("Manufacturer"),
        "mpn": para.get("Manufacturer Part"),
        "package": pkg,
        "jlcpcb_part_class": para.get("JLCPCB Part Class"),
        "jlcpcb_on_sale": r.get("jlcOnSale"),
        "smt": r.get("SMT"),
        "price_usd": lc.get("price"),
        "stock": lc.get("stock"),
        "min_qty": lc.get("min"),
        "lcsc_url": lc.get("url"),
        "datasheet": r.get("datasheet") or para.get("link"),
        "easyeda_symbol_available": bool(r.get("dataStr")),
        "easyeda_footprint_available": bool(r.get("packageDetail")),
        "hint": "easyeda2kicad --full --lcsc_id " + lcsc + " converts the EasyEDA symbol/footprint/3D to KiCad",
    }
    return rec


def search(query: str) -> dict:
    """Keyword search is not available without a browser session; explain the
    fallback so the agent does the right thing instead of guessing."""
    q = query.strip()
    if LCSC_RE.match(q.upper()):
        return lcsc_lookup(q)
    return {
        "found": False,
        "query": q,
        "why": "LCSC/JLCPCB keyword search endpoints reject non-browser clients",
        "do_instead": [
            f'WebSearch: "{q}" LCSC  (the result URL ends in _C<number>.html; that is the LCSC number)',
            f"then: kcs jlc C<number>  for price/stock/basic-vs-extended",
            "or ask the user for the LCSC number from the JLCPCB parts library page",
            f"for non-LCSC sourcing: WebSearch \"{q}\" datasheet, then the manufacturer page for CAD models",
        ],
    }


def lcsc_from_text(text: str) -> list[str]:
    """Extract LCSC numbers (C123456) from arbitrary text such as a URL or page."""
    return sorted(set(m.group(0).upper() for m in re.finditer(r"\bC\d{3,9}\b", text)))
