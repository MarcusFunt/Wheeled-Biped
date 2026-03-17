from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
from typing import List, Tuple, Optional

Point = Tuple[float, float]

# ============================================================
# Airless wheel lattice generator -> SVG
#
# Core idea:
#   1) Build a regular hex lattice in a flat strip (u, v),
#      where u is arc-length on a chosen REFERENCE circle.
#   2) Map (u, v) onto an annulus (x, y) using theta = u / R_ref.
#
# Consequence:
#   Cells are "most regular" near the reference radius.
#   At other radii, geometry is stretched tangentially by r / R_ref.
#
# Gradient support:
#   Vary the cutout inset (effective strut/ligament thickness)
#   as a function of radius.
# ============================================================

# ----------------------------
# USER PARAMETERS (mm)
# ----------------------------

# Overall wheel outer diameter and hub diameter (matches your screenshot)
OUTER_DIAMETER = 80.0
HUB_DIAMETER = 40.0

# Solid rim thickness (radial), so the lattice OD defaults to OD - 2*rim_thickness
RIM_SOLID_THICKNESS = 2.5

# Lattice boundary diameters (defaults match your screenshot: Ø40 to Ø75)
LATTICE_INNER_DIAMETER = HUB_DIAMETER
LATTICE_OUTER_DIAMETER = OUTER_DIAMETER - 2.0 * RIM_SOLID_THICKNESS  # 75 mm

# Extra clearance between lattice boundary circles and the cutouts (radial, mm)
BOUNDARY_CLEARANCE = 0.5

# Gap/ligament control (mm): gradient of desired minimum gap between neighbouring cutouts
GAP_INNER = 1.2   # near inner lattice boundary
GAP_OUTER = 0.8   # near outer lattice boundary
GAP_GRADIENT_EXP = 1.0  # 1=linear, >1 shifts change toward outer boundary

# If True, scale UV inset approximately to counteract tangential stretch (r/Rref)
COMPENSATE_TANGENTIAL_SCALE = True

# Layout solver preferences
PREFERRED_ROWS = 2
TARGET_HEX_SIDE = 4.5  # "true" near the reference radius
MIN_ROWS = 1
MAX_ROWS = 40

# Symmetry preference: prefer column counts divisible by this number (6, 8, 12, 24…)
PREFERRED_COLS_MULTIPLE = 6

# Manufacturing guardrails (mm)
MIN_HEX_SIDE = 2.5     # reject solutions that produce tiny hexes
MIN_GAP = 0.6          # reject solutions that produce tiny ligaments after clamping

# Where tangential sizing is exact:
# 0.0 = inner working radius, 0.5 = mid, 1.0 = outer working radius
REFERENCE_RADIUS_BLEND = 0.50

# Rotate the entire lattice
ROTATION_DEG = 0.0

# SVG output controls
SVG_MARGIN = 5.0
STROKE_WIDTH = 0.25

DRAW_OUTER_AND_HUB = True
DRAW_LATTICE_BOUNDS = True

# Composition:
# - "separate": each cutout is an individual path (best for CAD/CAM)
# - "evenodd": one combined filled path using fill-rule="evenodd" (best for preview + gradients)
COMPOSITION_MODE = "separate"  # "separate" or "evenodd"

# Gradient fill used only in "evenodd" mode
USE_RADIAL_FILL_GRADIENT = True

OUTPUT_BASENAME = "airless_wheel_hex_graded.svg"


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ----------------------------
# DERIVED GEOMETRY
# ----------------------------

R_OUTER = OUTER_DIAMETER * 0.5
R_HUB = HUB_DIAMETER * 0.5
R_LAT_IN = LATTICE_INNER_DIAMETER * 0.5
R_LAT_OUT = LATTICE_OUTER_DIAMETER * 0.5

if not (R_HUB <= R_LAT_IN <= R_LAT_OUT <= R_OUTER):
    raise ValueError("Expected HUB <= LATTICE_INNER <= LATTICE_OUTER <= OUTER_DIAMETER/2")

# Working region where cutout vertices must remain
R_WORK_IN = R_LAT_IN + BOUNDARY_CLEARANCE
R_WORK_OUT = R_LAT_OUT - BOUNDARY_CLEARANCE
WORK_THICKNESS = R_WORK_OUT - R_WORK_IN
if WORK_THICKNESS <= 0:
    raise ValueError("No usable lattice thickness (check diameters and BOUNDARY_CLEARANCE).")

R_REF = R_WORK_IN + REFERENCE_RADIUS_BLEND * WORK_THICKNESS
CIRC_REF = 2.0 * math.pi * R_REF
START_ANGLE_RAD = math.radians(ROTATION_DEG) - math.pi / 2.0  # seam at top after Y-flip


# ----------------------------
# HONEYCOMB GEOMETRY HELPERS
# ----------------------------

