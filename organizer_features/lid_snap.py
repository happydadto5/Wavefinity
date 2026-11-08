"""Optional lid fingers mating with the existing connector detents."""
from organizer_engine._specs import LOCK_PROTRUSION, LOCK_NOTCH_CLEARANCE
from organizer_engine._wave import _wall_lock_paths, _lock_profile, lock_z_levels
from organizer_geometry import _sweep_profile, _extrude_polygon, difference, intersection, union

SNAP_FLOOR_GAP = 0.5 - LOCK_NOTCH_CLEARANCE
SNAP_MIN_DEPTH = -lock_z_levels(0.0)[0] + LOCK_NOTCH_CLEARANCE + SNAP_FLOOR_GAP


def snap_status(box):
    if box.lid.flip_enabled:
        return 'Snap fit needs a lid that does not flip.'
    if box.z - box.base_thickness < SNAP_MIN_DEPTH:
        return 'This bin is too shallow for snap fingers.'
    return ''


def snap_fingers(box):
    if not box.lid.snap_enabled or snap_status(box):
        return []
    from organizer_engine._boxes import flat_cavity_polygon
    from organizer_engine import wavy_cavity_polygon
    from organizer_features.stack import STACK_SKIRT_DEPTH
    bottom = lock_z_levels(0.0)[0] - LOCK_NOTCH_CLEARANCE
    near = LOCK_PROTRUSION - LOCK_NOTCH_CLEARANCE
    far = near + 0.8
    profile = [(near, bottom), (far, bottom), (far, -STACK_SKIRT_DEPTH + 0.2), (near, -STACK_SKIRT_DEPTH + 0.2)]
    # Clip against the real cavity, including any flat interior band. The
    # connector bump paths stay where the connector system placed them.
    low = box.z + bottom
    wavy = _extrude_polygon(wavy_cavity_polygon(box), -bottom + 0.3)
    wavy.apply_translation((0, 0, low))
    cavity = wavy
    band_top = box.base_thickness + box.flat_inside
    if box.flat_inside > 0 and band_top > low:
        band = _extrude_polygon(flat_cavity_polygon(box), band_top - low)
        band.apply_translation((0, 0, low))
        upper = _extrude_polygon(wavy_cavity_polygon(box), box.z - band_top + 0.3)
        upper.apply_translation((0, 0, band_top))
        cavity = union([band, upper])
    fingers = []
    for path, inward in _wall_lock_paths(box):
        notch = _sweep_profile(path, inward, _lock_profile(LOCK_PROTRUSION, LOCK_NOTCH_CLEARANCE))
        notch.apply_translation((0, 0, box.z))
        # A fully buried bump cannot retain a finger.
        bump = _sweep_profile(path, inward, _lock_profile(LOCK_PROTRUSION))
        bump.apply_translation((0, 0, box.z))
        exposed = intersection([bump, cavity])
        if not len(exposed.faces) or abs(exposed.volume) < 1e-8:
            continue
        tab = _sweep_profile(path, inward, profile)
        tab.apply_translation((0, 0, box.z))
        finger = difference([intersection([tab, cavity]), notch])
        if len(finger.faces):
            fingers.append(finger)
    return fingers
