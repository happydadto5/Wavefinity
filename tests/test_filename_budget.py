"""Fix 1052: the 255-byte generated-filename budget (clean ValueError, not OSError)."""

from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import trimesh

import organizer_app
import organizer_base_trim
from organizer_app_impl._filenames import (
    MAX_FILENAME_BYTES,
    box_filename,
    check_filename_bytes,
)
from organizer_base_trim import BaseTrimSpec, generate_base_trim_files
from organizer_drawer import normalise_drawer
from organizer_engine import B4BSpec, BoxSpec
from organizer_inserts import Layout

EMOJI = "\N{GRINNING FACE}"  # 4 bytes in UTF-8
TIMESTAMP_BYTES = len(" 010125120000")


def _box() -> BoxSpec:
    return BoxSpec(48.0, 48.0, 40.0)


def _fused() -> Layout:
    return Layout((), "fused")


def _name_for_filename_bytes(filename_fn, total: int) -> str:
    """An ASCII part name that makes ``filename_fn(name)`` exactly ``total`` bytes."""
    base = len(filename_fn("").encode("utf-8"))
    # the name adds a separating space plus its own characters
    return "a" * (total - base - 1)


class CheckFilenameBytesTests(unittest.TestCase):
    def test_exactly_the_budget_is_accepted(self) -> None:
        check_filename_bytes("a" * MAX_FILENAME_BYTES)

    def test_one_byte_over_is_rejected_with_a_clear_message(self) -> None:
        with self.assertRaises(ValueError) as caught:
            check_filename_bytes("a" * (MAX_FILENAME_BYTES + 1))
        self.assertEqual(
            str(caught.exception),
            "bin name produces a 256-byte filename; the limit is 255 bytes "
            "including the export prefix/suffix",
        )

    def test_the_budget_is_bytes_not_characters(self) -> None:
        sixty_four = EMOJI * 64  # 64 characters, 256 bytes
        self.assertEqual(len(sixty_four), 64)
        with self.assertRaises(ValueError):
            check_filename_bytes(sixty_four)


class OrdinaryBinExportTests(unittest.TestCase):
    def test_sixty_emoji_name_is_rejected_but_sixty_ascii_exports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError) as caught:
                organizer_app.generate_organizer_files(
                    _box(), _fused(), Path(directory), part_name=EMOJI * 60)
            self.assertIn("255 bytes", str(caught.exception))
            self.assertEqual(list(Path(directory).iterdir()), [])
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_organizer_files(
                _box(), _fused(), Path(directory), part_name="a" * 60)
            self.assertTrue(Path(result["box"]["output"]).is_file())

    def test_a_long_ascii_name_is_rejected_before_anything_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                organizer_app.generate_organizer_files(
                    _box(), _fused(), Path(directory), part_name="a" * 300)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_storage_box_name_is_checked(self) -> None:
        box = BoxSpec(x=64, y=48, z=40, wall=1.2, b4b=B4BSpec(enabled=True))
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError) as caught:
                organizer_app.generate_b4b_files(box, Path(directory), EMOJI * 60)
            self.assertIn("255 bytes", str(caught.exception))
        with tempfile.TemporaryDirectory() as directory:
            result = organizer_app.generate_b4b_files(box, Path(directory), "a" * 60)
            self.assertTrue(Path(result["output"]).is_file())


