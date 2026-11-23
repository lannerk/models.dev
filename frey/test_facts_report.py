#!/usr/bin/env python3
"""Tests of facts_report.py (T-0116 ①): a price moved by more than 30 % is listed (either way, and one that
appeared or went away), one moved by less is not; removed and new models; a table that does not fit the
schema makes the exit code 1. T-0189 ③: frey/merge_upstream.sh (class Merge, needs git).
`python3 frey/test_facts_report.py` (jsonschema optional)."""

import copy
import json
import os
import shutil
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


@unittest.skipIf(os.name == "nt" or not shutil.which("bash") or not shutil.which("git"),
                 "merge_upstream.sh runs in the fork's Linux workflow; on Windows `bash` may be WSL's, which reads "
                 "neither these paths nor this git")
class Merge(unittest.TestCase):
    """T-0189 ③ (B-0025): merge_upstream.sh with a made-up upstream and fork. Upstream changes one workflow
    file, adds one and changes a model file: the sync is one commit onto the fork whose workflows are the
    fork's own (nothing in it a workflow token cannot push), with the model change, and the two workflow
    files are listed (a conflict in that directory goes the fork's way). The next week merges from the upstream commit taken (no conflict with itself); a
    conflict outside the workflows stops and changes nothing."""

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout.strip()

    def write(self, repo, path, text):
        p = os.path.join(repo, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)

    def commit(self, repo, message):
        self.git(repo, "add", "-A")
        self.git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", message)

    def merge(self, fork, out):
        return subprocess.run(["bash", os.path.join(fork, "frey", "merge_upstream.sh"), out], cwd=fork,
                              capture_output=True, text=True)

    def test_workflows_kept_and_the_next_week(self):
        with tempfile.TemporaryDirectory() as d:
            up, fork, out = (os.path.join(d, n) for n in ("up", "fork", "out"))
            os.makedirs(up)
            self.git(up, "init", "-q", "-b", "dev")
            self.write(up, ".github/workflows/ci-fixer.yml", "name: ci-fixer\n")
            self.write(up, ".github/workflows/deploy.yml", "name: deploy\n")
            self.write(up, "providers/x/models/m.toml", "input = 1\noutput = 2\n")
            self.write(up, "providers/x/models/n.toml", "input = 5\n")
            self.commit(up, "upstream 1")
            subprocess.run(["git", "clone", "-q", "-b", "dev", up, fork], check=True)
            self.git(fork, "remote", "rename", "origin", "upstream")
            # The fork: its own sync workflow, upstream's left as they were, Frey's directory.
            self.write(fork, ".github/workflows/frey-sync.yml", "name: frey-sync\n")
            # …and one of upstream's changed here, so that upstream's change to it conflicts: the fork's wins.
            self.write(fork, ".github/workflows/ci-fixer.yml", "name: ci-fixer\n# off in the fork\n")
            with open(os.path.join(HERE, "merge_upstream.sh"), encoding="utf-8") as f:
                self.write(fork, "frey/merge_upstream.sh", f.read())
            self.commit(fork, "fork")
            fork_workflows = self.git(fork, "ls-tree", "-r", "HEAD", "--", ".github/workflows")
            # Upstream: one workflow changed, one added, a model changed.
            self.write(up, ".github/workflows/ci-fixer.yml", "name: ci-fixer\nenv: aws\n")
            self.write(up, ".github/workflows/release.yml", "name: release\n")
            self.write(up, "providers/x/models/m.toml", "input = 3\noutput = 2\n")
            self.commit(up, "upstream 2")
            self.git(fork, "switch", "-q", "-c", "frey-sync/1")
            self.git(fork, "fetch", "-q", "upstream", "dev")
            before = self.git(fork, "rev-parse", "HEAD")
            r = self.merge(fork, out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            with open(os.path.join(out, "changed")) as f:
                self.assertEqual(f.read().strip(), "yes")
            self.assertEqual(self.git(fork, "symbolic-ref", "--short", "HEAD"), "frey-sync/1")
            # One commit onto the fork; nothing under the workflows changed; the model change is in.
            self.assertEqual(self.git(fork, "rev-list", f"{before}..HEAD"), self.git(fork, "rev-parse", "HEAD"))
            self.assertEqual(self.git(fork, "rev-parse", "HEAD^"), before)
            self.assertEqual(self.git(fork, "diff", "--name-only", before, "HEAD", "--", ".github"), "")
            self.assertEqual(self.git(fork, "ls-tree", "-r", "HEAD", "--", ".github/workflows"), fork_workflows)
            self.assertEqual(self.git(fork, "show", "HEAD:providers/x/models/m.toml"), "input = 3\noutput = 2")
            self.assertEqual(self.git(fork, "status", "--porcelain"), "")
            self.assertEqual(self.git(fork, "show", "HEAD:frey/upstream-dev"), self.git(fork, "rev-parse", "upstream/dev"))
            with open(os.path.join(out, "merge.log"), encoding="utf-8") as f:
                self.assertIn("CONFLICT (content): Merge conflict in .github/workflows/ci-fixer.yml", f.read())
            with open(os.path.join(out, "workflows.md"), encoding="utf-8") as f:
                listed = f.read()
            self.assertIn("`.github/workflows/ci-fixer.yml` (changed)", listed)
            self.assertIn("`.github/workflows/release.yml` (added)", listed)
            self.assertNotIn("deploy.yml", listed)
            # Nothing new: no.
            r = self.merge(fork, out)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(out, "changed")) as f:
                self.assertEqual(f.read().strip(), "no")
            # The next week (the pull request merged into dev): the same line changed again — merged from
            # the upstream commit taken, so no conflict with last week's change.
            self.git(fork, "switch", "-q", "-c", "frey-sync/2")
            self.write(up, "providers/x/models/m.toml", "input = 4\noutput = 2\n")
            self.write(up, ".github/workflows/ci-fixer.yml", "name: ci-fixer\nenv: aws2\n")
            self.commit(up, "upstream 3")
            self.git(fork, "fetch", "-q", "upstream", "dev")
            r = self.merge(fork, out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.git(fork, "show", "HEAD:providers/x/models/m.toml"), "input = 4\noutput = 2")
            self.assertEqual(self.git(fork, "ls-tree", "-r", "HEAD", "--", ".github/workflows"), fork_workflows)
            with open(os.path.join(out, "workflows.md"), encoding="utf-8") as f:
                listed = f.read()
            self.assertIn("ci-fixer.yml` (changed)", listed)
            self.assertNotIn("release.yml", listed, "only what changed since the last sync")
            # A conflict outside the workflows: stops (3), the branch as it was.
            self.git(fork, "switch", "-q", "-c", "frey-sync/3")
            self.write(fork, "providers/x/models/n.toml", "input = 6\n")
            self.commit(fork, "a fork-side change")
            self.write(up, "providers/x/models/n.toml", "input = 7\n")
            self.commit(up, "upstream 4")
            self.git(fork, "fetch", "-q", "upstream", "dev")
            head = self.git(fork, "rev-parse", "HEAD")
            r = self.merge(fork, out)
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
            self.assertIn("providers/x/models/n.toml", r.stderr)
            self.assertEqual(self.git(fork, "rev-parse", "HEAD"), head)
            self.assertEqual(self.git(fork, "symbolic-ref", "--short", "HEAD"), "frey-sync/3")
            self.assertEqual(self.git(fork, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
