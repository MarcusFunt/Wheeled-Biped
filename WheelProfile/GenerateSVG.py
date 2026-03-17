from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, List, Tuple

Point = Tuple[float, float]
COMPOSITION_MODES = ("separate", "evenodd")


@dataclass(frozen=True, slots=True)
class WheelParameters:
    outer_diameter: float
    hub_diameter: float
    rim_solid_thickness: float
    lattice_inner_diameter: float
    lattice_outer_diameter: float
    boundary_clearance: float
    gap_inner: float
    gap_outer: float
    gap_gradient_exp: float
    compensate_tangential_scale: bool
    preferred_rows: int
    target_hex_side: float
    min_rows: int
    max_rows: int
    preferred_cols_multiple: int
    min_hex_side: float
    min_gap: float
    reference_radius_blend: float
    rotation_deg: float
    svg_margin: float
    stroke_width: float
    draw_outer_and_hub: bool
    draw_lattice_bounds: bool
    composition_mode: str
    use_radial_fill_gradient: bool
    output_basename: str


def default_parameters() -> WheelParameters:
    outer_diameter = 80.0
    hub_diameter = 40.0
    rim_solid_thickness = 2.5
    return WheelParameters(
        outer_diameter=outer_diameter,
        hub_diameter=hub_diameter,
        rim_solid_thickness=rim_solid_thickness,
        lattice_inner_diameter=hub_diameter,
        lattice_outer_diameter=outer_diameter - 2.0 * rim_solid_thickness,
        boundary_clearance=0.5,
        gap_inner=1.2,
        gap_outer=0.8,
        gap_gradient_exp=1.0,
        compensate_tangential_scale=True,
        preferred_rows=2,
        target_hex_side=4.5,
        min_rows=1,
        max_rows=40,
        preferred_cols_multiple=6,
        min_hex_side=2.5,
        min_gap=0.6,
        reference_radius_blend=0.50,
        rotation_deg=0.0,
        svg_margin=5.0,
        stroke_width=0.25,
        draw_outer_and_hub=True,
        draw_lattice_bounds=True,
        composition_mode="separate",
        use_radial_fill_gradient=True,
        output_basename="airless_wheel_hex_graded.svg",
    )


DEFAULT_PARAMETERS = default_parameters()


@dataclass(frozen=True, slots=True)
class ParameterInfo:
    label: str
    hint: str
    detail: str
    constraints: str
    kind: str
    step: float = 0.0
    options: tuple[str, ...] = ()


GUI_PARAMETER_SECTIONS = (
    (
        "Dimensions",
        "Define the envelope of the wheel, where the lattice starts and stops, and how the pattern is rotated.",
        (
            "outer_diameter",
            "hub_diameter",
            "rim_solid_thickness",
            "lattice_inner_diameter",
            "lattice_outer_diameter",
            "boundary_clearance",
            "rotation_deg",
        ),
    ),
    (
        "Gap & Strength",
        "Shape the ligaments between cutouts and control how stiffness changes from the inner band to the outer band.",
        (
            "gap_inner",
            "gap_outer",
            "gap_gradient_exp",
            "compensate_tangential_scale",
            "min_gap",
        ),
    ),
    (
        "Layout Solver",
        "Bias the automatic solver toward your preferred cell count, symmetry, and reference sizing without hard-locking it.",
        (
            "preferred_rows",
            "target_hex_side",
            "min_rows",
            "max_rows",
            "preferred_cols_multiple",
            "min_hex_side",
            "reference_radius_blend",
        ),
    ),
    (
        "Export & Preview",
        "Tune the SVG output style and how much construction geometry shows up in the preview and final export.",
        (
            "svg_margin",
            "stroke_width",
            "draw_outer_and_hub",
            "draw_lattice_bounds",
            "composition_mode",
            "use_radial_fill_gradient",
            "output_basename",
        ),
    ),
)


