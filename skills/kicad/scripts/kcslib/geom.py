"""Coordinate helpers shared by the schematic and PCB writers.

Schematic symbol libraries use a Y-up coordinate system; placed schematics
and boards use Y-down. Rotation angles in files are counter-clockwise as
seen on screen.
"""
from __future__ import annotations

import math

GRID = 1.27  # 50 mil schematic grid, mm


def snap(v: float, grid: float = GRID) -> float:
    return round(round(v / grid) * grid, 4)


def snap_pt(pt: tuple[float, float], grid: float = GRID) -> tuple[float, float]:
    return (snap(pt[0], grid), snap(pt[1], grid))


def on_grid(v: float, grid: float = GRID, tol: float = 1e-3) -> bool:
    return abs(v - snap(v, grid)) < tol


def rot_ccw(x: float, y: float, deg: float) -> tuple[float, float]:
    """Rotate a Y-down screen vector counter-clockwise (as seen on screen)."""
    d = deg % 360
    if d == 0:
        return (x, y)
    if d == 90:
        return (y, -x)
    if d == 180:
        return (-x, -y)
    if d == 270:
        return (-y, x)
    r = math.radians(d)
    c, s = math.cos(r), math.sin(r)
    return (x * c + y * s, -x * s + y * c)


def lib_to_sch(px: float, py: float, rot: float = 0, mirror: str | None = None) -> tuple[float, float]:
    """Map a symbol-library point (Y up) to an offset from the placed symbol
    origin in schematic coordinates (Y down), honouring ``(at x y rot)`` and
    ``(mirror x|y)`` exactly as KiCad's symbol transform does.

    Verified against KiCad 10 by generating rotated/mirrored symbols and
    reading back the netlist (see tests in the kicad skill).
    """
    x, y = px, -py
    x, y = rot_ccw(x, y, rot)
    if mirror == "x":      # mirror about the X axis: flips vertically
        y = -y
    elif mirror == "y":    # mirror about the Y axis: flips horizontally
        x = -x
    return (x, y)


def pin_direction(angle: float, rot: float = 0, mirror: str | None = None) -> tuple[float, float]:
    """Unit vector (schematic coords) pointing *away* from the symbol body
    at a pin's connection end, i.e. the direction a stub wire should leave in.

    In the library a pin's ``angle`` is the direction the pin *points into*
    the body from its connection end: 0 = body is to the right of the pin end.
    """
    a = angle % 360
    # direction from connection end toward the body, in lib coords (Y up)
    toward = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[int(a)]
    tx, ty = lib_to_sch(toward[0], toward[1], rot, mirror)
    return (-tx, -ty)


def fmt_mm(v: float) -> str:
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s
