# 1. Preserve Bare Atom Tokens on S-Expression Round-Trip
Date: 2026-10-14
Status: Accepted

KiCad 9/10 schematic and board files distinguish between unquoted symbol atoms (e.g. yes, hide, 0.254) and quoted strings. All S-expression readers and writers in kcslib.sexpr must represent bare tokens with the Atom str-subclass and emit computed floats through fmt_mm() / num() without trailing zeros or '-0'.
