#!/usr/bin/env python3
"""Run the whole Wavefinity test suite with compact, token-cheap output.

Tests are broken into 4 chunks for fast troubleshooting. Run one command,
walk away, and check which chunk needs attention.

Usage:
    python3 run_tests.py                 # all 4 chunks (22 modules)
    python3 run_tests.py part1           # fast core tests
    python3 run_tests.py part2           # geometry/insert tests
    python3 run_tests.py part3           # organizer app tests
    python3 run_tests.py part4           # web/space tests
    python3 run_tests.py part1 part3     # multiple chunks
    python3 run_tests.py test_drawer     # single module (backward compat)
    python3 run_tests.py core            # original 8-module core gate

Each module runs in its own subprocess — one module's crash or import
error never kills the rest. After every module, test-status.md is rewritten
with per-module results and full tracebacks for failures.

Exit code is 0 iff everything passed.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

# Chunk definitions: module names in each part
PARTS = {
    "part1": [  # fast core — fundamental safety and geometry
        "test_b4b",
        "test_inventory_safety",
        "test_edge_conflicts",
        "test_ui_state_safety",
        "test_lid_geometry",
        "test_bambu_handoff",
        "test_space_identity",
        "test_standard_walls",
        "test_stack",
    ],
    "part2": [  # geometry/inserts — 3D mesh generation
        "test_organizer_inserts",
        "test_text_geometry",
        "test_pegboard",
        "test_photo_nest",
    ],
    "part3": [  # organizer app — drawer, bins, logging
        "test_organizer_app",
        "test_drawer",
        "test_bin_logging",
    ],
    "part4": [  # web/spaces — UI and space modules
        "test_wavefinity_web",
        "test_space_outputs",
        "test_space_preferences",
        "test_space_simplification",
        "test_space_storage",
        "test_storage_box_inside_bin",
    ],
}

# Original core gate (backward compat)
CORE = [
    "test_inventory_safety", "test_edge_conflicts", "test_ui_state_safety",
    "test_lid_geometry", "test_bambu_handoff", "test_space_identity",
    "test_standard_walls", "test_stack",
]

STATUS_FILE = Path(__file__).resolve().parent / "test-status.md"


def run_module(module: str) -> tuple[str, str]:
    """Run one test module in a subprocess. Returns (status, output)."""
    cmd = [sys.executable, "-m", "unittest", module, "-v"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=Path(__file__).resolve().parent,
        )
        output = result.stdout + result.stderr
        # Parse: look for OK or FAILED in output
        if result.returncode == 0 and "OK" in output:
            return "PASS", output
        else:
            return "FAIL", output
    except subprocess.TimeoutExpired:
        return "TIMEOUT", f"Module {module} timed out after 600s"
    except Exception as e:
        return "ERROR", f"Failed to run {module}: {e}"


def update_status(results: dict[str, tuple[str, str]]):
    """Rewrite test-status.md with current results."""
    lines = ["# Test Status", "", f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    passed = sum(1 for s, _ in results.values() if s == "PASS")
    total = len(results)
    lines.append(f"**{passed}/{total} modules passing**")
    lines.append("")
    for module, (status, output) in sorted(results.items()):
        icon = "✅" if status == "PASS" else "❌"
        lines.append(f"## {icon} {module}: {status}")
        if status != "PASS":
            lines.append("```")
            # Last 50 lines of output (the traceback)
            for line in output.strip().split("\n")[-50:]:
                lines.append(line)
            lines.append("```")
        lines.append("")
    STATUS_FILE.write_text("\n".join(lines))


def main(argv: list[str]) -> int:
    # Resolve which modules to run
    if not argv:
        # All parts
        modules = [m for part in ["part1", "part2", "part3", "part4"] for m in PARTS[part]]
        label = "all 4 parts"
    elif argv == ["core"]:
        modules = CORE
        label = "core gate"
    else:
        modules = []
        label_parts = []
        for arg in argv:
            if arg in PARTS:
                modules.extend(PARTS[arg])
                label_parts.append(arg)
            else:
                # Single module name (backward compat)
                modules.append(arg)
                label_parts.append(arg)
        label = ", ".join(label_parts)

    print(f"Running {label}: {len(modules)} modules")
    print(f"Status file: {STATUS_FILE}")
    print()

    results: dict[str, tuple[str, str]] = {}
    start = time.time()

    for i, module in enumerate(modules, 1):
        print(f"[{i}/{len(modules)}] {module}...", flush=True)
        status, output = run_module(module)
        results[module] = (status, output)
        icon = "✅" if status == "PASS" else "❌"
        print(f"  {icon} {status}")
        update_status(results)

    elapsed = time.time() - start
    passed = sum(1 for s, _ in results.values() if s == "PASS")
    failed = [m for m, (s, _) in results.items() if s != "PASS"]

    print()
    print(f"Done in {elapsed:.1f}s: {passed}/{len(modules)} passed")
    if failed:
        print(f"Failed modules: {', '.join(failed)}")
        print(f"Re-run with: python3 run_tests.py {' '.join(failed)}")
        print(f"Full details: {STATUS_FILE}")
        return 1
    else:
        print("All green!")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