PARAMETER_INFO = {
    "outer_diameter": ParameterInfo(
        label="Outer diameter (mm)",
        hint="Overall outside size of the wheel blank.",
        detail="This sets the maximum physical envelope of the part and determines the preview scale for the whole design.",
        constraints="Must stay larger than or equal to the lattice outer diameter.",
        kind="float",
        step=1.0,
    ),
    "hub_diameter": ParameterInfo(
        label="Hub diameter (mm)",
        hint="Diameter of the central bore or solid hub region.",
        detail="Use this to reserve space for the axle, hub interface, or any center structure that should remain solid.",
        constraints="Must stay smaller than or equal to the lattice inner diameter.",
        kind="float",
        step=1.0,
    ),
    "rim_solid_thickness": ParameterInfo(
        label="Rim solid thickness (mm)",
        hint="Suggested solid material thickness outside the lattice.",
        detail="This value does not directly solve the lattice, but it is a convenient way to think about how much solid rim you want outside the honeycomb band.",
        constraints="Positive value. A common starting point is outer diameter minus lattice outer diameter divided by two.",
        kind="float",
        step=0.1,
    ),
    "lattice_inner_diameter": ParameterInfo(
        label="Lattice inner diameter (mm)",
        hint="Where the honeycomb band begins near the hub.",
        detail="Increasing this opens a larger solid zone around the center and reduces the available radial working thickness for the lattice.",
        constraints="Must be greater than or equal to hub diameter and less than or equal to lattice outer diameter.",
        kind="float",
        step=0.1,
    ),
    "lattice_outer_diameter": ParameterInfo(
        label="Lattice outer diameter (mm)",
        hint="Where the honeycomb band ends before the solid rim.",
        detail="This is the outer limit for the cutout band. It usually tracks the outer diameter minus twice the solid rim thickness.",
        constraints="Must be greater than or equal to lattice inner diameter and less than or equal to outer diameter.",
        kind="float",
        step=0.1,
    ),
    "boundary_clearance": ParameterInfo(
        label="Boundary clearance (mm)",
        hint="Keeps the cutouts away from the band boundaries.",
        detail="This subtracts material near both lattice boundary circles so cell vertices do not run all the way to the edges.",
        constraints="Must be zero or greater. Increasing it reduces usable lattice thickness.",
        kind="float",
        step=0.1,
    ),
    "gap_inner": ParameterInfo(
        label="Gap inner (mm)",
        hint="Desired minimum gap between neighboring cutouts near the inner band.",
        detail="Larger values leave thicker ligaments near the hub, typically making the inner region stiffer and more conservative.",
        constraints="Positive value. Combined with gap outer and minimum gap during solving.",
        kind="float",
        step=0.1,
    ),
    "gap_outer": ParameterInfo(
        label="Gap outer (mm)",
        hint="Desired minimum gap between neighboring cutouts near the outer band.",
        detail="Use this to taper the ligament thickness outward. Smaller values open the outer cells more aggressively.",
        constraints="Positive value. Combined with gap inner and minimum gap during solving.",
        kind="float",
        step=0.1,
    ),
    "gap_gradient_exp": ParameterInfo(
        label="Gap gradient exponent",
        hint="Controls how quickly the gap changes from inner to outer radius.",
        detail="An exponent of 1.0 is linear. Values above 1 push more of the change toward the outer band, while values below 1 front-load the change near the hub.",
        constraints="Must be greater than zero.",
        kind="float",
        step=0.1,
    ),
    "compensate_tangential_scale": ParameterInfo(
        label="Compensate tangential scale",
        hint="Counteracts circumferential stretching away from the reference radius.",
        detail="Because the flat-strip lattice is wrapped onto an annulus, tangential dimensions naturally scale with radius. This option compensates for that when computing effective gap.",
        constraints="Turn on when you want more uniform physical spacing across the band.",
        kind="bool",
    ),
    "preferred_rows": ParameterInfo(
        label="Preferred rows",
        hint="Soft target for the number of radial lattice rows.",
        detail="The solver still searches within the allowed min and max row count, but it prefers layouts near this value when multiple solutions are valid.",
        constraints="Must be at least 1.",
        kind="int",
        step=1.0,
    ),
    "target_hex_side": ParameterInfo(
        label="Target hex side (mm)",
        hint="Preferred hex side length near the reference radius.",
        detail="The solver tries to land near this size while still satisfying the row count, gap, and symmetry constraints.",
        constraints="Must be positive.",
        kind="float",
        step=0.1,
    ),
    "min_rows": ParameterInfo(
        label="Minimum rows",
        hint="Lower bound for the automatic row search.",
        detail="Use this to stop the solver from collapsing to overly sparse radial packing when a very open lattice would technically fit.",
        constraints="Must be at least 1 and less than or equal to maximum rows.",
        kind="int",
        step=1.0,
    ),
    "max_rows": ParameterInfo(
        label="Maximum rows",
        hint="Upper bound for the automatic row search.",
        detail="Use this to avoid overly dense lattices that may solve mathematically but create manufacturing or strength problems.",
        constraints="Must be greater than or equal to minimum rows.",
        kind="int",
        step=1.0,
    ),
    "preferred_cols_multiple": ParameterInfo(
        label="Preferred columns multiple",
        hint="Soft symmetry preference for the circumferential column count.",
        detail="A value like 6 or 12 nudges the solver toward seam counts and repeated sectors that are easier to inspect and reason about.",
        constraints="Set to 0 to disable the symmetry preference.",
        kind="int",
        step=1.0,
    ),
    "min_hex_side": ParameterInfo(
        label="Minimum hex side (mm)",
        hint="Rejects solutions with cells smaller than this.",
        detail="This acts as a manufacturing and robustness guardrail so the solver does not satisfy the geometry with tiny, impractical cells.",
        constraints="Must be positive.",
        kind="float",
        step=0.1,
    ),
    "min_gap": ParameterInfo(
        label="Minimum gap (mm)",
        hint="Lower clamp for the solver's worst-case ligament spacing.",
        detail="Even if the inner and outer gap targets are smaller, the layout solver will not accept a solution that violates this lower bound.",
        constraints="Must be positive.",
        kind="float",
        step=0.1,
    ),
    "reference_radius_blend": ParameterInfo(
        label="Reference radius blend",
        hint="Chooses where the wrapped flat-strip geometry is most accurate.",
        detail="0.0 anchors the reference at the inner working radius, 0.5 uses the midpoint, and 1.0 anchors it at the outer working radius.",
        constraints="Must stay between 0.0 and 1.0.",
        kind="float",
        step=0.05,
    ),
    "rotation_deg": ParameterInfo(
        label="Rotation (deg)",
        hint="Rotates the lattice around the wheel center.",
        detail="This rotates the entire pattern without changing the solved cell sizes, which is useful for seam placement or aligning with spokes and hardware.",
        constraints="Any numeric value is allowed.",
        kind="float",
        step=1.0,
    ),
    "svg_margin": ParameterInfo(
        label="SVG margin (mm)",
        hint="Extra blank space around the wheel in the exported document.",
        detail="This only affects the output canvas size, making downstream import and laser or CAM nesting easier.",
        constraints="Must be positive.",
        kind="float",
        step=0.5,
    ),
    "stroke_width": ParameterInfo(
        label="Stroke width (mm)",
        hint="Outline thickness for previewed geometry in the SVG.",
        detail="This does not influence the solved lattice geometry. It only changes how the exported outlines are drawn.",
        constraints="Must be positive.",
        kind="float",
        step=0.05,
    ),
    "draw_outer_and_hub": ParameterInfo(
        label="Draw outer and hub",
        hint="Show the outer wheel boundary and hub circle in the SVG.",
        detail="Turn this off when you only want the cutout band geometry and will handle wheel outlines separately in CAD or CAM.",
        constraints="Preview and export stay consistent with this toggle.",
        kind="bool",
    ),
    "draw_lattice_bounds": ParameterInfo(
        label="Draw lattice bounds",
        hint="Show the inner and outer construction circles for the lattice band.",
        detail="These circles are useful when checking band thickness or aligning the pattern, but they are optional in the final SVG.",
        constraints="Preview and export stay consistent with this toggle.",
        kind="bool",
    ),
    "composition_mode": ParameterInfo(
        label="Composition mode",
        hint="Choose between individual cutout paths or a single even-odd fill path.",
        detail="Separate mode is usually cleaner for CAD and CAM imports. Even-odd mode is compact and works well for visual previews and filled exports.",
        constraints="Must be either separate or evenodd.",
        kind="combo",
        options=COMPOSITION_MODES,
    ),
    "use_radial_fill_gradient": ParameterInfo(
        label="Use radial fill gradient",
        hint="Adds a soft radial fill when using even-odd composition.",
        detail="This is a preview-oriented export option. It helps presentation, but it has no effect when the SVG is emitted as separate paths.",
        constraints="Only affects even-odd mode.",
        kind="bool",
    ),
    "output_basename": ParameterInfo(
        label="Output basename",
        hint="Default file name used when exporting without a custom output path.",
        detail="The file is written into the output directory next to the script unless you override the destination from the command line.",
        constraints="Must not be blank. The .svg suffix is added automatically if needed.",
        kind="text",
    ),
}


@dataclass(frozen=True, slots=True)
class Layout:
    rows: int
    cols: int
    side: float
    col_pitch: float
    row_pitch: float
    row_stack_height: float
    radial_margin: float
    strip_width: float


@dataclass(frozen=True, slots=True)
class WheelGeometry:
    params: WheelParameters
    r_outer: float
    r_hub: float
    r_lat_in: float
    r_lat_out: float
    r_work_in: float
    r_work_out: float
    work_thickness: float
    r_ref: float
    circ_ref: float
    start_angle_rad: float
    layout: Layout


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _require_positive(name: str, value: float) -> None:
    if value <= 0.0:
        raise ValueError(f"{name} must be > 0.")


