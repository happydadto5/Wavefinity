"""Local Photo Nest routes using the canonical image and geometry code."""
from photo_nest import photo_outline_from_data
from wavefinity_web_impl._nest import nest_retrace_payload, photo_nest_payload
from .editor_routes import entry_route


def nest_trace_payload(payload):
    corners_raw = payload.get("paper_corners")
    corners = ([[float(v) for v in point] for point in corners_raw]
               if isinstance(corners_raw, list) and len(corners_raw) == 4 else None)
    outline = photo_outline_from_data(
        str(payload.get("image", "")), str(payload.get("mime_type", "")),
        str(payload.get("paper_size", "letter")),
        float(payload.get("sensitivity", 50.0)), float(payload.get("cleanup", 50.0)),
        corners,
    )
    result = {
        "contour": [list(point) for point in outline.contour],
        "outline": {"width": outline.width, "depth": outline.depth},
        "trace_center_mm": list(outline.trace_center_mm) if outline.trace_center_mm else None,
    }
    if outline.reference_image and outline.reference_bounds:
        result["reference"] = {"image": outline.reference_image, "bounds": list(outline.reference_bounds)}
    if outline.rectified_image:
        result["rectified_image"] = outline.rectified_image
    return result


ROUTES = {
    "/api/nest/trace": nest_trace_payload,
    "/api/nest/photo": entry_route(photo_nest_payload),
    "/api/nest/retrace": nest_retrace_payload,
}