def polygon_signed_area(poly: List[Point]) -> float:
    area = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return 0.5 * area


def line_intersection(p1: Point, p2: Point, p3: Point, p4: Point) -> Point:
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4

    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-12:
        return ((x2 + x3) * 0.5, (y2 + y3) * 0.5)

    px = ((x1 * y2 - y1 * x2) * (x3 - x4) - (x1 - x2) * (x3 * y4 - y3 * x4)) / den
    py = ((x1 * y2 - y1 * x2) * (y3 - y4) - (y1 - y2) * (x3 * y4 - y3 * x4)) / den
    return (px, py)


def inset_convex_polygon(poly: List[Point], inset_dist: float) -> List[Point]:
    # Inset a convex polygon by offsetting each edge inward by inset_dist
    # and intersecting adjacent offset lines.
    if inset_dist <= 0:
        return poly[:]

    n = len(poly)
    ccw = polygon_signed_area(poly) > 0.0

    offset_lines: List[Tuple[Point, Point]] = []
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        ex = bx - ax
        ey = by - ay
        elen = math.hypot(ex, ey)
        if elen < 1e-12:
            continue

        # For CCW polygons, inward is the left normal (-ey, ex)
        if ccw:
            nx, ny = (-ey / elen, ex / elen)
        else:
            nx, ny = (ey / elen, -ex / elen)

        p1 = (ax + nx * inset_dist, ay + ny * inset_dist)
        p2 = (bx + nx * inset_dist, by + ny * inset_dist)
        offset_lines.append((p1, p2))

    if len(offset_lines) < 3:
        return poly[:]

    result: List[Point] = []
    m = len(offset_lines)
    for i in range(m):
        prev_line = offset_lines[(i - 1) % m]
        curr_line = offset_lines[i]
        result.append(line_intersection(prev_line[0], prev_line[1], curr_line[0], curr_line[1]))

    return result


def regular_hex_vertices_uv(cu: float, cv: float, side: float) -> List[Point]:
    # Pointy-top regular hex centred at (cu, cv) in flat strip coordinates.
    # Vertex order is CCW.
    dx = (math.sqrt(3.0) / 2.0) * side
    dy = 0.5 * side
    return [
        (cu,      cv - side),
        (cu + dx, cv - dy),
        (cu + dx, cv + dy),
        (cu,      cv + side),
        (cu - dx, cv + dy),
        (cu - dx, cv - dy),
    ]


def uv_to_xy(u: float, v: float, strip_width: float) -> Point:
    theta = START_ANGLE_RAD + (u / strip_width) * 2.0 * math.pi
    r = R_WORK_IN + v
    return (r * math.cos(theta), r * math.sin(theta))


# ----------------------------
# GAP GRADIENT
# ----------------------------

def gap_physical_at_radius(r: float) -> float:
    # Desired gap in mm as a function of radius (physical space).
    t = (r - R_WORK_IN) / WORK_THICKNESS
    t = clamp(t, 0.0, 1.0)
    t = t ** GAP_GRADIENT_EXP
    return GAP_INNER + (GAP_OUTER - GAP_INNER) * t


def gap_uv_for_cell(r_center: float) -> float:
    # Convert physical 'desired gap' into a UV inset distance control.
    # If compensating tangential stretch, scale UV gap by R_REF/r.
    g = gap_physical_at_radius(r_center)
    if COMPENSATE_TANGENTIAL_SCALE and r_center > 1e-9:
        g *= (R_REF / r_center)
    return g


# ----------------------------
# AUTO SOLVER
# ----------------------------

@dataclass(frozen=True)
class Layout:
    rows: int
    cols: int
    side: float
    col_pitch: float
    row_pitch: float
    row_stack_height: float
    radial_margin: float
    strip_width: float