def solve_layout(
    params: WheelParameters,
    r_work_in: float,
    work_thickness: float,
    r_ref: float,
    circ_ref: float,
) -> Layout:
    g_max_phys = max(params.gap_inner, params.gap_outer, params.min_gap)
    if params.compensate_tangential_scale:
        g_max_uv = g_max_phys * (r_ref / max(r_work_in, 1e-9))
    else:
        g_max_uv = g_max_phys

    min_side_from_gap = g_max_uv / math.sqrt(3.0) + 1e-9
    min_side_total = max(params.min_hex_side, min_side_from_gap)

    best_key: Tuple[float, ...] | None = None
    best_layout: Layout | None = None

    for rows in range(int(params.min_rows), int(params.max_rows) + 1):
        height_factor = 2.0 + 1.5 * (rows - 1)
        max_side_radial = work_thickness / height_factor
        if max_side_radial < min_side_total:
            continue

        cols_min = int(math.ceil(circ_ref / (math.sqrt(3.0) * max_side_radial)))
        cols_max = int(math.floor(circ_ref / (math.sqrt(3.0) * min_side_total)))
        cols_min = max(cols_min, 1)
        if cols_min > cols_max:
            continue

        candidate_cols = set()
        cols_target = circ_ref / (math.sqrt(3.0) * max(params.target_hex_side, 1e-9))
        for candidate in (math.floor(cols_target), round(cols_target), math.ceil(cols_target), cols_min, cols_max):
            candidate_cols.add(int(clamp(int(candidate), cols_min, cols_max)))

        if params.preferred_cols_multiple > 1:
            multiple = int(params.preferred_cols_multiple)
            for candidate in list(candidate_cols):
                base = int(round(candidate / multiple)) * multiple
                for delta in (-2, -1, 0, 1, 2):
                    matched = base + delta * multiple
                    if cols_min <= matched <= cols_max:
                        candidate_cols.add(int(matched))

        for cols in sorted(candidate_cols):
            side = circ_ref / (math.sqrt(3.0) * cols)
            if not (min_side_total <= side <= max_side_radial):
                continue

            col_pitch = math.sqrt(3.0) * side
            row_pitch = 1.5 * side
            row_stack_height = 2.0 * side + (rows - 1) * row_pitch
            radial_margin = 0.5 * (work_thickness - row_stack_height)
            if radial_margin < -1e-9:
                continue

            rows_dist = abs(rows - int(params.preferred_rows))
            if params.preferred_cols_multiple > 1:
                multiple = int(params.preferred_cols_multiple)
                mod = cols % multiple
                multiple_penalty = min(mod, multiple - mod) / multiple
            else:
                multiple_penalty = 0.0

            side_err = abs(side - float(params.target_hex_side)) / max(float(params.target_hex_side), 1e-9)
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


def resolve_geometry(params: WheelParameters) -> WheelGeometry:
    for name, value in (
        ("OUTER_DIAMETER", params.outer_diameter),
        ("HUB_DIAMETER", params.hub_diameter),
        ("RIM_SOLID_THICKNESS", params.rim_solid_thickness),
        ("LATTICE_INNER_DIAMETER", params.lattice_inner_diameter),
        ("LATTICE_OUTER_DIAMETER", params.lattice_outer_diameter),
        ("TARGET_HEX_SIDE", params.target_hex_side),
        ("MIN_HEX_SIDE", params.min_hex_side),
        ("MIN_GAP", params.min_gap),
        ("SVG_MARGIN", params.svg_margin),
        ("STROKE_WIDTH", params.stroke_width),
    ):
        _require_positive(name, value)

    if params.boundary_clearance < 0.0:
        raise ValueError("BOUNDARY_CLEARANCE must be >= 0.")
    if params.gap_gradient_exp <= 0.0:
        raise ValueError("GAP_GRADIENT_EXP must be > 0.")
    if params.min_rows < 1:
        raise ValueError("MIN_ROWS must be >= 1.")
    if params.max_rows < params.min_rows:
        raise ValueError("MAX_ROWS must be >= MIN_ROWS.")
    if params.preferred_rows < 1:
        raise ValueError("PREFERRED_ROWS must be >= 1.")
    if params.preferred_cols_multiple < 0:
        raise ValueError("PREFERRED_COLS_MULTIPLE must be >= 0.")
    if not (0.0 <= params.reference_radius_blend <= 1.0):
        raise ValueError("REFERENCE_RADIUS_BLEND must be between 0 and 1.")
    if params.composition_mode not in COMPOSITION_MODES:
        raise ValueError(f"COMPOSITION_MODE must be one of {COMPOSITION_MODES}.")
    if not params.output_basename.strip():
        raise ValueError("OUTPUT_BASENAME must not be blank.")

    r_outer = params.outer_diameter * 0.5
    r_hub = params.hub_diameter * 0.5
    r_lat_in = params.lattice_inner_diameter * 0.5
    r_lat_out = params.lattice_outer_diameter * 0.5

    if not (r_hub <= r_lat_in <= r_lat_out <= r_outer):
        raise ValueError("Expected HUB <= LATTICE_INNER <= LATTICE_OUTER <= OUTER_DIAMETER.")

    r_work_in = r_lat_in + params.boundary_clearance
    r_work_out = r_lat_out - params.boundary_clearance
    work_thickness = r_work_out - r_work_in
    if work_thickness <= 0.0:
        raise ValueError("No usable lattice thickness. Check diameters and BOUNDARY_CLEARANCE.")

    r_ref = r_work_in + params.reference_radius_blend * work_thickness
    circ_ref = 2.0 * math.pi * r_ref
    start_angle_rad = math.radians(params.rotation_deg) - math.pi / 2.0

    return WheelGeometry(
        params=params,
        r_outer=r_outer,
        r_hub=r_hub,
        r_lat_in=r_lat_in,
        r_lat_out=r_lat_out,
        r_work_in=r_work_in,
        r_work_out=r_work_out,
        work_thickness=work_thickness,
        r_ref=r_ref,
        circ_ref=circ_ref,
        start_angle_rad=start_angle_rad,
        layout=solve_layout(params, r_work_in, work_thickness, r_ref, circ_ref),
    )


def polygon_signed_area(poly: List[Point]) -> float:
    area = 0.0
    for index, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(index + 1) % len(poly)]
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
    if inset_dist <= 0.0:
        return poly[:]

    ccw = polygon_signed_area(poly) > 0.0
    offset_lines: List[Tuple[Point, Point]] = []

    for index in range(len(poly)):
        ax, ay = poly[index]
        bx, by = poly[(index + 1) % len(poly)]
        ex = bx - ax
        ey = by - ay
        length = math.hypot(ex, ey)
        if length < 1e-12:
            continue

        if ccw:
            nx, ny = (-ey / length, ex / length)
        else:
            nx, ny = (ey / length, -ex / length)

        offset_lines.append(
            (
                (ax + nx * inset_dist, ay + ny * inset_dist),
                (bx + nx * inset_dist, by + ny * inset_dist),
            )
        )

    if len(offset_lines) < 3:
        return poly[:]

    result: List[Point] = []
    for index in range(len(offset_lines)):
        prev_line = offset_lines[(index - 1) % len(offset_lines)]
        curr_line = offset_lines[index]
        result.append(line_intersection(prev_line[0], prev_line[1], curr_line[0], curr_line[1]))

    return result


def regular_hex_vertices_uv(cu: float, cv: float, side: float) -> List[Point]:
    dx = (math.sqrt(3.0) / 2.0) * side
    dy = 0.5 * side
    return [
        (cu, cv - side),
        (cu + dx, cv - dy),
        (cu + dx, cv + dy),
        (cu, cv + side),
        (cu - dx, cv + dy),
        (cu - dx, cv - dy),
    ]


def uv_to_xy(u: float, v: float, geometry: WheelGeometry) -> Point:
    theta = geometry.start_angle_rad + (u / geometry.layout.strip_width) * 2.0 * math.pi
    r = geometry.r_work_in + v
    return (r * math.cos(theta), r * math.sin(theta))


