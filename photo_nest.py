"""Turn one overhead part photo on US letter paper into a scaled outline."""

from __future__ import annotations

import base64
import binascii
import math
from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient


LETTER_WIDTH_MM = 215.9
LETTER_HEIGHT_MM = 279.4
WARP_PIXELS_PER_MM = 4.0
MAX_IMAGE_PIXELS = 32_000_000
MAX_UPLOAD_BYTES = 18_000_000
ACCEPTED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _cross2(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


@dataclass(frozen=True)
class PhotoOutline:
    contour: tuple[tuple[float, float], ...]
    width: float
    depth: float
    paper_corners: tuple[tuple[float, float], ...]


def decode_image_data(data_url: str, mime_type: str = "") -> np.ndarray:
    """Decode a browser data URL without retaining the uploaded bytes."""
    if not isinstance(data_url, str) or "," not in data_url:
        raise ValueError("choose a JPG, JPEG, PNG, or WEBP photo")
    header, encoded = data_url.split(",", 1)
    declared = header[5:].split(";", 1)[0].lower() if header.startswith("data:") else ""
    chosen = (mime_type or declared).lower()
    if chosen not in ACCEPTED_IMAGE_TYPES or (declared and declared not in ACCEPTED_IMAGE_TYPES):
        raise ValueError("choose a JPG, JPEG, PNG, or WEBP photo")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("the selected photo could not be read") from error
    if not payload or len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("the photo must be smaller than 18 MB")
    
    # Check dimensions before decompressing to avoid OOM bombs
    try:
        from PIL import Image
        import io
        with Image.open(io.BytesIO(payload)) as img:
            if img.width * img.height > MAX_IMAGE_PIXELS:
                raise ValueError("the photo is too large; use an image under 32 megapixels")
    except ValueError:
        raise
    except Exception as error:
        raise ValueError("the selected photo could not be read") from error

    image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("the selected photo could not be read")
    return image


def order_paper_corners(points: Iterable[Iterable[float]]) -> np.ndarray:
    """Return four corners clockwise as top-left, top-right, bottom-right, bottom-left."""
    corners = np.asarray(tuple(points), dtype=np.float32)
    if corners.shape != (4, 2) or not np.isfinite(corners).all():
        raise ValueError("paper detection needs four valid corners")
    centre = corners.mean(axis=0)
    angles = np.arctan2(corners[:, 1] - centre[1], corners[:, 0] - centre[0])
    corners = corners[np.argsort(angles)]
    start = int(np.argmin(corners[:, 0] + corners[:, 1]))
    corners = np.roll(corners, -start, axis=0)
    # atan2 order is TL, TR, BR, BL in image coordinates. Correct a rare
    # counter-clockwise input before checking the perspective.
    cross = _cross2(corners[1] - corners[0], corners[2] - corners[1])
    if cross < 0:
        corners = corners[[0, 3, 2, 1]]
    return corners.astype(np.float32)


def validate_paper_corners(points: Iterable[Iterable[float]]) -> np.ndarray:
    corners = order_paper_corners(points)
    edges = np.array([
        np.linalg.norm(corners[(index + 1) % 4] - corners[index])
        for index in range(4)
    ])
    if edges.min() < 30.0:
        raise ValueError("paper missing: all four letter-paper corners must be visible")
    if edges.max() / edges.min() > 5.0:
        raise ValueError("perspective too severe: hold the camera directly overhead")
    area = abs(float(cv2.contourArea(corners)))
    rect_area = float((corners[:, 0].max() - corners[:, 0].min())
                      * (corners[:, 1].max() - corners[:, 1].min()))
    if rect_area <= 0.0 or area / rect_area < 0.48:
        raise ValueError("perspective too severe: hold the camera directly overhead")
    for index in range(4):
        before = corners[index - 1] - corners[index]
        after = corners[(index + 1) % 4] - corners[index]
        sine = abs(_cross2(before, after)) / (
            float(np.linalg.norm(before) * np.linalg.norm(after)) + 1e-12
        )
        if sine < 0.28:
            raise ValueError("perspective too severe: hold the camera directly overhead")
    return corners


def _quad_candidates(mask: np.ndarray, scale: float) -> list[np.ndarray]:
    contours, _hierarchy = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    minimum = mask.shape[0] * mask.shape[1] * 0.12
    candidates: list[np.ndarray] = []
    for contour in contours:
        area = abs(float(cv2.contourArea(contour)))
        if area < minimum:
            continue
        perimeter = cv2.arcLength(contour, True)
        for fraction in (0.012, 0.018, 0.025, 0.035, 0.05):
            approx = cv2.approxPolyDP(contour, fraction * perimeter, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                candidates.append(approx[:, 0, :].astype(np.float32) / scale)
                break
    return candidates


def detect_paper_corners(image: np.ndarray) -> np.ndarray:
    """Find the largest plausible four-cornered sheet in a photograph."""
    if image is None or image.ndim != 3 or min(image.shape[:2]) < 120:
        raise ValueError("paper missing: use a clear photo showing the entire sheet")
    height, width = image.shape[:2]
    scale = min(1.0, 1800.0 / max(height, width))
    work = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(work, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (7, 7), 0)
    edges = cv2.Canny(blur, 35, 120)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)

    hsv = cv2.cvtColor(work, cv2.COLOR_BGR2HSV)
    bright = cv2.inRange(hsv, np.array((0, 0, 115), np.uint8), np.array((179, 125, 255), np.uint8))
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8), iterations=2)

    candidates = _quad_candidates(edges, scale) + _quad_candidates(bright, scale)
    ranked: list[tuple[float, np.ndarray]] = []
    for candidate in candidates:
        try:
            ordered = validate_paper_corners(candidate)
        except ValueError:
            continue
        if (ordered[:, 0].min() <= 2.0 or ordered[:, 1].min() <= 2.0
                or ordered[:, 0].max() >= width - 3.0
                or ordered[:, 1].max() >= height - 3.0):
            continue
        area = abs(float(cv2.contourArea(ordered)))
        ranked.append((area, ordered))
    if not ranked:
        raise ValueError("paper missing: show all four corners of one 8.5 × 11 in sheet")
    return max(ranked, key=lambda entry: entry[0])[1]