def solve_layout() -> Layout:
    # Conservative worst-case gap across radius (UV units)
    g_max_phys = max(GAP_INNER, GAP_OUTER, MIN_GAP)
    if COMPENSATE_TANGENTIAL_SCALE:
        g_max_uv = g_max_phys * (R_REF / max(R_WORK_IN, 1e-9))
    else:
        g_max_uv = g_max_phys

    min_side_from_gap = g_max_uv / math.sqrt(3.0) + 1e-9
    min_side_total = max(MIN_HEX_SIDE, min_side_from_gap)

    best_key: Optional[Tuple[float, ...]] = None
    best_layout: Optional[Layout] = None

    for rows in range(int(MIN_ROWS), int(MAX_ROWS) + 1):
        height_factor = 2.0 + 1.5 * (rows - 1)
        max_side_radial = WORK_THICKNESS / height_factor
        if max_side_radial < min_side_total:
            continue

        cols_min = int(math.ceil(CIRC_REF / (math.sqrt(3.0) * max_side_radial)))
        cols_max = int(math.floor(CIRC_REF / (math.sqrt(3.0) * min_side_total)))
        cols_min = max(cols_min, 1)
        if cols_min > cols_max:
            continue

        candidate_cols = set()
        cols_target = CIRC_REF / (math.sqrt(3.0) * TARGET_HEX_SIDE)
        for c in (math.floor(cols_target), round(cols_target), math.ceil(cols_target), cols_min, cols_max):
            candidate_cols.add(int(clamp(int(c), cols_min, cols_max)))

        if PREFERRED_COLS_MULTIPLE and PREFERRED_COLS_MULTIPLE > 1:
            m = int(PREFERRED_COLS_MULTIPLE)
            for c in list(candidate_cols):
                base = int(round(c / m)) * m
                for k in (-2, -1, 0, 1, 2):
                    cm = base + k * m
                    if cols_min <= cm <= cols_max:
                        candidate_cols.add(int(cm))

        for cols in sorted(candidate_cols):
            side = CIRC_REF / (math.sqrt(3.0) * cols)
            if not (min_side_total <= side <= max_side_radial):
                continue

            col_pitch = math.sqrt(3.0) * side
            row_pitch = 1.5 * side
            row_stack_height = 2.0 * side + (rows - 1) * row_pitch
            radial_margin = 0.5 * (WORK_THICKNESS - row_stack_height)
            if radial_margin < -1e-9:
                continue

            # ----- Reworked solver priorities -----
            rows_dist = abs(rows - int(PREFERRED_ROWS)) if PREFERRED_ROWS is not None else 0

            if PREFERRED_COLS_MULTIPLE and PREFERRED_COLS_MULTIPLE > 1:
                m = int(PREFERRED_COLS_MULTIPLE)
                mod = cols % m
                multiple_penalty = min(mod, m - mod) / m
            else:
                multiple_penalty = 0.0

            side_err = abs(side - float(TARGET_HEX_SIDE)) / float(TARGET_HEX_SIDE)

            key = (rows_dist, multiple_penalty, side_err, -radial_margin, rows * cols)

            if best_key is None or key < best_key:
                best_key = key
                best_layout = Layout(
                    rows=rows,
                    cols=cols,
                    side=side,
                    col_pitch=col_pitch,
                    row_pitch=row_pitch,
                    row_stack_height=row_stack_height,
                    radial_margin=radial_margin,
                    strip_width=cols * col_pitch,
                )

    if best_layout is None:
        raise RuntimeError("No valid layout found. Loosen constraints or increase WORK_THICKNESS.")
    return best_layout


LAYOUT = solve_layout()


# ----------------------------
# GEOMETRY GENERATION
# ----------------------------

def generate_cutout_polygons_xy() -> List[List[Point]]:
    rows = LAYOUT.rows
    cols = LAYOUT.cols
    side = LAYOUT.side
    col_pitch = LAYOUT.col_pitch
    row_pitch = LAYOUT.row_pitch
    strip_width = LAYOUT.strip_width

    v_center_start = LAYOUT.radial_margin + side
    polygons: List[List[Point]] = []

    for row in range(rows):
        cv = v_center_start + row * row_pitch
        offset = 0.5 * col_pitch if (row % 2) else 0.0

        for col in range(cols):
            cu = col * col_pitch + offset

            r_center = R_WORK_IN + cv
            gap_uv = gap_uv_for_cell(r_center)
            inset_dist = 0.5 * gap_uv

            apothem = (math.sqrt(3.0) / 2.0) * side
            inset_dist = min(inset_dist, 0.95 * apothem)

            poly_uv = regular_hex_vertices_uv(cu, cv, side)
            poly_uv_inset = inset_convex_polygon(poly_uv, inset_dist)
            poly_xy = [uv_to_xy(u, v, strip_width) for (u, v) in poly_uv_inset]
            polygons.append(poly_xy)

    return polygons


# ----------------------------
# SVG HELPERS
# ----------------------------

def svg_path_from_polygon(points: List[Point]) -> str:
    if not points:
        return ""
    d = f"M {points[0][0]:.6f},{points[0][1]:.6f} "
    for x, y in points[1:]:
        d += f"L {x:.6f},{y:.6f} "
    d += "Z"
    return d


def svg_path_circle(cx: float, cy: float, r: float) -> str:
    # Full circle as two arcs
    return (
        f"M {cx + r:.6f},{cy:.6f} "
        f"A {r:.6f},{r:.6f} 0 1 0 {cx - r:.6f},{cy:.6f} "
        f"A {r:.6f},{r:.6f} 0 1 0 {cx + r:.6f},{cy:.6f} Z"
    )


