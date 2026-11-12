#!/usr/bin/env python3
"""models_sources.py — T-0174 (AD159): the other three sources of the model table, the weekly merge, and
the release check.

The table (`configs/models-facts.json`) is built in this order, each a snapshot kept in
`configs/sources/` and never edited by hand:

  1. models.dev — the facts (tools/models_facts.py)
  2. pi — the interface layer (tools/models_pi.py)
  3. OpenRouter — `GET https://openrouter.ai/api/v1/models` (public, no key): each model's `reasoning`
     (`supported_efforts`, `default_effort`, `mandatory`, `default_enabled`) is the thinking layer of the
     `openrouter` preset's models — the endpoint's own word on itself, so it wins over pi's levels there
     (a difference is listed); `supported_parameters` is checked against pi's interface fields (listed
     only). Its terms of use are in `configs/sources/openrouter.TERMS.md`.
  4. LiteLLM — `model_prices_and_context_window.json` (MIT): when a model retires and what replaces it
     (`lifecycle`), the shortest prompt a cache takes (`cache_min_tokens`), parallel tool calls
     (`parallel_tool_calls`) into the facts layer; its windows and output limits are only compared (its
     DeepSeek entries say 131,072 where the vendor and the others say about a million — listed, never
     taken).
  5. aider — `aider/resources/model-settings.yml` (Apache-2.0): hints only, into
     `configs/sources/aider-hints.json`; never in the table, never in effect (which model to test for
     what first).
  6. our own corrections (`configs/models-facts-overrides.toml`, by models_facts.py) and the recorded
     quirk table (`configs/models.toml`, read by Frey after the table) win over all of these.

    python3 tools/models_sources.py snapshot openrouter <models.json> [--at <YYYY-MM-DD>]
    python3 tools/models_sources.py snapshot litellm <checkout>       [--at <YYYY-MM-DD>]
    python3 tools/models_sources.py snapshot aider <checkout>         [--at <YYYY-MM-DD>]
        the downloaded file (or checkout) as the snapshot, the fields Frey reads only; `--at` is the day
        it was taken (default today); its license or terms beside it
    python3 tools/models_sources.py apply [--check] [--without openrouter]
        pi's layer (as models_pi.py apply) and then layers 3–5 onto configs/models-facts.json; the
        differences between the sources into configs/sources/conflicts.json, aider's hints into
        configs/sources/aider-hints.json. --check rewrites nothing and fails when a file would change.
        --without openrouter leaves its layer out (its terms, below).
    python3 tools/models_sources.py changes <last week's table> [<this week's table>]
        the weekly report: models added and removed, windows, prices and thinking levels that changed
    python3 tools/models_sources.py age [--at <YYYY-MM-DD>] [--max-days 7]
        the release check: the table's date — the oldest day among the sources taken — at most
        `--max-days` before `--at` (default today), else exit 1
"""

import datetime
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import models_pi  # noqa: E402

FREY = os.path.dirname(HERE)
CONFIGS = os.path.join(FREY, "configs")
SOURCES = os.path.join(CONFIGS, "sources")
FACTS = os.path.join(CONFIGS, "models-facts.json")
OPENROUTER = os.path.join(SOURCES, "openrouter.json")
LITELLM = os.path.join(SOURCES, "litellm.json")
AIDER = os.path.join(SOURCES, "aider.json")
CONFLICTS = os.path.join(SOURCES, "conflicts.json")
HINTS = os.path.join(SOURCES, "aider-hints.json")

# Frey's level names, in order (frey_config::EFFORT_LEVELS without `off`).
LEVELS = ["minimal", "low", "medium", "high", "xhigh", "max"]

