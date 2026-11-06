#!/usr/bin/env python3
"""models_facts.py — the model facts table (T-0112, AD132 A): `configs/models-facts.json` from a models.dev
checkout (https://github.com/anomalyco/models.dev, MIT).

    python3 tools/models_facts.py <models.dev checkout> [--out configs/models-facts.json] [--check]
        [--vendors <toml>] [--overrides <toml>] [--upstream <url>] [--commit <id> --date <time>]
    (--upstream: the repository the checkout is of, written into the header — our fork's when the catalog
    builds from it; the last two for tests)

For every preset in `configs/vendors.toml` that names a `models_dev` provider, every model that provider
serves: its limits, prices (input / output / reasoning / cache read and write, the price overrides and the
time-of-day multipliers as models.dev writes them), modalities, tool and reasoning support, status, dates,
open weights and the benchmarks its lab reports — the provider's file merged over its `base_model` (lab)
file the way models.dev merges them (plain tables deep-merge, arrays and values replace,
`base_model_omit` removes after merging). Then `configs/models-facts-overrides.toml` on top.

Reproducible: the same checkout gives the same bytes (`generated_at` is the upstream commit's time, not
now; keys sorted; one model per line). `--check` rewrites nothing and fails when the file would change.
stderr gets the presets models.dev does not serve and the ones whose address differs from models.dev's —
listed, never changed (the presets are recorded from the vendors' own documentation).

The output is data. Nothing in it can turn a permission, a tool or a prompt on: Frey reads it for numbers
(windows, output limits, prices) and shows the rest (frey_vendors::facts).
"""

import json
import os
import subprocess
import sys
import tomllib
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
FREY = os.path.dirname(HERE)
VENDORS = os.path.join(FREY, "configs", "vendors.toml")
OVERRIDES = os.path.join(FREY, "configs", "models-facts-overrides.toml")
OUT = os.path.join(FREY, "configs", "models-facts.json")
FORMAT = 1
UPSTREAM = "https://github.com/anomalyco/models.dev"


def merge(base, over):
    """models.dev's merge: plain tables deep-merge; arrays and values replace."""
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def omit(d, dotted):
    *path, last = dotted.split(".")
    for p in path:
        d = d.get(p)
        if not isinstance(d, dict):
            return
    d.pop(last, None)


def load_model(repo, path):
    with open(path, "rb") as f:
        own = tomllib.load(f)
    base_id = own.get("base_model")
    if base_id:
        with open(os.path.join(repo, "models", base_id + ".toml"), "rb") as f:
            base = tomllib.load(f)
        merged = merge(base, {k: v for k, v in own.items() if k not in ("base_model", "base_model_omit")})
        for dotted in own.get("base_model_omit", []):
            omit(merged, dotted)
        return merged
    return own