class TransactionalBoundaryTests(unittest.TestCase):
    """The timestamp branch in _promote_staged_set is its own boundary."""

    def _export(self, directory: str, part_name: str) -> dict:
        box = BoxSpec(48.0, 48.0, 40.0, wall=1.6)  # non-default wall -> longer prefix
        return organizer_app.generate_organizer_files_transactional(
            box, _fused(), Path(directory), part_name=part_name, auto_timestamp=True)

    def _seed_existing(self, directory: str, part_name: str) -> str:
        """Pre-create the colliding file so the promote step adds the timestamp."""
        box = BoxSpec(48.0, 48.0, 40.0, wall=1.6)
        name = box_filename(box, part_name)
        (Path(directory) / name).write_bytes(b"existing")
        return name

    def test_final_name_at_the_budget_after_timestamp_is_accepted(self) -> None:
        box = BoxSpec(48.0, 48.0, 40.0, wall=1.6)
        part_name = _name_for_filename_bytes(
            lambda name: box_filename(box, name), MAX_FILENAME_BYTES - TIMESTAMP_BYTES)
        with tempfile.TemporaryDirectory() as directory:
            existing = self._seed_existing(directory, part_name)
            result = self._export(directory, part_name)
            final = Path(result["box"]["output"])
            self.assertEqual(len(final.name.encode("utf-8")), MAX_FILENAME_BYTES)
            self.assertNotEqual(final.name, existing)
            self.assertTrue(final.is_file())

    def test_one_byte_over_after_timestamp_is_rejected_and_output_untouched(self) -> None:
        box = BoxSpec(48.0, 48.0, 40.0, wall=1.6)
        part_name = _name_for_filename_bytes(
            lambda name: box_filename(box, name), MAX_FILENAME_BYTES - TIMESTAMP_BYTES + 1)
        with tempfile.TemporaryDirectory() as directory:
            self._seed_existing(directory, part_name)
            before = sorted(path.name for path in Path(directory).iterdir())
            with self.assertRaises(ValueError) as caught:
                self._export(directory, part_name)
            self.assertIn("256-byte filename", str(caught.exception))
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), before)

    def test_legacy_long_name_design_loads_but_export_rejects(self) -> None:
        box, layout, label, _part, location, scoop = organizer_app.design_from_dict(
            organizer_app.design_to_dict(_box(), _fused(), "", "x", "bottom", False))
        data = organizer_app.design_to_dict(box, layout, label, "x" * 1000, location, scoop)
        loaded = organizer_app.design_from_dict(data)  # no raise: not a poison pill
        self.assertEqual(loaded[3], "x" * 1000)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "keep.txt").write_text("keep")
            before = sorted(path.name for path in Path(directory).iterdir())
            with self.assertRaises(ValueError):
                organizer_app.generate_organizer_files_transactional(
                    loaded[0], loaded[1], Path(directory), label=loaded[2],
                    part_name=loaded[3], label_location=loaded[4], scoop=loaded[5])
            self.assertEqual(sorted(path.name for path in Path(directory).iterdir()), before)


class BaseTrimBoundaryTests(unittest.TestCase):
    def _generate(self, directory: str, part_name: str, pieces: int) -> dict:
        spec = BaseTrimSpec(field_x=80.0, field_y=80.0)
        made = [
            (SimpleNamespace(index=index, label=f"Part {index}"), trimesh.creation.box((4, 4, 4)))
            for index in range(1, pieces + 1)
        ]
        with mock.patch.object(organizer_base_trim, "make_base_trim_pieces", return_value=made), \
                mock.patch.object(organizer_base_trim, "export_mesh"), \
                mock.patch.object(organizer_base_trim, "mesh_report", return_value={}):
            return generate_base_trim_files(
                spec, Path(directory), part_name, auto_timestamp=True)

    def test_longest_piece_suffix_sets_the_budget(self) -> None:
        spec = BaseTrimSpec(field_x=80.0, field_y=80.0)
        longest = " Part 99 of 99.3mf"
        base = len(organizer_base_trim._base_filename(spec, "").encode("utf-8"))
        fits = "a" * (MAX_FILENAME_BYTES - base - 1 - len(longest))
        with tempfile.TemporaryDirectory() as directory:
            result = self._generate(directory, fits, 99)
            self.assertEqual(len(result["parts"]), 99)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self._generate(directory, fits + "a", 99)

    def test_timestamp_counts_toward_the_budget(self) -> None:
        # Blank name forces the timestamp branch: suffix + 13 bytes on top.
        spec = BaseTrimSpec(field_x=80.0, field_y=80.0)
        base = len(organizer_base_trim._base_filename(spec, "").encode("utf-8"))
        suffix = len(" Part 99 of 99.3mf") + TIMESTAMP_BYTES
        self.assertLess(base + suffix, MAX_FILENAME_BYTES)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(len(self._generate(directory, "", 99)["parts"]), 99)


class DrawerNameScopeTests(unittest.TestCase):
    def test_a_long_drawer_name_is_untouched(self) -> None:
        # Deliberate scoping: the drawer name never reaches a filename.
        drawer = normalise_drawer(
            {"width": 300.0, "depth": 300.0, "height": 60.0, "name": "d" * 1000})
        self.assertEqual(drawer["name"], "d" * 1000)


if __name__ == "__main__":
    unittest.main()
