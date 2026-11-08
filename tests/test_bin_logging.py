import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from organizer_engine import BoxSpec
from organizer_inserts import Feature, Item, Layout, Segment, Zone
from organizer_app import (
    generate_organizer_files,
    log_bin_to_folder,
    summarize_interior_parts,
)
from organizer_inventory import COLUMNS
import wavefinity_web


class TestBinLogging(unittest.TestCase):


    def test_generation_logging_respects_request_and_folder_policy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            design_folder = Path(tmpdir) / "Designs"
            design_folder.mkdir()
            design = wavefinity_web.default_design()
            with (
                patch.object(wavefinity_web, "HOSTED", False),
                patch.object(wavefinity_web, "load_preferences", return_value={}),
                patch.object(wavefinity_web, "generate_organizer_files_transactional", return_value={}) as generate,
            ):
                # The caller decides whether this generation writes a row.
                wavefinity_web.generate_payload({"design": design, "output": str(design_folder)})
                self.assertFalse(generate.call_args.kwargs["keep_log"])
                wavefinity_web.generate_payload({
                    "design": design, "output": str(design_folder), "keep_log": True,
                })
                self.assertTrue(generate.call_args.kwargs["keep_log"])

                # An explicit opt-out in the folder's own metadata disables it.
                (design_folder / ".wavefinity.json").write_text(
                    '{"version":2,"folder_mode":"design","inventory":false}',
                    encoding="utf-8",
                )
                wavefinity_web.generate_payload({
                    "design": design, "output": str(design_folder), "keep_log": True,
                })
                self.assertFalse(generate.call_args.kwargs["keep_log"])

                # Space inventory is available, but a current row must not be
                # duplicated when its Generate request suppresses logging.
                (design_folder / ".wavefinity.json").write_text(
                    '{"version":2,"folder_mode":"space","inventory":true,'
                    '"space":{"name":"Tools","kind":"drawer","x":100,"y":80,"z":40}}',
                    encoding="utf-8",
                )
                wavefinity_web.generate_payload({
                    "design": design, "output": str(design_folder), "keep_log": False,
                })
                self.assertFalse(generate.call_args.kwargs["keep_log"])



if __name__ == "__main__":
    unittest.main()