# LiteLLM's `litellm_provider` -> the presets it describes.
LITELLM_PRESETS = {
    "deepseek": ["deepseek"],
    "anthropic": ["anthropic"],
    "openai": ["openai"],
    "gemini": ["gemini"],
    "xai": ["xai"],
    "mistral": ["mistral"],
    "moonshot": ["moonshot", "moonshot-intl"],
    "minimax": ["minimax", "minimax-intl"],
    "dashscope": ["qwen", "qwen-intl"],
    "zai": ["zhipu", "zhipu-intl"],
}
# The LiteLLM fields kept in the snapshot.
LITELLM_FIELDS = [
    "litellm_provider", "mode", "max_input_tokens", "max_output_tokens", "deprecation_date",
    "deprecation_source", "successor_model", "prompt_cache_min_tokens",
    "supports_parallel_function_calling", "supports_function_calling", "supports_reasoning",
]
# aider's name prefix -> the presets it describes (a name without one is OpenAI's or Anthropic's by its
# family, as aider's own docs say).
AIDER_PRESETS = {
    "deepseek/": ["deepseek"], "anthropic/": ["anthropic"], "openai/": ["openai"],
    "gemini/": ["gemini"], "xai/": ["xai"], "mistral/": ["mistral"], "openrouter/": ["openrouter"],
}
AIDER_FIELDS = [
    "edit_format", "weak_model_name", "editor_model_name", "editor_edit_format", "use_repo_map",
    "use_temperature", "examples_as_sys_msg", "extra_params", "reasoning_tag", "accepts_settings",
    "cache_control", "caches_by_default", "streaming", "use_system_prompt", "lazy", "overeager",
    "reminder", "system_prompt_prefix",
]


def today():
    return datetime.date.today().isoformat()


def flag(argv, name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def write_json(path, value):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1) + "\n")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---- snapshots ------------------------------------------------------------------------------------


def snapshot_openrouter(path, at):
    raw = load(path)
    models = {}
    for m in raw.get("data", []):
        top = m.get("top_provider") or {}
        keep = {
            "context_length": m.get("context_length"),
            "max_completion_tokens": top.get("max_completion_tokens"),
            "reasoning": m.get("reasoning"),
            "supported_parameters": sorted(m.get("supported_parameters") or []),
            "expiration_date": m.get("expiration_date"),
        }
        models[m["id"]] = {k: v for k, v in keep.items() if v not in (None, [], {})}
    out = {
        "source": "https://openrouter.ai/api/v1/models",
        "taken": at,
        "terms": "configs/sources/openrouter.TERMS.md",
        "models": models,
    }
    write_json(OPENROUTER, out)
    return out


def git_head(checkout):
    head = os.path.join(checkout, ".git", "HEAD")
    if not os.path.exists(head):
        return None
    ref = open(head, encoding="utf-8").read().strip()
    if ref.startswith("ref: "):
        p = os.path.join(checkout, ".git", ref[5:])
        if os.path.exists(p):
            return open(p, encoding="utf-8").read().strip()
        packed = os.path.join(checkout, ".git", "packed-refs")
        for line in open(packed, encoding="utf-8") if os.path.exists(packed) else []:
            if line.strip().endswith(ref[5:]):
                return line.split()[0]
        return None
    return ref


def snapshot_litellm(checkout, at):
    raw = load(os.path.join(checkout, "model_prices_and_context_window.json"))
    models = {}
    for name, e in raw.items():
        if not isinstance(e, dict) or e.get("litellm_provider") not in LITELLM_PRESETS:
            continue
        if e.get("mode") not in (None, "chat", "responses"):
            continue
        models[name] = {k: e[k] for k in LITELLM_FIELDS if k in e}
    out = {
        "source": "https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json",
        "commit": git_head(checkout),
        "taken": at,
        "license": "MIT; configs/sources/litellm.LICENSE",
        "models": models,
    }
    write_json(LITELLM, out)
    shutil.copyfile(os.path.join(checkout, "LICENSE"), os.path.join(SOURCES, "litellm.LICENSE"))
    return out