def build_svg() -> str:
    polygons = generate_cutout_polygons_xy()

    # Outer circle bounds everything by definition.
    min_x, min_y, max_x, max_y = (-R_OUTER, -R_OUTER, R_OUTER, R_OUTER)

    width = (max_x - min_x) + 2.0 * SVG_MARGIN
    height = (max_y - min_y) + 2.0 * SVG_MARGIN

    # Shift into positive SVG space; also flip Y so math coords show upright.
    shift_x = -min_x + SVG_MARGIN
    shift_y = -min_y + SVG_MARGIN

    parts: List[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width:.6f}mm" height="{height:.6f}mm" '
        f'viewBox="0 0 {width:.6f} {height:.6f}">'
    )

    if COMPOSITION_MODE == "evenodd" and USE_RADIAL_FILL_GRADIENT:
        parts.append("<defs>")
        parts.append(
            '<radialGradient id="wheelFill" cx="50%" cy="50%" r="50%">'
            '<stop offset="0%" stop-color="#dddddd"/>'
            '<stop offset="100%" stop-color="#999999"/>'
            "</radialGradient>"
        )
        parts.append("</defs>")

    parts.append(f'<g transform="translate({shift_x:.6f},{height - shift_y:.6f}) scale(1,-1)">')

    if COMPOSITION_MODE == "separate":
        if DRAW_OUTER_AND_HUB:
            parts.append(
                f'<circle cx="0" cy="0" r="{R_OUTER:.6f}" stroke="black" '
                f'stroke-width="{STROKE_WIDTH:.6f}" fill="none" />'
            )
            parts.append(
                f'<circle cx="0" cy="0" r="{R_HUB:.6f}" stroke="black" '
                f'stroke-width="{STROKE_WIDTH:.6f}" fill="none" />'
            )

        if DRAW_LATTICE_BOUNDS:
            parts.append(
                f'<circle cx="0" cy="0" r="{R_LAT_IN:.6f}" stroke="#666666" '
                f'stroke-width="{STROKE_WIDTH:.6f}" fill="none" />'
            )
            parts.append(
                f'<circle cx="0" cy="0" r="{R_LAT_OUT:.6f}" stroke="#666666" '
                f'stroke-width="{STROKE_WIDTH:.6f}" fill="none" />'
            )

        for poly in polygons:
            parts.append(
                f'<path d="{svg_path_from_polygon(poly)}" stroke="black" '
                f'stroke-width="{STROKE_WIDTH:.6f}" fill="none" />'
            )

    elif COMPOSITION_MODE == "evenodd":
        d_parts: List[str] = []
        d_parts.append(svg_path_circle(0.0, 0.0, R_OUTER))
        d_parts.append(svg_path_circle(0.0, 0.0, R_HUB))
        for poly in polygons:
            d_parts.append(svg_path_from_polygon(poly))

        fill = 'url(#wheelFill)' if USE_RADIAL_FILL_GRADIENT else "#cccccc"
        parts.append(
            f'<path d="{" ".join(d_parts)}" fill="{fill}" fill-rule="evenodd" '
            f'stroke="black" stroke-width="{STROKE_WIDTH:.6f}" />'
        )

    else:
        raise ValueError("COMPOSITION_MODE must be 'separate' or 'evenodd'.")

    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)


# ----------------------------
# OUTPUT
# ----------------------------

def main() -> None:
    out_dir = Path(__file__).resolve().parent / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / OUTPUT_BASENAME
    out_path.write_text(build_svg(), encoding="utf-8", newline="\n")

    print(f"Wrote SVG to: {out_path}")
    print()
    print("Geometry (mm):")
    print(f"  OUTER_DIAMETER         = {OUTER_DIAMETER:.3f}")
    print(f"  HUB_DIAMETER           = {HUB_DIAMETER:.3f}")
    print(f"  LATTICE_INNER_DIAMETER = {LATTICE_INNER_DIAMETER:.3f}")
    print(f"  LATTICE_OUTER_DIAMETER = {LATTICE_OUTER_DIAMETER:.3f}")
    print(f"  BOUNDARY_CLEARANCE     = {BOUNDARY_CLEARANCE:.3f}")
    print()
    print("Solved layout:")
    print(f"  rows                   = {LAYOUT.rows}")
    print(f"  cols                   = {LAYOUT.cols}")
    print(f"  hex side (ref radius)   = {LAYOUT.side:.3f}")
    print(f"  radial margin           = {LAYOUT.radial_margin:.3f}")
    print(f"  reference radius        = {R_REF:.3f}")
    print(f"  gap inner/outer         = {GAP_INNER:.3f} / {GAP_OUTER:.3f}")
    print(f"  compensate tangential   = {COMPENSATE_TANGENTIAL_SCALE}")
    print(f"  composition mode        = {COMPOSITION_MODE}")


if __name__ == "__main__":
    main()