def number(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def cache_write(cache):
    """A cache write price: a number, or the shortest-lived one of several (`{"5m": …, "1h": …}`)."""
    w = cache.get("write")
    if isinstance(w, dict):
        def minutes(k):
            n = "".join(c for c in k if c.isdigit()) or "0"
            return int(n) * (60 if k.endswith("h") else 1)
        keys = sorted(w, key=minutes)
        return number(w[keys[0]]) if keys else None
    return number(w)


def cost_of(raw):
    text = raw.get("text") or {}
    inp, out = text.get("input") or {}, text.get("output") or {}
    if number(inp.get("price")) is None and number(out.get("price")) is None:
        return None
    cache = inp.get("cache") if isinstance(inp.get("cache"), dict) else {}
    c = {
        "currency": "USD",
        "per_tokens": 1000000,
        "input": number(inp.get("price")),
        "output": number(out.get("price")),
        "reasoning": number(out.get("reasoning")),
        "cache_read": number(cache.get("read")),
        "cache_write": cache_write(cache),
    }
    if inp.get("unit"):
        c["unit"] = inp["unit"]
    # An override sets some of the prices when its condition holds (models.dev: "matching overrides merge
    # field by field, in order"): the input's price and cache prices, the output's price and reasoning price.
    def override(o, fields):
        r = {"when": o.get("when", {})}
        for name, value in fields(o).items():
            if number(value) is not None:
                r[name] = value
        return r

    def input_fields(o):
        cache = o.get("cache") if isinstance(o.get("cache"), dict) else {}
        return {"price": o.get("price"), "cache_read": cache.get("read"), "cache_write": cache_write(cache)}

    def output_fields(o):
        return {"price": o.get("price"), "reasoning": o.get("reasoning")}

    if inp.get("overrides"):
        c["input_overrides"] = [override(o, input_fields) for o in inp["overrides"]]
    if out.get("overrides"):
        c["output_overrides"] = [override(o, output_fields) for o in out["overrides"]]
    # A multiplier's factor is a number, or one per kind of token (`{"text": 1.1}`): the text one.
    mults = []
    for m in raw.get("multipliers") or []:
        factor = m.get("factor")
        if isinstance(factor, dict):
            factor = factor.get("text")
        if number(factor) is not None:
            mults.append({"when": m.get("when", {}), "factor": factor})
    if mults:
        c["multipliers"] = mults
    return {k: v for k, v in c.items() if v is not None}


def capability(caps, name):
    v = caps.get(name)
    if isinstance(v, dict):
        return v.get("supported")
    return v if isinstance(v, bool) else None


def facts_of(m):
    limit = {k: number(v) for k, v in (m.get("limit") or {}).items() if k in ("context", "input", "output")}
    caps = m.get("capabilities") or {}
    f = {
        "name": m.get("name"),
        "status": m.get("status"),
        "release_date": str(m["release_date"]) if m.get("release_date") else None,
        "knowledge": str(m["knowledge"]) if m.get("knowledge") else None,
        "open_weights": m.get("open_weights"),
        # models.dev writes 0 for a limit that does not apply (an image model's window): left out.
        "limit": {k: v for k, v in limit.items() if v} or None,
        "modalities": m.get("modalities") or None,
        "tools": capability(caps, "tools"),
        "reasoning": capability(caps, "reasoning"),
        "cost": cost_of(m.get("cost") or {}),
        "benchmarks": [
            {k: b[k] for k in ("name", "score", "variant", "metric", "dataset", "version", "harness", "date", "source") if k in b}
            for b in m.get("benchmarks") or []
        ] or None,
    }
    for b in f["benchmarks"] or []:
        if "date" in b:
            b["date"] = str(b["date"])
    return {k: v for k, v in f.items() if v is not None}


def hosts(url):
    return {urlparse(url).hostname} if url else set()


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    repo = argv[1]

    def flag(name, default):
        return argv[argv.index(name) + 1] if name in argv else default

    out = flag("--out", OUT)
    check = "--check" in argv
    if "--commit" in argv:
        commit, when = flag("--commit", ""), flag("--date", "")
    else:
        commit, when = subprocess.run(
            ["git", "-C", repo, "log", "-1", "--format=%H %cI"], capture_output=True, text=True, check=True
        ).stdout.split()
    with open(flag("--vendors", VENDORS), "rb") as f:
        vendors = tomllib.load(f)["vendor"]
    overrides = {"version": 0, "override": []}
    overrides_file = flag("--overrides", OVERRIDES)
    if os.path.exists(overrides_file):
        with open(overrides_file, "rb") as f:
            overrides = tomllib.load(f)
    providers, report = {}, []
    for v in vendors:
        pid = v.get("models_dev")
        if not pid:
            report.append(f"{v['name']}: no models.dev provider (not in the table)")
            continue
        pdir = os.path.join(repo, "providers", pid)
        with open(os.path.join(pdir, "provider.toml"), "rb") as f:
            provider = tomllib.load(f)
        ours = set().union(*(hosts(v.get(k)) for k in ("openai_base_url", "messages_base_url", "responses_base_url", "gemini_base_url")))
        ours |= set(v.get("hosts", []))
        theirs = hosts(provider.get("api"))
        if theirs and not theirs & ours:
            report.append(f"{v['name']}: models.dev's {pid} is at {provider['api']}, the preset at {', '.join(sorted(ours))}")
        models = {}
        mdir = os.path.join(pdir, "models")
        for dirpath, _, files in os.walk(mdir):
            for name in files:
                if not name.endswith(".toml"):
                    continue
                path = os.path.join(dirpath, name)
                mid = os.path.relpath(path, mdir)[: -len(".toml")].replace(os.sep, "/")
                models[mid] = facts_of(load_model(repo, path))
        for o in overrides.get("override", []):
            if o.get("vendor") == v["name"] and o.get("model") in models:
                models[o["model"]] = merge(models[o["model"]], o.get("set", {}))
        providers[v["name"]] = {"models_dev": pid, "models": models}
    header = {
        "format": FORMAT,
        "source": "models.dev",
        "upstream": flag("--upstream", UPSTREAM),
        "upstream_commit": commit,
        "generated_at": when,
        "overrides_version": overrides.get("version", 0),
        "license": "MIT (Copyright (c) 2025 models.dev); configs/models-facts.LICENSE",
    }
    lines = ["{"]
    for k in sorted(header):
        lines.append(f"  {json.dumps(k)}: {json.dumps(header[k], ensure_ascii=False)},")
    lines.append('  "providers": {')
    pnames = sorted(providers)
    for i, p in enumerate(pnames):
        entry = providers[p]
        lines.append(f"    {json.dumps(p)}: {{")
        lines.append(f'      "models_dev": {json.dumps(entry["models_dev"])},')
        lines.append('      "models": {')
        mids = sorted(entry["models"])
        for j, mid in enumerate(mids):
            body = json.dumps(entry["models"][mid], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            lines.append(f"        {json.dumps(mid)}: {body}" + ("," if j + 1 < len(mids) else ""))
        lines.append("      }")
        lines.append("    }" + ("," if i + 1 < len(pnames) else ""))
    lines.append("  }")
    lines.append("}")
    text = "\n".join(lines) + "\n"
    count = sum(len(e["models"]) for e in providers.values())
    for r in report:
        print("models_facts: " + r, file=sys.stderr)
    if check:
        with open(out, encoding="utf-8") as f:
            if f.read() != text:
                sys.exit(f"models_facts: {out} differs from what {commit[:12]} gives")
        print(f"models_facts: {out} is what {commit[:12]} gives ({count} models)", file=sys.stderr)
        return
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"models_facts: {out}: {len(providers)} presets, {count} models, models.dev {commit[:12]} ({when})", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv)
