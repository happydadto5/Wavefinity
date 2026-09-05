import base64
import unittest

import cv2
import numpy as np

from photo_nest import (
    LETTER_HEIGHT_MM,
    LETTER_WIDTH_MM,
    WARP_PIXELS_PER_MM,
    clean_outline_mask,
    correct_perspective,
    decode_image_data,
    detect_paper_corners,
    extract_photo_outline,
    perspective_transform_inputs,
    photo_outline_from_data,
    segment_object,
    validate_paper_corners,
)


def letter_image(objects=((55, 95, 135, 115),), pixels_per_mm=WARP_PIXELS_PER_MM):
    width = round(LETTER_WIDTH_MM * pixels_per_mm)
    height = round(LETTER_HEIGHT_MM * pixels_per_mm)
    image = np.full((height, width, 3), 248, np.uint8)
    for x0, y0, x1, y1 in objects:
        cv2.rectangle(
            image,
            (round(x0 * pixels_per_mm), round(y0 * pixels_per_mm)),
            (round(x1 * pixels_per_mm), round(y1 * pixels_per_mm)),
            (25, 35, 45),
            -1,
        )
    return image


def photographed_letter():
    source = letter_image()
    canvas = np.full((1500, 1300, 3), 45, np.uint8)
    src = np.float32([
        [0, 0], [source.shape[1] - 1, 0],
        [source.shape[1] - 1, source.shape[0] - 1], [0, source.shape[0] - 1],
    ])
    dst = np.float32([[220, 110], [1080, 190], [1010, 1360], [130, 1280]])
    transform = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(source, transform, (canvas.shape[1], canvas.shape[0]))
    paper_mask = cv2.warpPerspective(
        np.full(source.shape[:2], 255, np.uint8), transform,
        (canvas.shape[1], canvas.shape[0]),
    )
    canvas[paper_mask > 0] = warped[paper_mask > 0]
    return canvas, dst


class LetterScaleTests(unittest.TestCase):
    def test_transform_inputs_make_true_letter_dimensions(self):
        corners = np.float32([[20, 15], [450, 30], [430, 590], [5, 570]])
        source, destination, size = perspective_transform_inputs(corners, 2.0)
        self.assertEqual(size, (round(LETTER_WIDTH_MM * 2), round(LETTER_HEIGHT_MM * 2)))
        transform = cv2.getPerspectiveTransform(source, destination)
        mapped = cv2.perspectiveTransform(source[None, :, :], transform)[0]
        np.testing.assert_allclose(mapped, destination, atol=0.02)

    def test_perspective_correction_recovers_letter_rectangle(self):
        photo, corners = photographed_letter()
        corrected = correct_perspective(photo, corners)
        self.assertEqual(corrected.shape[1], round(LETTER_WIDTH_MM * WARP_PIXELS_PER_MM))
        self.assertEqual(corrected.shape[0], round(LETTER_HEIGHT_MM * WARP_PIXELS_PER_MM))

    def test_full_pipeline_recovers_known_part_size(self):
        photo, _corners = photographed_letter()
        outline = extract_photo_outline(photo)
        self.assertAlmostEqual(outline.width, 80.0, delta=1.0)
        self.assertAlmostEqual(outline.depth, 20.0, delta=1.0)
        self.assertGreaterEqual(len(outline.contour), 4)

    def test_jpg_png_and_webp_data_urls_are_accepted(self):
        photo, _corners = photographed_letter()
        for extension, mime in ((".jpg", "image/jpeg"), (".png", "image/png"), (".webp", "image/webp")):
            with self.subTest(extension=extension):
                ok, encoded = cv2.imencode(extension, photo)
                self.assertTrue(ok)
                data = f"data:{mime};base64," + base64.b64encode(encoded).decode("ascii")
                outline = photo_outline_from_data(data, mime)
                self.assertAlmostEqual(outline.width, 80.0, delta=1.0)


class OutlineCleanupAndRejectionTests(unittest.TestCase):
    def test_cleanup_removes_tiny_noise_but_keeps_shape(self):
        mask = np.zeros((400, 400), np.uint8)
        cv2.rectangle(mask, (80, 120), (320, 280), 255, -1)
        mask[10, 10] = 255
        mask[390, 200] = 255
        cleaned = clean_outline_mask(mask, 4.0)
        self.assertEqual(int(cleaned[10, 10]), 0)
        self.assertEqual(int(cleaned[200, 200]), 255)

    def test_missing_paper_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "paper missing"):
            detect_paper_corners(np.full((600, 800, 3), 127, np.uint8))

    def test_severe_perspective_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "perspective too severe"):
            validate_paper_corners([[0, 0], [600, 0], [330, 100], [270, 100]])

    def test_multiple_objects_are_rejected(self):
        image = letter_image(((30, 60, 80, 90), (130, 180, 180, 220)))
        with self.assertRaisesRegex(ValueError, "multiple objects"):
            segment_object(image)

    def test_object_touching_edge_is_rejected(self):
        image = letter_image(((0, 60, 45, 100),))
        with self.assertRaisesRegex(ValueError, "touching paper edge"):
            segment_object(image)

    def test_tiny_outline_is_rejected(self):
        image = letter_image(((100, 130, 101, 131),))
        with self.assertRaisesRegex(ValueError, "too small or noisy"):
            segment_object(image)

    def test_unsupported_upload_type_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "JPG, JPEG, PNG, or WEBP"):
            decode_image_data("data:image/gif;base64,R0lGODlhAQABAIAAAAUEBA==", "image/gif")


if __name__ == "__main__":
    unittest.main()