def perspective_transform_inputs(
    points: Iterable[Iterable[float]], pixels_per_mm: float = WARP_PIXELS_PER_MM,
) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    """Validated source/destination points used for the letter-paper homography."""
    source = validate_paper_corners(points)
    horizontal = (np.linalg.norm(source[1] - source[0]) + np.linalg.norm(source[2] - source[3])) / 2.0
    vertical = (np.linalg.norm(source[2] - source[1]) + np.linalg.norm(source[3] - source[0])) / 2.0
    if horizontal > vertical:
        source = source[[1, 2, 3, 0]]
    width = max(2, int(round(LETTER_WIDTH_MM * pixels_per_mm)))
    height = max(2, int(round(LETTER_HEIGHT_MM * pixels_per_mm)))
    destination = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
        dtype=np.float32,
    )
    return source, destination, (width, height)


def correct_perspective(
    image: np.ndarray, points: Iterable[Iterable[float]],
    pixels_per_mm: float = WARP_PIXELS_PER_MM,
) -> np.ndarray:
    source, destination, size = perspective_transform_inputs(points, pixels_per_mm)
    transform = cv2.getPerspectiveTransform(source, destination)
    condition = float(np.linalg.cond(transform))
    if not math.isfinite(condition) or condition > 1e8:
        raise ValueError("perspective too severe: hold the camera directly overhead")
    return cv2.warpPerspective(image, transform, size, flags=cv2.INTER_CUBIC,
                               borderMode=cv2.BORDER_REPLICATE)


def clean_outline_mask(mask: np.ndarray, pixels_per_mm: float) -> np.ndarray:
    """Remove camera specks and smooth sub-millimetre mask stair-steps."""
    binary = (mask > 0).astype(np.uint8) * 255
    small = max(3, int(round(0.65 * pixels_per_mm)) | 1)
    large = max(3, int(round(1.25 * pixels_per_mm)) | 1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((small, small), np.uint8))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((large, large), np.uint8))
    sigma = max(0.6, 0.28 * pixels_per_mm)
    blurred = cv2.GaussianBlur(binary, (0, 0), sigma)
    return (blurred >= 127).astype(np.uint8) * 255