def gap_physical_at_radius(r: float, geometry: WheelGeometry) -> float:
    params = geometry.params
    t = (r - geometry.r_work_in) / geometry.work_thickness
    t = clamp(t, 0.0, 1.0) ** params.gap_gradient_exp
    return params.gap_inner + (params.gap_outer - params.gap_inner) * t


def gap_uv_for_cell(r_center: float, geometry: WheelGeometry) -> float:
    gap = gap_physical_at_radius(r_center, geometry)
    if geometry.params.compensate_tangential_scale and r_center > 1e-9:
        gap *= geometry.r_ref / r_center
    return gap


def generate_cutout_polygons_xy(geometry: WheelGeometry) -> List[List[Point]]:
    layout = geometry.layout
    v_center_start = layout.radial_margin + layout.side
    polygons: List[List[Point]] = []

    for row in range(layout.rows):
        cv = v_center_start + row * layout.row_pitch
        offset = 0.5 * layout.col_pitch if (row % 2) else 0.0

        for col in range(layout.cols):
            cu = col * layout.col_pitch + offset
            r_center = geometry.r_work_in + cv
            inset_dist = 0.5 * gap_uv_for_cell(r_center, geometry)
            apothem = (math.sqrt(3.0) / 2.0) * layout.side
            inset_dist = min(inset_dist, 0.95 * apothem)

            poly_uv = regular_hex_vertices_uv(cu, cv, layout.side)
            poly_uv_inset = inset_convex_polygon(poly_uv, inset_dist)
            polygons.append([uv_to_xy(u, v, geometry) for (u, v) in poly_uv_inset])

    return polygons


def svg_path_from_polygon(points: List[Point]) -> str:
    if not points:
        return ""
    path = f"M {points[0][0]:.6f},{points[0][1]:.6f} "
    for x, y in points[1:]:
        path += f"L {x:.6f},{y:.6f} "
    return f"{path}Z"


def svg_path_circle(cx: float, cy: float, r: float) -> str:
    return (
        f"M {cx + r:.6f},{cy:.6f} "
        f"A {r:.6f},{r:.6f} 0 1 0 {cx - r:.6f},{cy:.6f} "
        f"A {r:.6f},{r:.6f} 0 1 0 {cx + r:.6f},{cy:.6f} Z"
    )


def build_svg(geometry: WheelGeometry) -> str:
    polygons = generate_cutout_polygons_xy(geometry)
    width = geometry.params.svg_margin * 2.0 + geometry.r_outer * 2.0
    height = width
    shift_x = geometry.r_outer + geometry.params.svg_margin
    shift_y = geometry.r_outer + geometry.params.svg_margin

    parts = ['<?xml version="1.0" encoding="UTF-8"?>']
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.6f}mm" '
        f'height="{height:.6f}mm" viewBox="0 0 {width:.6f} {height:.6f}">'
    )

    if geometry.params.composition_mode == "evenodd" and geometry.params.use_radial_fill_gradient:
        parts.append("<defs>")
        parts.append(
            '<radialGradient id="wheelFill" cx="50%" cy="50%" r="50%">'
            '<stop offset="0%" stop-color="#dddddd"/>'
            '<stop offset="100%" stop-color="#999999"/>'
            "</radialGradient>"
        )
        parts.append("</defs>")

    parts.append(f'<g transform="translate({shift_x:.6f},{height - shift_y:.6f}) scale(1,-1)">')

    if geometry.params.composition_mode == "separate":
        if geometry.params.draw_outer_and_hub:
            parts.append(
                f'<circle cx="0" cy="0" r="{geometry.r_outer:.6f}" stroke="black" '
                f'stroke-width="{geometry.params.stroke_width:.6f}" fill="none" />'
            )
            parts.append(
                f'<circle cx="0" cy="0" r="{geometry.r_hub:.6f}" stroke="black" '
                f'stroke-width="{geometry.params.stroke_width:.6f}" fill="none" />'
            )

        if geometry.params.draw_lattice_bounds:
            parts.append(
                f'<circle cx="0" cy="0" r="{geometry.r_lat_in:.6f}" stroke="#666666" '
                f'stroke-width="{geometry.params.stroke_width:.6f}" fill="none" />'
            )
            parts.append(
                f'<circle cx="0" cy="0" r="{geometry.r_lat_out:.6f}" stroke="#666666" '
                f'stroke-width="{geometry.params.stroke_width:.6f}" fill="none" />'
            )

        for poly in polygons:
            parts.append(
                f'<path d="{svg_path_from_polygon(poly)}" stroke="black" '
                f'stroke-width="{geometry.params.stroke_width:.6f}" fill="none" />'
            )

    elif geometry.params.composition_mode == "evenodd":
        d_parts = [svg_path_circle(0.0, 0.0, geometry.r_outer), svg_path_circle(0.0, 0.0, geometry.r_hub)]
        d_parts.extend(svg_path_from_polygon(poly) for poly in polygons)
        fill = "url(#wheelFill)" if geometry.params.use_radial_fill_gradient else "#cccccc"
        parts.append(
            f'<path d="{" ".join(d_parts)}" fill="{fill}" fill-rule="evenodd" '
            f'stroke="black" stroke-width="{geometry.params.stroke_width:.6f}" />'
        )

    parts.append("</g>")
    parts.append("</svg>")
    return "\n".join(parts)


def normalize_output_basename(name: str) -> str:
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("OUTPUT_BASENAME must not be blank.")
    if not trimmed.lower().endswith(".svg"):
        return f"{trimmed}.svg"
    return trimmed


def default_output_directory() -> Path:
    return Path(__file__).resolve().parent / "output"


def resolve_output_path(output_path: Path | None, basename: str) -> Path:
    if output_path is None:
        return default_output_directory() / normalize_output_basename(basename)
    if output_path.exists() and output_path.is_dir():
        return output_path / normalize_output_basename(basename)
    if output_path.suffix.lower() != ".svg":
        return output_path.with_suffix(".svg")
    return output_path


def write_svg(params: WheelParameters, output_path: Path | None = None) -> tuple[Path, WheelGeometry]:
    geometry = resolve_geometry(params)
    out_path = resolve_output_path(output_path, params.output_basename)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_svg(geometry), encoding="utf-8", newline="\n")
    return out_path, geometry


def format_cli_report(out_path: Path, geometry: WheelGeometry) -> str:
    lines = [f"Wrote SVG to: {out_path}", "", "Geometry (mm):"]
    lines.append(f"  OUTER_DIAMETER         = {geometry.params.outer_diameter:.3f}")
    lines.append(f"  HUB_DIAMETER           = {geometry.params.hub_diameter:.3f}")
    lines.append(f"  LATTICE_INNER_DIAMETER = {geometry.params.lattice_inner_diameter:.3f}")
    lines.append(f"  LATTICE_OUTER_DIAMETER = {geometry.params.lattice_outer_diameter:.3f}")
    lines.append(f"  BOUNDARY_CLEARANCE     = {geometry.params.boundary_clearance:.3f}")
    lines.extend(("", "Solved layout:"))
    lines.append(f"  rows                    = {geometry.layout.rows}")
    lines.append(f"  cols                    = {geometry.layout.cols}")
    lines.append(f"  hex side (ref radius)   = {geometry.layout.side:.3f}")
    lines.append(f"  radial margin           = {geometry.layout.radial_margin:.3f}")
    lines.append(f"  reference radius        = {geometry.r_ref:.3f}")
    lines.append(f"  gap inner/outer         = {geometry.params.gap_inner:.3f} / {geometry.params.gap_outer:.3f}")
    lines.append(f"  compensate tangential   = {geometry.params.compensate_tangential_scale}")
    lines.append(f"  composition mode        = {geometry.params.composition_mode}")
    return "\n".join(lines)


