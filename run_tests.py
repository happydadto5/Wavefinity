#!/usr/bin/env python3
"""Run the whole Wavefinity test suite with compact, token-cheap output.

Default (everything passes): one summary line.
Any failure: the failing test IDs and their tracebacks - nothing else. No
per-test dots, no passing-test names, and no app access-log noise (several
tests spin up a real WavefinityServer, which prints one line per request).

Usage:
    python3 run_tests.py                 # whole suite (test_*.py)
    python3 run_tests.py test_b4b         # one module
    python3 run_tests.py test_b4b test_stack

Exit code is 0 iff everything passed.
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import sys
import time
import unittest


def main(argv: list[str]) -> int:
    loader = unittest.TestLoader()
    if argv:
        suite = loader.loadTestsFromNames(argv)
    else:
        # Only root-level test modules are active. Historical browser tests live
        # under retired-tests/ and must never enter normal discovery.
        suite = unittest.TestSuite(
            loader.loadTestsFromName(path.stem)
            for path in sorted(Path(__file__).resolve().parent.glob("test_*.py"))
        )

    # verbosity=0 already skips the per-test dots; redirecting stdout/stderr
    # during the run also swallows the app's own request-log prints, which
    # verbosity has no control over.
    runner = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0)
    start = time.time()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        result = runner.run(suite)
    elapsed = time.time() - start

    total = result.testsRun
    failed = len(result.failures)
    errored = len(result.errors)
    skipped = len(result.skipped)
    passed = total - failed - errored - skipped

    if not failed and not errored:
        skip_note = f", {skipped} skipped" if skipped else ""
        print(f"PASS: {passed}/{total} passed{skip_note} in {elapsed:.1f}s")
        return 0

    print(f"FAIL: {passed} passed, {failed} failed, {errored} errored, "
          f"{skipped} skipped, {total} total in {elapsed:.1f}s\n")
    for label, items in (("FAILURE", result.failures), ("ERROR", result.errors)):
        for test, trace in items:
            print(f"--- {label}: {test} ---")
            print(trace.strip())
            print()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
