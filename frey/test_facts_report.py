#!/usr/bin/env python3
"""Tests of facts_report.py (T-0116 ①): a price moved by more than 30 % is listed (either way, and one that
appeared or went away), one moved by less is not; removed and new models; a table that does not fit the
schema makes the exit code 1. `python3 frey/test_facts_report.py` (jsonschema optional)."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import facts_report  # noqa: E402


def table(prices):
    """A facts table: preset `deepseek`, one model per entry of `prices` (input, output)."""
    return {
        "format": 1,
        "source": "models.dev",
        "upstream": "https://github.com/anomalyco/models.dev",
        "upstream_commit": "0" * 40,
        "generated_at": "2026-11-02T00:00:00+00:00",
        "overrides_version": 1,
        "license": "MIT",
        "providers": {
            "deepseek": {
                "models_dev": "deepseek",
                "models": {
                    mid: {"name": mid.title(), "cost": {"currency": "USD", "per_tokens": 1000000, "input": i, "output": o}}
                    for mid, (i, o) in prices.items()
                },
            }
        },
    }


class Report(unittest.TestCase):
    def test_moves_over_the_threshold_removed_and_new(self):
        old = table({"flash": (0.15, 0.6), "pro": (0.66, 1.98), "gone": (1.0, 1.0)})
        new = table({"flash": (0.30, 0.65), "pro": (0.66, 1.0), "fresh": (0.1, 0.2)})
        new["providers"]["deepseek"]["models"]["flash"]["cost"]["cache_read"] = 0.003
        text, attention = facts_report.report(old, new, 0.3, [])
        self.assertTrue(attention)
        self.assertIn("| deepseek | flash | input | 0.15 | 0.3 | +100% |", text)
        self.assertNotIn("| flash | output", text, "+8% is under 30%")
        self.assertIn("| deepseek | pro | output | 1.98 | 1.0 | -49% |", text)
        self.assertIn("| deepseek | flash | cache_read | None | 0.003 | appeared |", text)
        self.assertIn("### Models removed upstream (1)\n\n- deepseek / gone", text)
        self.assertIn("### New models (1)\n\n- deepseek / fresh (Fresh)", text)
        self.assertIn("schema: fits", text)

    def test_nothing_moved(self):
        old = table({"flash": (0.15, 0.6)})
        text, attention = facts_report.report(old, copy.deepcopy(old), 0.3, None)
        self.assertFalse(attention)
        self.assertIn("schema: not checked", text)
        self.assertIn("more than 30% (0)\n\nNone.", text)

    def test_the_command_line_and_the_schema(self):
        old = table({"flash": (0.15, 0.6)})
        bad = table({"flash": (-1.0, 0.6)})
        schema = os.path.join(HERE, "facts-1.schema.json")
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for name, t in (("old", old), ("new", old), ("bad", bad)):
                p = os.path.join(d, name + ".json")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(t, f)
                paths.append(p)
            run = lambda new: subprocess.run(  # noqa: E731
                [sys.executable, os.path.join(HERE, "facts_report.py"), paths[0], new, "--schema", schema],
                capture_output=True, text=True)
            good = run(paths[1])
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertIn("## Frey's facts table after this sync", good.stdout)
            try:
                import jsonschema  # noqa: F401
            except ImportError:
                return
            broken = run(paths[2])
            self.assertEqual(broken.returncode, 1, broken.stdout)
            self.assertIn("do not merge as it is", broken.stdout)


if __name__ == "__main__":
    unittest.main()
