# 3. Y-Up Symbol Library to Y-Down Placed Schematic Coordinate Transform
Date: 2026-10-16
Status: Accepted

KiCad symbol libraries define pin offsets in a Y-up Cartesian frame whereas placed schematic instances use a Y-down screen coordinate system. lib_to_sch() must invert Y before applying counter-clockwise screen rotation and axis mirroring.