def format_preview_status(geometry: WheelGeometry) -> str:
    return (
        f"rows={geometry.layout.rows}, cols={geometry.layout.cols}, cutouts={geometry.layout.rows * geometry.layout.cols}, "
        f"side={geometry.layout.side:.3f} mm, radial margin={geometry.layout.radial_margin:.3f} mm"
    )


def format_parameter_value(attr: str, value: Any) -> str:
    if attr in {"compensate_tangential_scale", "draw_outer_and_hub", "draw_lattice_bounds", "use_radial_fill_gradient"}:
        return "On" if bool(value) else "Off"
    if attr == "composition_mode":
        return str(value)
    if attr == "output_basename":
        return str(value)
    if attr in {"preferred_rows", "min_rows", "max_rows", "preferred_cols_multiple"}:
        return str(int(value))
    if attr == "rotation_deg":
        return f"{float(value):.3f} deg"
    if attr in {"gap_gradient_exp", "reference_radius_blend"}:
        return f"{float(value):.3f}"
    return f"{float(value):.3f} mm"


def build_parameter_runtime_note(attr: str, params: WheelParameters, geometry: WheelGeometry | None = None) -> str:
    if attr == "outer_diameter":
        return f"Current radius is {params.outer_diameter * 0.5:.3f} mm."
    if attr == "hub_diameter":
        return f"Current hub radius is {params.hub_diameter * 0.5:.3f} mm."
    if attr == "rim_solid_thickness":
        return f"Suggested lattice outer diameter is {params.outer_diameter - 2.0 * params.rim_solid_thickness:.3f} mm."
    if attr == "lattice_inner_diameter":
        return f"Inner band sits {params.lattice_inner_diameter - params.hub_diameter:.3f} mm outside the hub."
    if attr == "lattice_outer_diameter":
        return f"Gap to the outer diameter is {(params.outer_diameter - params.lattice_outer_diameter) * 0.5:.3f} mm per side."
    if attr == "boundary_clearance":
        return f"This removes {2.0 * params.boundary_clearance:.3f} mm from total working thickness."
    if attr == "gap_inner":
        return f"Inner to outer gap delta is {params.gap_outer - params.gap_inner:.3f} mm."
    if attr == "gap_outer":
        return f"Inner to outer gap delta is {params.gap_outer - params.gap_inner:.3f} mm."
    if attr == "gap_gradient_exp":
        if params.gap_gradient_exp > 1.0:
            return "Most of the gap change is pushed toward the outer band."
        if params.gap_gradient_exp < 1.0:
            return "Most of the gap change happens closer to the hub."
        return "The gap change is currently linear through the band."
    if attr == "compensate_tangential_scale":
        return "Enabled keeps physical spacing more uniform around the band." if params.compensate_tangential_scale else "Disabled leaves the wrapped tangential stretch uncompensated."
    if attr == "preferred_rows":
        if geometry is not None:
            return f"The solver currently chose {geometry.layout.rows} rows."
        return f"The solver will search between {params.min_rows} and {params.max_rows} rows."
    if attr == "target_hex_side":
        if geometry is not None:
            return f"The solved reference side is {geometry.layout.side:.3f} mm."
        return "The solver will try to stay near this size at the reference radius."
    if attr == "min_rows":
        return f"The solver search window is {params.min_rows} to {params.max_rows} rows."
    if attr == "max_rows":
        return f"The solver search window is {params.min_rows} to {params.max_rows} rows."
    if attr == "preferred_cols_multiple":
        if params.preferred_cols_multiple <= 0:
            return "Symmetry bias is disabled."
        if geometry is not None:
            return f"The solver currently chose {geometry.layout.cols} columns."
        return "This nudges the circumferential column count toward a clean repeating pattern."
    if attr == "min_hex_side":
        if geometry is not None:
            return f"The current solved side stays {geometry.layout.side - params.min_hex_side:.3f} mm above this floor."
        return "The solver rejects layouts whose cells would shrink below this size."
    if attr == "min_gap":
        return "This is the solver floor even when gap targets request smaller openings."
    if attr == "reference_radius_blend":
        if geometry is not None:
            return f"The current reference radius is {geometry.r_ref:.3f} mm."
        return "0.0 anchors at the inner band, 1.0 at the outer band."
    if attr == "rotation_deg":
        return "Useful for moving the seam or aligning the pattern with external features."
    if attr == "svg_margin":
        return f"Export canvas becomes {params.outer_diameter + 2.0 * params.svg_margin:.3f} mm square."
    if attr == "stroke_width":
        return "Affects drawing only, not the solved lattice geometry."
    if attr == "draw_outer_and_hub":
        return "Outer and hub reference circles are currently visible." if params.draw_outer_and_hub else "Outer and hub reference circles are currently hidden."
    if attr == "draw_lattice_bounds":
        return "Construction circles for the lattice band are currently visible." if params.draw_lattice_bounds else "Construction circles for the lattice band are currently hidden."
    if attr == "composition_mode":
        if params.composition_mode == "evenodd":
            return "Export uses one filled path with holes cut out by even-odd winding."
        return "Export keeps every cutout as its own path for CAD and CAM friendliness."
    if attr == "use_radial_fill_gradient":
        if params.composition_mode != "evenodd":
            return "This setting is dormant until composition mode is switched to evenodd."
        return "Even-odd export will include a presentation-oriented radial fill."
    if attr == "output_basename":
        name = str(params.output_basename).strip() or DEFAULT_PARAMETERS.output_basename
        return f"Default export target is {default_output_directory() / normalize_output_basename(name)}."
    return ""


def build_parameter_status_text(attr: str, params: WheelParameters, geometry: WheelGeometry | None = None) -> str:
    default_text = format_parameter_value(attr, getattr(DEFAULT_PARAMETERS, attr))
    runtime_text = build_parameter_runtime_note(attr, params, geometry)
    parts = [f"Default: {default_text}"]
    if runtime_text:
        parts.append(runtime_text)
    parts.append(f"Rule: {PARAMETER_INFO[attr].constraints}")
    return " | ".join(parts)


def build_parameter_tooltip_text(attr: str, params: WheelParameters, geometry: WheelGeometry | None = None) -> str:
    lines = [
        PARAMETER_INFO[attr].detail,
        f"Current: {format_parameter_value(attr, getattr(params, attr))}",
        f"Default: {format_parameter_value(attr, getattr(DEFAULT_PARAMETERS, attr))}",
        f"Constraint: {PARAMETER_INFO[attr].constraints}",
    ]
    runtime_text = build_parameter_runtime_note(attr, params, geometry)
    if runtime_text:
        lines.append(runtime_text)
    return "\n".join(lines)


