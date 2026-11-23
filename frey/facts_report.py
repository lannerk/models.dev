#!/usr/bin/env python3
"""facts_report.py — what an upstream sync would change in Frey's facts table (T-0116, AD132 ⑤).

    python3 frey/facts_report.py <old.json> <new.json> [--schema frey/facts-1.schema.json] [--threshold 0.3]

Both files are facts tables as frey/models_facts.py writes them (the fork's `dev` before the sync, and
after merging upstream). Prints a Markdown report for the pull request: the new table checked against the
schema (when jsonschema is installed; a table that does not fit makes the exit code 1), then — for Frey's
presets only — the prices that moved by more than the threshold (30 % by default) either way, the models
models.dev removed, and the new ones. A person reads it and merges, or fixes `frey/overrides/` first.
Standard library only (jsonschema optional).
"""

import json
import sys

PRICES = ("input", "output", "reasoning", "cache_read", "cache_write")


def flag(argv, name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def models(table):
    out = {}
    for preset, p in table.get("providers", {}).items():
        for mid, m in p.get("models", {}).items():
            out[(preset, mid)] = m
    return out


def moved(old, new, threshold):
    """(preset, model, price, before, after, change) for each price that moved by more than `threshold`
    (a price that appeared or went away counts as moved)."""
    out = []
    for key in sorted(set(old) & set(new)):
        a, b = old[key].get("cost") or {}, new[key].get("cost") or {}
        for name in PRICES:
            x, y = a.get(name), b.get(name)
            if x == y:
                continue
            if x is None or y is None:
                out.append((*key, name, x, y, None))
                continue
            change = (y - x) / x if x else float("inf")
            if abs(change) > threshold:
                out.append((*key, name, x, y, change))
    return out


def schema_errors(table, schema_path):
    try:
        import jsonschema  # noqa: PLC0415 (optional)
    except ImportError:
        return None
    with open(schema_path, encoding="utf-8") as f:
        schema = json.load(f)
    validator = jsonschema.Draft202012Validator(schema)
    return [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in validator.iter_errors(table)][:20]


def report(old, new, threshold, errors):
    o, n = models(old), models(new)
    lines = ["## Frey's facts table after this sync", ""]
    lines.append(f"- upstream `{old.get('upstream_commit', '?')[:12]}` → `{new.get('upstream_commit', '?')[:12]}`; "
                 f"{len(o)} → {len(n)} models of Frey's presets")
    if errors is None:
        lines.append("- schema: not checked (jsonschema is not installed)")
    elif errors:
        lines.append(f"- **schema: {len(errors)} problem(s) — do not merge as it is**")
        lines += [f"  - {e}" for e in errors]
    else:
        lines.append("- schema: fits `facts-1`")
    changes = moved(o, n, threshold)
    removed = sorted(set(o) - set(n))
    added = sorted(set(n) - set(o))
    lines += ["", f"### Prices that moved by more than {threshold:.0%} ({len(changes)})", ""]
    if changes:
        lines += ["| preset | model | price | before | after | change |", "|---|---|---|---|---|---|"]
        for preset, mid, name, x, y, change in changes:
            shown = "appeared" if x is None else "went away" if y is None else f"{change:+.0%}"
            lines.append(f"| {preset} | {mid} | {name} | {x} | {y} | {shown} |")
    else:
        lines.append("None.")
    lines += ["", f"### Models removed upstream ({len(removed)})", ""]
    lines += [f"- {p} / {m}" for p, m in removed] or ["None."]
    lines += ["", f"### New models ({len(added)})", ""]
    lines += [f"- {p} / {m} ({n[(p, m)].get('name', '')})" for p, m in added[:200]] or ["None."]
    if len(added) > 200:
        lines.append(f"- … and {len(added) - 200} more")
    lines += ["", "A person reads this and merges; corrections go into `frey/overrides/models-facts-overrides.toml`, "
              "never into upstream's files."]
    return "\n".join(lines) + "\n", bool(changes or removed)


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    with open(argv[1], encoding="utf-8") as f:
        old = json.load(f)
    with open(argv[2], encoding="utf-8") as f:
        new = json.load(f)
    errors = schema_errors(new, flag(argv, "--schema", "frey/facts-1.schema.json"))
    text, _ = report(old, new, float(flag(argv, "--threshold", "0.3")), errors)
    sys.stdout.write(text)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