def snapshot_aider(checkout, at):
    import yaml  # only here: the snapshot is taken where PyYAML is; apply reads JSON

    with open(os.path.join(checkout, "aider", "resources", "model-settings.yml"), encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    models = {}
    for e in raw:
        models[e["name"]] = {k: e[k] for k in AIDER_FIELDS if k in e}
    out = {
        "source": "https://github.com/Aider-AI/aider/blob/main/aider/resources/model-settings.yml",
        "commit": git_head(checkout),
        "taken": at,
        "license": "Apache-2.0; configs/sources/aider.LICENSE",
        "models": models,
    }
    write_json(AIDER, out)
    shutil.copyfile(os.path.join(checkout, "LICENSE.txt"), os.path.join(SOURCES, "aider.LICENSE"))
    return out


# ---- the layers -------------------------------------------------------------------------------------


def strip(table):
    """Takes this script's layers off (so apply can run again): the thinking levels OpenRouter set (pi's
    come back with its layer), and the lifecycle fields."""
    for prov in table["providers"].values():
        for m in prov.get("models", {}).values():
            for k in ("lifecycle", "cache_min_tokens", "parallel_tool_calls"):
                m.pop(k, None)
    table.pop("sources", None)


def openrouter_levels(reasoning):
    """OpenRouter's `reasoning` as (levels, off, always_on, default): levels in Frey's order with the
    value OpenRouter takes (its effort names are Frey's), `none` as the value that turns it off."""
    efforts = reasoning.get("supported_efforts") or []
    levels = [[l, l] for l in LEVELS if l in efforts]
    off = "none" if "none" in efforts else None
    return levels, off, bool(reasoning.get("mandatory")), reasoning.get("default_effort")


def layer_openrouter(table, snap, conflicts):
    """Layer 3 for the `openrouter` preset: OpenRouter's own levels; pi's that differ are listed."""
    prov = table["providers"].get("openrouter")
    if not prov:
        return 0
    taken = "openrouter api %s" % snap["taken"]
    n = 0
    for mid, m in prov["models"].items():
        o = snap["models"].get(mid)
        if not o or not o.get("reasoning"):
            continue
        levels, off, always, default = openrouter_levels(o["reasoning"])
        if not levels:
            continue
        iface = m.setdefault("interface", {}).setdefault("openai_compat", {"from": taken})
        pi_levels = iface.get("thinking_levels")
        if pi_levels is not None and [l for l, _ in pi_levels] != [l for l, _ in levels]:
            conflicts["thinking"].append({
                "preset": "openrouter", "model": mid,
                "pi": [l for l, _ in pi_levels], "openrouter": [l for l, _ in levels],
                "used": "openrouter",
            })
        iface["thinking_levels"] = levels
        iface["thinking_from"] = taken
        if default:
            iface["thinking_default"] = default
        if off:
            iface["thinking_off"] = off
            iface.pop("thinking_always_on", None)
        if always:
            iface["thinking_always_on"] = True
            iface.pop("thinking_off", None)
        # supported_parameters against pi's interface fields: listed only.
        params = set(o.get("supported_parameters") or [])
        if params and iface.get("supports_reasoning_effort") and not ({"reasoning", "reasoning_effort"} & params):
            conflicts["parameters"].append({
                "preset": "openrouter", "model": mid,
                "pi": "supports_reasoning_effort", "openrouter": "takes neither reasoning nor reasoning_effort",
            })
        n += 1
    return n


def litellm_entry(snap, preset, mid):
    """LiteLLM's entry for (preset, model): `<provider>/<model>`, else the bare name of that provider."""
    for prov, presets in LITELLM_PRESETS.items():
        if preset not in presets:
            continue
        for key in ("%s/%s" % (prov, mid), mid):
            e = snap["models"].get(key)
            if e and e.get("litellm_provider") == prov:
                return key, e
    return None, None


def layer_litellm(table, snap, conflicts):
    """Layer 1 additions from LiteLLM; its windows and output limits only compared."""
    taken = "litellm %s %s" % ((snap.get("commit") or "")[:12], snap["taken"])
    n = 0
    for preset, prov in sorted(table["providers"].items()):
        for mid, m in sorted(prov["models"].items()):
            key, e = litellm_entry(snap, preset, mid)
            if not e:
                continue
            if e.get("deprecation_date"):
                life = {"retires": e["deprecation_date"], "from": taken}
                if e.get("successor_model"):
                    life["successor"] = e["successor_model"]
                if e.get("deprecation_source"):
                    life["source"] = e["deprecation_source"]
                m["lifecycle"] = life
            if e.get("prompt_cache_min_tokens"):
                # LiteLLM writes it as a float (4096.0).
                m["cache_min_tokens"] = int(e["prompt_cache_min_tokens"])
            if "supports_parallel_function_calling" in e:
                m["parallel_tool_calls"] = bool(e["supports_parallel_function_calling"])
            limit = m.get("limit") or {}
            for ours, theirs, what in (("context", "max_input_tokens", "window"), ("output", "max_output_tokens", "output")):
                a, b = limit.get(ours), e.get(theirs)
                if a and b and a != b:
                    conflicts["limits"].append({
                        "preset": preset, "model": mid, "what": what,
                        "models.dev": a, "litellm": b, "litellm_entry": key, "used": "models.dev",
                    })
            n += 1
    return n


def aider_hints(table, snap):
    """aider's settings for the models of the table, by preset — hints, never applied."""
    out = {}
    for name, e in sorted(snap["models"].items()):
        for prefix, presets in AIDER_PRESETS.items():
            if not name.startswith(prefix):
                continue
            mid = name[len(prefix):]
            for preset in presets:
                if mid in table["providers"].get(preset, {}).get("models", {}):
                    out.setdefault(preset, {})[mid] = e
    return {
        "note": "aider's model settings as hints only: never in the table, never in effect (AD159: which model to test for what first).",
        "source": snap["source"],
        "commit": snap.get("commit"),
        "taken": snap["taken"],
        "license": snap["license"],
        "hints": out,
    }


def build(table, without=(), sources=SOURCES, pi=None):
    """`table` with pi's layer and layers 3–5 on (an earlier one replaced), the snapshots read from
    `sources` (the release repositories keep their copies elsewhere): (table, unmatched, conflicts,
    hints, counts)."""
    pi_path = pi or os.path.join(sources, os.path.basename(models_pi.SNAPSHOT))
    table, unmatched = models_pi.layer(table, models_pi.load_snapshot(pi_path))
    openrouter, litellm, aider = (os.path.join(sources, os.path.basename(p)) for p in (OPENROUTER, LITELLM, AIDER))
    # The recorded quirk table is Frey's (the release repositories have none: nothing to compare there).
    recorded = os.path.join(CONFIGS, "models.toml")
    unmatched["recorded_conflicts"] = models_pi.recorded_conflicts(table) if os.path.exists(recorded) else []
    strip(table)
    conflicts = {"thinking": [], "parameters": [], "limits": []}
    taken = {"models.dev": table.get("generated_at", "")[:10]}
    if os.path.exists(pi_path):
        snap = models_pi.load_snapshot(pi_path)
        taken["pi"] = snap.get("taken") or "pi-ai %s" % snap.get("version")
    counts = {}
    hints = None
    if "openrouter" not in without and os.path.exists(openrouter):
        snap = load(openrouter)
        counts["openrouter"] = layer_openrouter(table, snap, conflicts)
        taken["openrouter"] = snap["taken"]
    if os.path.exists(litellm):
        snap = load(litellm)
        counts["litellm"] = layer_litellm(table, snap, conflicts)
        taken["litellm"] = snap["taken"]
    if os.path.exists(aider):
        snap = load(aider)
        hints = aider_hints(table, snap)
        counts["aider"] = sum(len(v) for v in hints["hints"].values())
        taken["aider"] = snap["taken"]
    table["sources"] = taken
    for v in conflicts.values():
        v.sort(key=lambda c: json.dumps(c, sort_keys=True))
    return table, unmatched, conflicts, hints, counts


def is_day(text):
    try:
        datetime.date.fromisoformat(text)
        return True
    except (TypeError, ValueError):
        return False


def table_date(table):
    """The table's date: the day the weekly merge took its snapshots — the oldest of them (all were taken
    by then). models.dev's is its upstream commit's day, which the fork's weekly pull request (reviewed by
    a person, AD132 ⑤) moves; it is reported, not counted (see `age`)."""
    days = [d for k, d in (table.get("sources") or {}).items() if k != "models.dev" and is_day(d)]
    return min(days) if days else table.get("generated_at", "")[:10]


def apply(argv):
    import models_facts

    check = "--check" in argv
    without = {flag(argv, "--without")} - {None}
    before = open(FACTS, encoding="utf-8").read()
    table, unmatched, conflicts, hints, counts = build(json.loads(before), without)
    out = models_facts.render({k: v for k, v in table.items() if k != "providers"}, table["providers"])
    files = {
        FACTS: out,
        models_pi.UNMATCHED: json.dumps(unmatched, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
        CONFLICTS: json.dumps(conflicts, ensure_ascii=False, sort_keys=True, indent=1) + "\n",
    }
    if hints is not None:
        files[HINTS] = json.dumps(hints, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    if check:
        stale = [os.path.relpath(p, FREY) for p, text in files.items()
                 if not os.path.exists(p) or open(p, encoding="utf-8").read() != text]
        if stale:
            print("models_sources: would change: " + ", ".join(stale), file=sys.stderr)
            return 1
        print("models_sources: OK (current)")
        return 0
    for p, text in files.items():
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print("models_sources: %s; conflicts: %d thinking, %d parameters, %d limits; table date %s"
          % (", ".join("%s %d" % kv for kv in sorted(counts.items())), len(conflicts["thinking"]),
             len(conflicts["parameters"]), len(conflicts["limits"]), table_date(table)))
    return 0


# ---- the weekly report and the release check ----------------------------------------------------------


def changes(old, new):
    """What changed from `old` to `new` (two tables): models added and removed, windows, output limits,
    input and output prices, thinking levels — per preset and model."""
    out = {"added": [], "removed": [], "changed": []}
    for preset in sorted(set(old["providers"]) | set(new["providers"])):
        a = old["providers"].get(preset, {}).get("models", {})
        b = new["providers"].get(preset, {}).get("models", {})
        out["added"] += ["%s/%s" % (preset, m) for m in sorted(set(b) - set(a))]
        out["removed"] += ["%s/%s" % (preset, m) for m in sorted(set(a) - set(b))]
        for mid in sorted(set(a) & set(b)):
            x, y = a[mid], b[mid]
            for what, get in (
                ("window", lambda e: (e.get("limit") or {}).get("context")),
                ("output", lambda e: (e.get("limit") or {}).get("output")),
                ("input price", lambda e: (e.get("cost") or {}).get("input")),
                ("output price", lambda e: (e.get("cost") or {}).get("output")),
                ("thinking", lambda e: [l for i in (e.get("interface") or {}).values() for l, _ in i.get("thinking_levels", [])]),
                ("retires", lambda e: (e.get("lifecycle") or {}).get("retires")),
            ):
                if get(x) != get(y):
                    out["changed"].append({"model": "%s/%s" % (preset, mid), "what": what, "was": get(x), "now": get(y)})
    return out


def age(argv):
    at = datetime.date.fromisoformat(flag(argv, "--at", today()))
    most = int(flag(argv, "--max-days", "7"))
    table = load(flag(argv, "--table", FACTS))
    day = table_date(table)
    days = (at - datetime.date.fromisoformat(day)).days
    content = table.get("generated_at", "")[:10]
    if is_day(content) and (at - datetime.date.fromisoformat(content)).days > most:
        print("models_sources: note: models.dev's part is from %s — the fork's weekly pull request "
              "(lannerk/models.dev, frey-sync/<day>) waits for review (AD132 ⑤)" % content, file=sys.stderr)
    if days > most:
        print("models_sources: the model table is from %s, %d days before %s (at most %d): run the weekly merge "
              "(docs/ops/release.md §4.2) before releasing" % (day, days, at, most), file=sys.stderr)
        return 1
    print("models_sources: the model table is from %s (%d days before %s, at most %d)" % (day, days, at, most))
    return 0


def main(argv):
    if len(argv) >= 3 and argv[0] == "snapshot":
        at = flag(argv, "--at", today())
        kind, path = argv[1], argv[2]
        made = {"openrouter": snapshot_openrouter, "litellm": snapshot_litellm, "aider": snapshot_aider}.get(kind)
        if not made:
            print(__doc__, file=sys.stderr)
            return 2
        out = made(path, at)
        print("models_sources: %s snapshot of %d models (%s)" % (kind, len(out["models"]), at))
        return 0
    if argv and argv[0] == "apply":
        return apply(argv)
    if len(argv) >= 2 and argv[0] == "changes":
        new = load(argv[2]) if len(argv) >= 3 else load(FACTS)
        print(json.dumps(changes(load(argv[1]), new), ensure_ascii=False, indent=1))
        return 0
    if argv and argv[0] == "age":
        return age(argv)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