def build_summary_cards_text(
    params: WheelParameters,
    geometry: WheelGeometry | None,
    last_export_path: Path | None = None,
    error: str | None = None,
) -> tuple[str, str, str]:
    output_name = str(params.output_basename).strip() or DEFAULT_PARAMETERS.output_basename
    export_target = last_export_path if last_export_path is not None else default_output_directory() / normalize_output_basename(output_name)

    if geometry is None:
        layout_text = "Awaiting valid geometry.\nAdjust the parameters until the solver can produce a legal layout."
        material_text = "Working band unavailable.\nThe wheel envelope and lattice boundaries must define a positive thickness."
    else:
        layout_text = (
            f"{geometry.layout.rows} rows x {geometry.layout.cols} cols\n"
            f"{geometry.layout.rows * geometry.layout.cols} total cutouts\n"
            f"Hex side {geometry.layout.side:.3f} mm at ref radius"
        )
        material_text = (
            f"Working band {geometry.work_thickness:.3f} mm\n"
            f"Reference radius {geometry.r_ref:.3f} mm\n"
            f"Gap {params.gap_inner:.3f} -> {params.gap_outer:.3f} mm"
        )

    export_text = (
        f"Mode {params.composition_mode}\n"
        f"Gradient {'on' if params.use_radial_fill_gradient else 'off'}\n"
        f"{export_target}"
    )
    if error:
        export_text = f"{export_text}\nStatus: {error}"

    return layout_text, material_text, export_text


