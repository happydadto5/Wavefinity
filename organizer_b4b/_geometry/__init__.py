"""Storage Box (B4B) geometry builders: body, lid, hinge, latch and handle meshes."""

from __future__ import annotations

# Names this module used to re-export from sibling modules (kept for compatibility).
from organizer_engine import (
    CORNER_INSET,
    LOCK_EMBED,
    LOCK_SAFE_SKIN,
    LIFT_GRABBER_RIM_CLEARANCE,
    WAVE_AMPLITUDE,
    BoxSpec,
    _lift_grabber_bulge_mesh,
    _place_lift_grabber,
)
from organizer_geometry import (
    _extrude_polygon,
    _extrude_xz_profile,
    _extrude_yz_profile,
    difference,
    intersection as _intersection,
    union,
)
from .._constants import (
    B4B_STACK_RECESS_DEPTH,
    B4B_STACK_BOSS_DIAMETER,
    B4B_STACK_FEMALE_RADIAL_CLEARANCE,
    B4B_STACK_SOCKET_DEPTH,
    B4B_STACK_SOCKET_INTERFERENCE,
    B4B_STACK_INSET_FRACTION,
    B4B_STACK_INSET_MIN,
    B4B_LID_SKIRT_WALL,
    B4B_LID_SEAT_CLEARANCE,
    B4B_LID_SKIRT_LAP,
    B4B_LID_SKIRT_MIN_LAP,
    B4B_SUPPORT_FREE_FLAT,
    B4B_RUNNING_GAP,
    B4B_HEAD_RECESS_DEPTH,
    HardwareProfile,
    B4B_HW_RELIEF_CLEARANCE,
    B4B_LID_ROOT_BITE,
    B4B_LID_ROOT_REACH,
    B4B_LID_FITTING_DROP,
    B4B_HW_FILLET,
    B4B_STACK_BOSS_CHAMFER,
    B4B_HANDLE_EYE_OVERLAP,
    B4B_HANDLE_STOP_FACE,
    B4B_HANDLE_DETENT_RAMP,
    B4B_HANDLE_EDGE_CHAMFER,
    B4B_HANDLE_EDGE_STEPS,
)
from .._layout import (
    B4BLayout,
    b4b_layout,
    b4b_lid_skin_from_eff,
    b4b_effective_box,
    b4b_lid_underside_z_from_eff,
    b4b_lid_underside_z,
    b4b_rim_z_from_eff,
)
from .._plans import (
    B4BHardwarePlan,
    _ear_wall_anchor_y,
    b4b_hardware_plan,
    B4BHandlePlan,
    b4b_handle_plan,
)

import math
import numpy as np
import trimesh
from shapely.geometry import Point, Polygon
from shapely.affinity import translate as translate_polygon

from ._cutters import (
    support_free_profile_yz,
    _round_bore,
    _weld,
    _filleted,
    _cavity_prism,
    _lid_root_profile,
    _handle_fork_positions,
    _stack_positions,
    _root_profile_yz,
    _root_taper_prism,
    _relief_cutter,
    _pivot_section,
    _head_recess_cutter,
    _ear_solid,
    _gusset,
)
from ._handle import (
    _softened_slab,
    _handle_centreline,
    b4b_handle_outline,
    make_b4b_handle,
    _handle_stop_heel,
    _handle_body_parts,
    _lid_rear_relief_cutter,
    _sweep_intersection_cc,
)
from ._hinges import (
    _hinge_body_parts,
    _hinge_lid_parts,
    _latch_body_parts,
    _latch_lid_parts,
    b4b_latch_lever_profile,
    make_b4b_latches,
)
from ._body import (
    _stack_locator_centres,
    _stack_recesses,
    _B4B_GRABBER_WALL_PAIRS,
    _b4b_wall_face_table,
    validate_b4b_lift_grabbers,
    validate_b4b_side_openings,
    make_b4b_lift_grabbers,
    make_b4b_body,
    _skirt_polygons,
    _skirt_lap,
    make_b4b_lid,
    _chamfered_boss,
    _stack_lid_sockets,
    _stack_pegs,
)