def segment_object(
    rectified: np.ndarray, pixels_per_mm: float = WARP_PIXELS_PER_MM,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the single cleaned foreground component and its outside contour."""
    lab = cv2.cvtColor(rectified, cv2.COLOR_BGR2LAB).astype(np.float32)
    margin = max(4, int(round(5.0 * pixels_per_mm)))
    corner = max(margin + 2, int(round(16.0 * pixels_per_mm)))
    samples = np.concatenate([
        lab[margin:corner, margin:corner].reshape(-1, 3),
        lab[margin:corner, -corner:-margin].reshape(-1, 3),
        lab[-corner:-margin, margin:corner].reshape(-1, 3),
        lab[-corner:-margin, -corner:-margin].reshape(-1, 3),
    ])
    background = np.median(samples, axis=0)
    distance = np.linalg.norm(lab - background, axis=2)
    distance8 = np.clip(distance, 0, 255).astype(np.uint8)
    otsu, _ = cv2.threshold(distance8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    threshold = max(14.0, min(70.0, float(otsu)))
    raw = (distance > threshold).astype(np.uint8) * 255
    raw = clean_outline_mask(raw, pixels_per_mm)

    count, labels, stats, _centres = cv2.connectedComponentsWithStats(raw, 8)
    components = []
    pixel_area = 1.0 / (pixels_per_mm * pixels_per_mm)
    for label in range(1, count):
        area_mm2 = float(stats[label, cv2.CC_STAT_AREA]) * pixel_area
        if area_mm2 >= 20.0:
            components.append((area_mm2, label, stats[label]))
    if not components:
        raise ValueError("outline too small or noisy: use a closer, sharper, high-contrast photo")
    components.sort(reverse=True)
    largest_area = components[0][0]
    meaningful = [entry for entry in components if entry[0] >= max(35.0, largest_area * 0.10)]
    if len(meaningful) != 1:
        raise ValueError("multiple objects found: place exactly one part on the paper")
    _area, label, stat = meaningful[0]
    edge = max(2, int(round(2.5 * pixels_per_mm)))
    x, y, width, height, _pixels = (int(value) for value in stat)
    if x <= edge or y <= edge or x + width >= raw.shape[1] - edge or y + height >= raw.shape[0] - edge:
        raise ValueError("object touching paper edge: leave visible paper around the entire part")

    chosen = (labels == label).astype(np.uint8) * 255
    contours, _hierarchy = cv2.findContours(chosen, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        raise ValueError("outline too small or noisy: use a closer, sharper photo")
    outside = max(contours, key=cv2.contourArea)
    epsilon = max(1.0, 0.35 * pixels_per_mm)
    outside = cv2.approxPolyDP(outside, epsilon, True)
    return chosen, outside[:, 0, :].astype(np.float64)


def contour_to_millimetres(
    pixels: np.ndarray, pixels_per_mm: float = WARP_PIXELS_PER_MM,
) -> tuple[tuple[float, float], ...]:
    coords = np.asarray(pixels, dtype=float) / pixels_per_mm
    if coords.ndim != 2 or coords.shape[1] != 2 or len(coords) < 3:
        raise ValueError("outline too small or noisy: no closed shape was found")
    coords[:, 1] *= -1.0
    polygon = Polygon(coords).buffer(0)
    if polygon.geom_type == "MultiPolygon":
        polygon = max(polygon.geoms, key=lambda one: one.area)
    if not isinstance(polygon, Polygon) or polygon.is_empty:
        raise ValueError("outline too small or noisy: no closed shape was found")
    polygon = orient(polygon.simplify(0.2, preserve_topology=True), sign=1.0)
    min_x, min_y, max_x, max_y = polygon.bounds
    if polygon.area < 25.0 or min(max_x - min_x, max_y - min_y) < 4.0:
        raise ValueError("outline too small or noisy: use a closer, sharper photo")
    centre_x, centre_y = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
    points = tuple(
        (round(float(x - centre_x), 3), round(float(y - centre_y), 3))
        for x, y in list(polygon.exterior.coords)[:-1]
    )
    if len(points) < 3 or len(points) > 500:
        raise ValueError("outline too small or noisy: simplify the background and retake the photo")
    return points


def extract_photo_outline(image: np.ndarray) -> PhotoOutline:
    corners = detect_paper_corners(image)
    rectified = correct_perspective(image, corners)
    _mask, pixels = segment_object(rectified)
    contour = contour_to_millimetres(pixels)
    polygon = Polygon(contour)
    min_x, min_y, max_x, max_y = polygon.bounds
    return PhotoOutline(
        contour,
        round(max_x - min_x, 3),
        round(max_y - min_y, 3),
        tuple((round(float(x), 3), round(float(y), 3)) for x, y in corners),
    )


def photo_outline_from_data(data_url: str, mime_type: str = "") -> PhotoOutline:
    return extract_photo_outline(decode_image_data(data_url, mime_type))