def find_first_existing_path(candidates: List[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_gui_fonts(dpg: Any) -> dict[str, Any]:
    regular_path = find_first_existing_path([Path(r"C:\Windows\Fonts\segoeui.ttf")])
    bold_path = find_first_existing_path([Path(r"C:\Windows\Fonts\segoeuib.ttf"), Path(r"C:\Windows\Fonts\segoeui.ttf")])
    light_path = find_first_existing_path([Path(r"C:\Windows\Fonts\segoeuil.ttf"), Path(r"C:\Windows\Fonts\segoeui.ttf")])

    if regular_path is None or bold_path is None or light_path is None:
        return {}

    with dpg.font_registry():
        body = dpg.add_font(str(regular_path), 18)
        small = dpg.add_font(str(regular_path), 15)
        section = dpg.add_font(str(bold_path), 20)
        title = dpg.add_font(str(bold_path), 29)
        subtitle = dpg.add_font(str(light_path), 17)

    return {
        "body": body,
        "small": small,
        "section": section,
        "title": title,
        "subtitle": subtitle,
    }


def build_gui_themes(dpg: Any) -> dict[str, Any]:
    with dpg.theme() as app_theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (242, 240, 234, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (252, 251, 247, 255))
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, (255, 253, 249, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border, (214, 209, 201, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (236, 234, 228, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (227, 236, 236, 255))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (214, 231, 231, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Button, (219, 229, 227, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (193, 220, 216, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (165, 201, 196, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Header, (226, 233, 232, 255))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (202, 221, 219, 255))
            dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (182, 210, 206, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Tab, (228, 225, 219, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TabHovered, (206, 221, 219, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TabActive, (184, 209, 205, 255))
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (43, 112, 106, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (38, 46, 48, 255))
            dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (112, 118, 122, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (233, 230, 224, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab, (196, 200, 196, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered, (173, 181, 178, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabActive, (151, 164, 161, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ResizeGrip, (174, 193, 191, 120))
            dpg.add_theme_color(dpg.mvThemeCol_ResizeGripHovered, (146, 184, 179, 180))
            dpg.add_theme_color(dpg.mvThemeCol_ResizeGripActive, (123, 170, 164, 220))
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 18, 18)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 12, 10)
            dpg.add_theme_style(dpg.mvStyleVar_CellPadding, 12, 8)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 12, 10)
            dpg.add_theme_style(dpg.mvStyleVar_ItemInnerSpacing, 10, 8)
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 18)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 16)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 10)
            dpg.add_theme_style(dpg.mvStyleVar_GrabRounding, 10)
            dpg.add_theme_style(dpg.mvStyleVar_ScrollbarRounding, 14)
            dpg.add_theme_style(dpg.mvStyleVar_PopupRounding, 12)
            dpg.add_theme_style(dpg.mvStyleVar_WindowBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_FrameBorderSize, 1)

    with dpg.theme() as card_theme:
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (252, 251, 248, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Border, (219, 214, 205, 255))
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 18)
            dpg.add_theme_style(dpg.mvStyleVar_ChildBorderSize, 1)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 16, 16)

    with dpg.theme() as accent_button_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (61, 129, 122, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (73, 146, 138, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (51, 113, 107, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (245, 248, 247, 255))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 12)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 14, 10)

    with dpg.theme() as secondary_button_theme:
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, (231, 228, 221, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (218, 222, 218, 255))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (204, 214, 211, 255))
            dpg.add_theme_color(dpg.mvThemeCol_Text, (41, 49, 50, 255))
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 12)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 14, 10)

    return {
        "app": app_theme,
        "card": card_theme,
        "accent_button": accent_button_theme,
        "secondary_button": secondary_button_theme,
    }


def render_preview(dpg: Any, drawlist_tag: str, width: int, height: int, geometry: WheelGeometry) -> None:
    dpg.delete_item(drawlist_tag, children_only=True)

    pad = 24.0
    scale = min((width - 2.0 * pad) / (2.0 * geometry.r_outer), (height - 2.0 * pad) / (2.0 * geometry.r_outer))
    center = (width * 0.5, height * 0.5)
    outline_color = (29, 37, 40, 255)
    bound_color = (94, 129, 132, 200)
    background_fill = (247, 245, 240, 255)
    background_border = (221, 216, 208, 255)
    outer_fill = (240, 236, 229, 255)
    band_fill = (201, 223, 223, 165)
    hub_fill = (247, 245, 240, 255)
    cutout_fill = (255, 255, 255, 225)

    def map_point(point: Point) -> Tuple[float, float]:
        x, y = point
        return (center[0] + x * scale, center[1] - y * scale)

    def map_radius(radius: float) -> float:
        return radius * scale

    dpg.draw_rectangle((0, 0), (width, height), color=background_border, fill=background_fill, parent=drawlist_tag)
    dpg.draw_circle(center, map_radius(geometry.r_outer), color=(231, 225, 216, 255), fill=outer_fill, thickness=2.0, parent=drawlist_tag)
    dpg.draw_circle(center, map_radius(geometry.r_lat_out), color=(193, 213, 214, 255), fill=band_fill, thickness=1.0, parent=drawlist_tag)
    dpg.draw_circle(center, map_radius(geometry.r_lat_in), color=background_fill, fill=hub_fill, thickness=0.0, parent=drawlist_tag)
    dpg.draw_circle(center, map_radius(geometry.r_hub), color=(233, 228, 220, 255), fill=hub_fill, thickness=1.0, parent=drawlist_tag)

    if geometry.params.draw_outer_and_hub:
        dpg.draw_circle(center, map_radius(geometry.r_outer), color=outline_color, thickness=2.0, parent=drawlist_tag)
        dpg.draw_circle(center, map_radius(geometry.r_hub), color=outline_color, thickness=2.0, parent=drawlist_tag)

    if geometry.params.draw_lattice_bounds:
        dpg.draw_circle(center, map_radius(geometry.r_lat_in), color=bound_color, thickness=1.0, parent=drawlist_tag)
        dpg.draw_circle(center, map_radius(geometry.r_lat_out), color=bound_color, thickness=1.0, parent=drawlist_tag)

    for poly in generate_cutout_polygons_xy(geometry):
        dpg.draw_polygon([map_point(point) for point in poly], color=outline_color, fill=cutout_fill, thickness=1.0, parent=drawlist_tag)


def launch_gui(initial_params: WheelParameters | None = None) -> None:
    try:
        from dearpygui import dearpygui as dpg
    except ImportError as exc:
        raise RuntimeError("Dear PyGui is not installed. Run 'pip install dearpygui'.") from exc

    params = initial_params or DEFAULT_PARAMETERS
    field_tags = {field: f"wheel_{field}" for field in WheelParameters.__dataclass_fields__}
    parameter_status_tags = {field: f"{field_tags[field]}_status" for field in WheelParameters.__dataclass_fields__}
    tooltip_meta_tags = {field: f"{field_tags[field]}_tooltip_meta" for field in WheelParameters.__dataclass_fields__}
    drawlist_tag = "wheel_preview_drawlist"
    status_tag = "wheel_status_text"
    preview_size = 720
    summary_tags = {
        "layout": "wheel_summary_layout",
        "material": "wheel_summary_material",
        "export": "wheel_summary_export",
    }
    last_export_path: Path | None = None

    dpg.create_context()
    themes = build_gui_themes(dpg)
    fonts = load_gui_fonts(dpg)
    dpg.bind_theme(themes["app"])
    if "body" in fonts:
        dpg.bind_font(fonts["body"])

    def apply_font(item: Any, font_key: str) -> None:
        font = fonts.get(font_key)
        if font is not None:
            dpg.bind_item_font(item, font)

    def set_status(message: str) -> None:
        dpg.set_value(status_tag, message)

    def update_parameter_info(current_params: WheelParameters, geometry: WheelGeometry | None = None) -> None:
        for attr in WheelParameters.__dataclass_fields__:
            status_text = build_parameter_status_text(attr, current_params, geometry)
            tooltip_text = build_parameter_tooltip_text(attr, current_params, geometry)
            dpg.set_value(parameter_status_tags[attr], status_text)
            dpg.set_value(tooltip_meta_tags[attr], tooltip_text)

    def update_summary_cards(current_params: WheelParameters, geometry: WheelGeometry | None, error: str | None = None) -> None:
        layout_text, material_text, export_text = build_summary_cards_text(current_params, geometry, last_export_path, error)
        dpg.set_value(summary_tags["layout"], layout_text)
        dpg.set_value(summary_tags["material"], material_text)
        dpg.set_value(summary_tags["export"], export_text)

    def collect_parameters() -> WheelParameters:
        return WheelParameters(
            outer_diameter=float(dpg.get_value(field_tags["outer_diameter"])),
            hub_diameter=float(dpg.get_value(field_tags["hub_diameter"])),
            rim_solid_thickness=float(dpg.get_value(field_tags["rim_solid_thickness"])),
            lattice_inner_diameter=float(dpg.get_value(field_tags["lattice_inner_diameter"])),
            lattice_outer_diameter=float(dpg.get_value(field_tags["lattice_outer_diameter"])),
            boundary_clearance=float(dpg.get_value(field_tags["boundary_clearance"])),
            gap_inner=float(dpg.get_value(field_tags["gap_inner"])),
            gap_outer=float(dpg.get_value(field_tags["gap_outer"])),
            gap_gradient_exp=float(dpg.get_value(field_tags["gap_gradient_exp"])),
            compensate_tangential_scale=bool(dpg.get_value(field_tags["compensate_tangential_scale"])),
            preferred_rows=int(dpg.get_value(field_tags["preferred_rows"])),
            target_hex_side=float(dpg.get_value(field_tags["target_hex_side"])),
            min_rows=int(dpg.get_value(field_tags["min_rows"])),
            max_rows=int(dpg.get_value(field_tags["max_rows"])),
            preferred_cols_multiple=int(dpg.get_value(field_tags["preferred_cols_multiple"])),
            min_hex_side=float(dpg.get_value(field_tags["min_hex_side"])),
            min_gap=float(dpg.get_value(field_tags["min_gap"])),
            reference_radius_blend=float(dpg.get_value(field_tags["reference_radius_blend"])),
            rotation_deg=float(dpg.get_value(field_tags["rotation_deg"])),
            svg_margin=float(dpg.get_value(field_tags["svg_margin"])),
            stroke_width=float(dpg.get_value(field_tags["stroke_width"])),
            draw_outer_and_hub=bool(dpg.get_value(field_tags["draw_outer_and_hub"])),
            draw_lattice_bounds=bool(dpg.get_value(field_tags["draw_lattice_bounds"])),
            composition_mode=str(dpg.get_value(field_tags["composition_mode"])),
            use_radial_fill_gradient=bool(dpg.get_value(field_tags["use_radial_fill_gradient"])),
            output_basename=str(dpg.get_value(field_tags["output_basename"])).strip() or DEFAULT_PARAMETERS.output_basename,
        )

    def add_parameter_control(attr: str) -> None:
        info = PARAMETER_INFO[attr]

        with dpg.group():
            label_tag = dpg.add_text(info.label, color=(33, 42, 45, 255))
            hint_tag = dpg.add_text(info.hint, wrap=430, color=(101, 108, 111, 255))
            apply_font(hint_tag, "small")

            if info.kind == "float":
                control = dpg.add_input_double(
                    tag=field_tags[attr],
                    default_value=float(getattr(params, attr)),
                    format="%.3f",
                    step=info.step or 0.1,
                    width=-1,
                    callback=refresh_preview,
                )
            elif info.kind == "int":
                control = dpg.add_input_int(
                    tag=field_tags[attr],
                    default_value=int(getattr(params, attr)),
                    step=int(info.step or 1),
                    width=-1,
                    callback=refresh_preview,
                )
            elif info.kind == "bool":
                control = dpg.add_checkbox(
                    tag=field_tags[attr],
                    default_value=bool(getattr(params, attr)),
                    callback=refresh_preview,
                )
            elif info.kind == "combo":
                control = dpg.add_combo(
                    tag=field_tags[attr],
                    default_value=str(getattr(params, attr)),
                    items=list(info.options),
                    width=-1,
                    callback=refresh_preview,
                )
            elif info.kind == "text":
                control = dpg.add_input_text(
                    tag=field_tags[attr],
                    default_value=str(getattr(params, attr)),
                    width=-1,
                    callback=refresh_preview,
                    on_enter=True,
                )
            else:
                raise ValueError(f"Unsupported parameter kind: {info.kind}")

            meta_tag = dpg.add_text("", tag=parameter_status_tags[attr], wrap=430, color=(88, 97, 100, 255))
            apply_font(label_tag, "body")
            apply_font(meta_tag, "small")

            with dpg.tooltip(control):
                tooltip_title = dpg.add_text(info.label, color=(31, 40, 43, 255))
                apply_font(tooltip_title, "section")
                tooltip_detail = dpg.add_text(info.detail, wrap=340, color=(69, 77, 80, 255))
                apply_font(tooltip_detail, "small")
                dpg.add_spacer(height=4)
                tooltip_meta = dpg.add_text("", tag=tooltip_meta_tags[attr], wrap=340, color=(89, 98, 101, 255))
                apply_font(tooltip_meta, "small")

            dpg.add_spacer(height=8)

    def refresh_preview(sender: Any = None, app_data: Any = None, user_data: Any = None) -> None:
        del sender, app_data, user_data
        current_params = collect_parameters()
        error: str | None = None
        geometry: WheelGeometry | None = None

        try:
            geometry = resolve_geometry(current_params)
        except Exception as exc:
            error = str(exc)
            dpg.delete_item(drawlist_tag, children_only=True)
            set_status(f"Invalid parameters | {error}")
        else:
            render_preview(dpg, drawlist_tag, preview_size, preview_size, geometry)
            set_status(f"Preview ready | {format_preview_status(geometry)}")

        update_parameter_info(current_params, geometry)
        update_summary_cards(current_params, geometry, error)

    def export_svg(sender: Any = None, app_data: Any = None, user_data: Any = None) -> None:
        del sender, app_data, user_data
        nonlocal last_export_path

        current_params = collect_parameters()
        try:
            out_path, geometry = write_svg(current_params)
        except Exception as exc:
            update_parameter_info(current_params, None)
            update_summary_cards(current_params, None, str(exc))
            set_status(f"Export failed | {exc}")
            return

        last_export_path = out_path
        render_preview(dpg, drawlist_tag, preview_size, preview_size, geometry)
        update_parameter_info(current_params, geometry)
        update_summary_cards(current_params, geometry)
        set_status(f"Exported {out_path} | {format_preview_status(geometry)}")

    def reset_defaults(sender: Any = None, app_data: Any = None, user_data: Any = None) -> None:
        del sender, app_data, user_data
        nonlocal last_export_path

        last_export_path = None
        defaults = default_parameters()
        for attr in field_tags:
            dpg.set_value(field_tags[attr], getattr(defaults, attr))
        refresh_preview()

    def build_section_tab(title: str, subtitle: str, attrs: tuple[str, ...]) -> None:
        with dpg.tab(label=title):
            section_title = dpg.add_text(title, color=(34, 43, 46, 255))
            section_subtitle = dpg.add_text(subtitle, wrap=430, color=(98, 105, 109, 255))
            apply_font(section_title, "section")
            apply_font(section_subtitle, "small")
            dpg.add_spacer(height=8)
            for attr in attrs:
                add_parameter_control(attr)

    with dpg.window(label="Wheel Generator", tag="wheel_generator_window", no_title_bar=True):
        title_tag = dpg.add_text("Wheel Generator", color=(31, 40, 43, 255))
        subtitle_tag = dpg.add_text(
            "Interactive airless wheel lattice studio with live solver feedback, tuned for quick geometry iteration and SVG export.",
            wrap=1280,
            color=(94, 102, 105, 255),
        )
        apply_font(title_tag, "title")
        apply_font(subtitle_tag, "subtitle")
        dpg.add_spacer(height=10)

        with dpg.group(horizontal=True):
            with dpg.child_window(width=500, border=False) as sidebar_card:
                panel_title = dpg.add_text("Parameter Studio", color=(34, 43, 45, 255))
                panel_subtitle = dpg.add_text(
                    "Each control shows a live rule summary below it and a deeper explanation when you hover the field.",
                    wrap=440,
                    color=(96, 104, 108, 255),
                )
                apply_font(panel_title, "section")
                apply_font(panel_subtitle, "small")
                dpg.add_spacer(height=8)
                with dpg.tab_bar():
                    for title, subtitle, attrs in GUI_PARAMETER_SECTIONS:
                        build_section_tab(title, subtitle, attrs)
            dpg.bind_item_theme(sidebar_card, themes["card"])

            with dpg.child_window(border=False, autosize_x=True, autosize_y=True):
                with dpg.group(horizontal=True):
                    preview_button = dpg.add_button(label="Refresh Preview", callback=refresh_preview, width=150)
                    export_button = dpg.add_button(label="Export SVG", callback=export_svg, width=140)
                    reset_button = dpg.add_button(label="Reset Defaults", callback=reset_defaults, width=150)
                dpg.bind_item_theme(preview_button, themes["secondary_button"])
                dpg.bind_item_theme(export_button, themes["accent_button"])
                dpg.bind_item_theme(reset_button, themes["secondary_button"])

                dpg.add_spacer(height=10)
                with dpg.table(header_row=False, policy=dpg.mvTable_SizingStretchProp, borders_innerV=False, borders_outerV=False, borders_innerH=False, borders_outerH=False):
                    dpg.add_table_column()
                    dpg.add_table_column()
                    dpg.add_table_column()
                    with dpg.table_row():
                        for card_title, tag in (
                            ("Solved Layout", summary_tags["layout"]),
                            ("Material Band", summary_tags["material"]),
                            ("Export", summary_tags["export"]),
                        ):
                            with dpg.table_cell():
                                with dpg.child_window(height=140, border=False) as summary_card:
                                    summary_title = dpg.add_text(card_title, color=(35, 44, 46, 255))
                                    summary_body = dpg.add_text("", tag=tag, wrap=210, color=(85, 94, 97, 255))
                                    apply_font(summary_title, "section")
                                    apply_font(summary_body, "small")
                                dpg.bind_item_theme(summary_card, themes["card"])

                dpg.add_spacer(height=10)
                with dpg.child_window(border=False, autosize_x=True, autosize_y=True) as preview_card:
                    preview_title = dpg.add_text("Preview", color=(34, 43, 45, 255))
                    preview_subtitle = dpg.add_text(
                        "Live annulus view of the current lattice, including optional construction circles and export styling cues.",
                        wrap=preview_size,
                        color=(96, 104, 108, 255),
                    )
                    apply_font(preview_title, "section")
                    apply_font(preview_subtitle, "small")
                    dpg.add_spacer(height=8)
                    dpg.add_drawlist(width=preview_size, height=preview_size, tag=drawlist_tag)
                    status_text = dpg.add_text("", tag=status_tag, wrap=preview_size, color=(84, 93, 96, 255))
                    apply_font(status_text, "small")
                dpg.bind_item_theme(preview_card, themes["card"])

    dpg.create_viewport(title="Wheel Generator", width=1460, height=940)
    dpg.set_viewport_clear_color((242, 240, 234, 255))
    dpg.setup_dearpygui()
    dpg.set_primary_window("wheel_generator_window", True)
    refresh_preview()
    dpg.show_viewport()
    dpg.start_dearpygui()
    dpg.destroy_context()


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate an airless wheel SVG or launch the Dear PyGui editor.")
    parser.add_argument("--gui", action="store_true", help="Launch the Dear PyGui editor.")
    parser.add_argument("--output", type=Path, help="Write the SVG to a specific file path.")
    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> None:
    args = parse_args(argv)
    params = default_parameters()

    if args.gui:
        launch_gui(params)
        return

    out_path, geometry = write_svg(params, args.output)
    print(format_cli_report(out_path, geometry))


if __name__ == "__main__":
    main()
