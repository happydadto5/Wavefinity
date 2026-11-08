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
    def test_a_long_ascii_name_is_rejected_before_anything_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                organizer_app.generate_organizer_files(
                    _box(), _fused(), Path(directory), part_name="a" * 300)
            self.assertEqual(list(Path(directory).iterdir()), [])

class DrawerNameScopeTests(unittest.TestCase):
    def test_a_long_drawer_name_is_untouched(self) -> None:
        # Deliberate scoping: the drawer name never reaches a filename.
        drawer = normalise_drawer(
            {"width": 300.0, "depth": 300.0, "height": 60.0, "name": "d" * 1000})
        self.assertEqual(drawer["name"], "d" * 1000)


if __name__ == "__main__":
    unittest.main()
