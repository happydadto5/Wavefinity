import numpy as np, trimesh
from organizer_engine import (
    BoxSpec, ConnectorSpec, make_side_connector, connector_bin_heights,
    installed_side_boxes, seat_transform, translated, validate_side_fit,
    measure_lock, connector_for_print, differing_web_reach,
)

def span(mesh, z):
    k = trimesh.creation.box(extents=(20.0, 0.05, 0.05))
    k.apply_translation((0.0, 0.0, z))
    h = k.intersection(mesh)
    if h.is_empty or h.volume < 1e-9:
        return None
    return float(h.bounds[0][0]), float(h.bounds[1][0])

def worst_overhang(mesh):
    """Shallowest wall angle among downward-facing faces clear of the build
    plate, in degrees from horizontal. 90 = vertical, <45 needs support."""
    m = mesh
    z0 = float(m.bounds[0][2])
    cz = m.triangles_center[:, 2]
    n = m.face_normals
    keep = (n[:, 2] < -1e-6) & (cz > z0 + 0.5) & (m.area_faces > 0.05)
    if not keep.any():
        return 90.0
    tilt = np.degrees(np.arcsin(np.clip(-n[keep][:, 2], 0, 1)))  # 0=vert, 90=flat
    return float(90.0 - tilt.max())

con = ConnectorSpec()
print(f"web inward reach = {differing_web_reach(BoxSpec(40.,40.,50.), con):.4f} mm\n")
print(f"{'pair':>10} {'drop':>5} {'unbrcd':>7} {'guided':>7} {'gap':>7} "
      f"{'seat':>6} {'lock':>7} {'tight':>6} {'wall<':>7}")
for ha, hb in ((50., 20.), (40., 24.), (40., 30.), (60., 20.), (40., 36.),
               (50., 12.), (30., 20.), (50., 50.)):
    box = BoxSpec(40.0, 40.0, max(ha, hb))
    heights = connector_bin_heights(box, ha, hb)
    clip = make_side_connector(box, con, "y", 0.0, 12.0, ha, hb)
    seated = translated(clip, seat_transform(box, con, 0.0, "y", max(heights)))
    tall = installed_side_boxes(box, "y", ha, hb)[0]
    drop = ha - hb
    unbraced = max(0.0, drop - con.arm_depth)
    gaps = []
    if unbraced > 0.4:
        for z in np.linspace(hb + 0.2, ha - con.arm_depth - 0.2, 25):
            try:
                c, w = span(seated, float(z)), span(tall, float(z))
            except Exception:
                continue
            if c and w:
                gaps.append(c[0] - w[1])
    guided = (sum(1 for g in gaps if g < 0.25) / len(gaps) * unbraced) if gaps else 0.0
    seat = validate_side_fit(box, con, clip, "y", 0.0, ha, hb)
    lock = measure_lock(box, con, "y", 0.0, bin_a_height=ha, bin_b_height=hb)["lift_0.5_mm3"]
    g = min(gaps) if gaps else float("nan")
    print(f"{f'{ha:g}/{hb:g}':>10} {drop:5.0f} {unbraced:7.1f} {guided:7.1f} {g:7.3f} "
          f"{seat:6.3f} {lock:7.3f} {str(clip.is_watertight):>6} "
          f"{worst_overhang(connector_for_print(clip)):6.1f}d")
