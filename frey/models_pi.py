#!/usr/bin/env python3
"""models_pi.py — T-0173 (AD159): pi's model data as one source of the model table.

pi (https://github.com/earendil-works/pi, MIT) keeps, for every model it knows, how to call it: the
interface quirks (`compat`, 31 kinds) and the thinking levels (`thinkingLevelMap`: its seven level names
to the vendor's own value, `null` where the model has no such level). Frey's table takes those as its
"interface" layer.

    python3 tools/models_pi.py snapshot <pi-ai package dir>
        the package's `dist/providers/data/*.json` as they are, into `configs/sources/pi-ai.json`
        (version and license recorded; its LICENSE copied to `configs/sources/pi-ai.LICENSE`)
    python3 tools/models_pi.py apply [--check]
        `configs/sources/pi-ai.json` merged into `configs/models-facts.json` (any earlier pi layer
        replaced, so it can be run again); the names that did not match into
        `configs/sources/pi-ai-unmatched.json`. --check rewrites nothing and fails when either file
        would change.

How it is merged (the rules are in ai/specs/architecture.md §10, "模型表"):
- Only pi providers that are one of Frey's presets, on the protocol that preset speaks (PRESETS below);
  a model is merged when the preset's table already has that model id. Everything else is listed in
  the unmatched file, never guessed.
- Per model: `interface.<protocol>` — the thinking levels in pi's order (level, the value sent), the
  `compat` fields under Frey's names (FIELDS) and the rest of `compat` as it is (`other`), pi's own window
  and output limit (`context_window`, `max_output`), and `from` (where it came from). Where pi's numbers
  differ from the facts layer's (models.dev), the facts layer's stay and the difference is listed.
- Per preset: `interface_defaults.<protocol>` — the fields every merged model of that preset has with the
  same value: what a model the table does not have yet gets (thinking levels are per model, never a
  default).
- Our own corrections (`configs/models-facts-overrides.toml`, applied by models_facts.py) and the recorded
  quirk table (`configs/models.toml`) are read after this layer by Frey, so they win.
"""

import json
import re
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FREY = os.path.dirname(HERE)
CONFIGS = os.path.join(FREY, "configs")
SOURCES = os.path.join(CONFIGS, "sources")
SNAPSHOT = os.path.join(SOURCES, "pi-ai.json")
UNMATCHED = os.path.join(SOURCES, "pi-ai-unmatched.json")
FACTS = os.path.join(CONFIGS, "models-facts.json")

# pi provider, pi api -> (Frey preset, Frey protocol). Only the pairs where both name the same vendor
# and the same protocol; checked against configs/vendors.toml by `apply`.
PRESETS = {
    ("deepseek", "openai-completions"): ("deepseek", "openai_compat"),
    ("openrouter", "openai-completions"): ("openrouter", "openai_compat"),
    ("anthropic", "anthropic-messages"): ("anthropic", "messages_api"),
    ("openai", "openai-responses"): ("openai", "responses"),
    ("google", "google-generative-ai"): ("gemini", "gemini"),
    ("moonshotai-cn", "openai-completions"): ("moonshot", "openai_compat"),
    ("moonshotai", "openai-completions"): ("moonshot-intl", "openai_compat"),
    ("minimax-cn", "anthropic-messages"): ("minimax", "messages_api"),
    ("minimax", "anthropic-messages"): ("minimax-intl", "messages_api"),
}

# pi's `compat` field -> Frey's name, for the ones Frey reads (T-0173 ④); every other one is kept in
# `other` as pi writes it.
FIELDS = {
    "thinkingFormat": "thinking_format",
    "supportsReasoningEffort": "supports_reasoning_effort",
    "requiresReasoningContentOnAssistantMessages": "reasoning_on_assistant_messages",
    "maxTokensField": "max_tokens_field",
    "supportsDeveloperRole": "supports_developer_role",
    "supportsStrictMode": "supports_strict_mode",
    "sendSessionAffinityHeaders": "session_affinity_headers",
    "sessionAffinityFormat": "session_affinity_format",
    "cacheControlFormat": "cache_control_format",
}

# pi's level names, in its order.
LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "max"]


def snapshot(package):
    data = os.path.join(package, "dist", "providers", "data")
    with open(os.path.join(package, "package.json"), encoding="utf-8") as f:
        meta = json.load(f)
    providers = {}
    for name in sorted(os.listdir(data)):
        if name.endswith(".json"):
            with open(os.path.join(data, name), encoding="utf-8") as f:
                providers[name[:-5]] = json.load(f)
    out = {
        "source": "pi-ai",
        "package": meta["name"],
        "version": meta["version"],
        "license": meta.get("license", ""),
        "upstream": "https://github.com/earendil-works/pi",
        "providers": providers,
        # T-0174: the day it was taken, for the table's date (tools/models_sources.py age).
        "taken": __import__("datetime").date.today().isoformat(),
    }
    os.makedirs(SOURCES, exist_ok=True)
    write_json(SNAPSHOT, out)
    # The npm package carries no LICENSE file; `configs/sources/pi-ai.LICENSE` is the repository's
    # (github.com/earendil-works/pi, MIT, Copyright (c) 2025 Mario Zechner), kept by hand.
    for lic in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        if os.path.exists(os.path.join(package, lic)):
            shutil.copyfile(os.path.join(package, lic), os.path.join(SOURCES, "pi-ai.LICENSE"))
            break
    return out


def write_json(path, value):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1) + "\n")


def load_snapshot(path=SNAPSHOT):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def google_level(model_id):
    """pi-ai 1.5.2 `dist/api/google-shared.js` `usesGoogleThinkingLevel` (lines 37-48): the models that take
    Gemini's `thinkingLevel`; the rest take `thinkingBudget`. Run here, once per model, so the table says
    which one each model takes (T-0164: a row per model, no rule at run time)."""
    i = model_id.lower()
    return bool(re.search(r"gemini-3(?:\.\d+)?-(?:pro|flash)", i) or re.search(r"gemini-(?:[4-9]|[1-9]\d)", i)
                or i in ("gemini-flash-latest", "gemini-flash-lite-latest") or re.search(r"gemma-?4", i))


def format_of(protocol, entry, compat):
    """How the request says the level (T-0164), for the protocols whose form pi does not name in `compat`:
    the Messages API's adaptive effort (`forceAdaptiveThinking`, pi `anthropic-messages.js` 945-951 and
    1184-1189) or a token budget (1191-1196); Responses' `reasoning.effort`; Gemini's level or budget."""
    if protocol == "openai_compat":
        if compat.get("thinkingFormat"):
            return compat["thinkingFormat"]
        return "openai" if compat.get("supportsReasoningEffort") else None
    if protocol == "messages_api":
        return "anthropic_adaptive" if compat.get("forceAdaptiveThinking") else "anthropic_budget"
    if protocol == "responses":
        return "openai_responses"
    if protocol == "gemini":
        return "google_level" if google_level(entry.get("id", "")) else "google_budget"
    return None


def interface_of(entry, version, protocol):
    compat = entry.get("compat") or {}
    out = {}
    levels = entry.get("thinkingLevelMap") or {}
    if entry.get("reasoning") is True:
        # pi's own rule (pi-ai 1.5.2 `dist/models.js` `getSupportedThinkingLevels`, lines 701-712):
        # minimal..high are there unless the map says `null`; xhigh and max only when the map names them.
        # The value sent is the map's string, else the level's own name. `off` is kept apart below.
        out["thinking_levels"] = [
            [lv, levels[lv] if isinstance(levels.get(lv), str) else lv]
            for lv in LEVELS[1:]
            if (lv in levels and levels[lv] is not None) or (lv not in levels and lv not in ("xhigh", "max"))
        ]
        # pi: `off: null` — the model cannot be told not to think; a string — the value that turns it off;
        # absent — pi turns it off its own way (the format's).
        if "off" in levels:
            if levels["off"] is None:
                out["thinking_always_on"] = True
            else:
                out["thinking_off"] = levels["off"]
    for k, v in compat.items():
        if k in FIELDS:
            out[FIELDS[k]] = v
    if entry.get("reasoning") is True and "thinking_format" not in out:
        fmt = format_of(protocol, entry, compat)
        if fmt:
            out["thinking_format"] = fmt
    other = {k: v for k, v in compat.items() if k not in FIELDS}
    if other:
        out["other"] = other
    if isinstance(entry.get("contextWindow"), int):
        out["context_window"] = entry["contextWindow"]
    if isinstance(entry.get("maxTokens"), int):
        out["max_output"] = entry["maxTokens"]
    if isinstance(entry.get("reasoning"), bool):
        out["reasoning"] = entry["reasoning"]
    out["from"] = "pi-ai %s" % version
    return out


def strip(facts):
    for prov in facts["providers"].values():
        prov.pop("interface_defaults", None)
        for m in prov.get("models", {}).values():
            m.pop("interface", None)
            frm = m.get("from")
            if isinstance(frm, dict):
                for k in [k for k in frm if k.startswith("interface")]:
                    frm.pop(k)
                if not frm:
                    m.pop("from", None)


def layer(facts, pi):
    """`facts` (header keys and `providers`, as models_facts.py builds it) with pi's interface layer put
    on (an earlier one replaced); returns it and the unmatched list."""
    facts = json.loads(json.dumps(facts))
    strip(facts)
    version = pi["version"]
    unmatched = {"source": "pi-ai %s" % version, "providers_without_preset": [], "models": [], "differences": []}
    for prov_name, apis in sorted(pi["providers"].items()):
        if prov_name.startswith("."):
            continue  # the package's own manifest, not a provider
        for api, models in sorted(apis.items()):
            if not isinstance(models, dict):
                continue
            target = PRESETS.get((prov_name, api))
            if target is None:
                unmatched["providers_without_preset"].append("%s/%s (%d models)" % (prov_name, api, len(models)))
                continue
            preset, protocol = target
            ours = facts["providers"].get(preset)
            if ours is None:
                unmatched["providers_without_preset"].append("%s/%s: preset %s has no facts" % (prov_name, api, preset))
                continue
            merged = []
            for key in sorted(models):
                entry = models[key]
                mid = entry.get("id")
                fact = ours["models"].get(mid)
                if fact is None:
                    unmatched["models"].append("%s %s (pi %s/%s)" % (preset, mid, prov_name, api))
                    continue
                iface = interface_of(entry, version, protocol)
                fact.setdefault("interface", {})[protocol] = iface
                lim = fact.get("limit") or {}
                for ours_key, theirs_key in (("context", "context_window"), ("output", "max_output")):
                    if theirs_key in iface and lim.get(ours_key) not in (None, iface[theirs_key]):
                        unmatched["differences"].append("%s %s: limit.%s %s (models.dev, kept) / %s %s (pi)" % (preset, mid, ours_key, lim.get(ours_key), theirs_key, iface[theirs_key]))
                merged.append(iface)
            if merged:
                common = {}
                for k, v in merged[0].items():
                    if k in ("thinking_levels", "thinking_off", "thinking_always_on", "context_window", "max_output", "reasoning", "from"):
                        continue
                    if all(m.get(k) == v for m in merged):
                        common[k] = v
                if common:
                    common["from"] = "pi-ai %s (all %d of its %s models)" % (version, len(merged), preset)
                    ours.setdefault("interface_defaults", {})[protocol] = common
    # Still format 1: the new fields are optional (schemas/models/facts-1.schema.json says so); a Frey
    # from before T-0173 refuses a refreshed copy whole and keeps the one it has (AD132's rule).
    facts["interface_source"] = "pi-ai %s (MIT, configs/sources/pi-ai.LICENSE)" % version
    return facts, unmatched


def recorded_conflicts(table, models_toml=os.path.join(CONFIGS, "models.toml")):
    """T-0173 ③: where pi's layer says otherwise than the recorded quirk table (configs/models.toml,
    `verified = "live"`) — the recorded value wins at run time (quirks.rs); listed so a reader sees it."""
    import tomllib
    with open(models_toml, "rb") as f:
        entries = tomllib.load(f).get("model", [])
    out = []
    for e in entries:
        if e.get("verified") != "live":
            continue
        prov = table["providers"].get(e["vendor"], {})
        for mid, fact in sorted(prov.get("models", {}).items()):
            if not any(mid == m or (m.endswith("*") and mid.startswith(m[:-1])) for m in e["models"]):
                continue
            iface = (fact.get("interface") or {}).get(e["protocol"])
            if not iface:
                continue
            pairs = [("context_window", iface.get("context_window")), ("max_output_tokens", iface.get("max_output"))]
            if "reasoning_replay" in e and iface.get("reasoning_on_assistant_messages") is not None:
                pairs.append(("reasoning_replay", "required" if iface["reasoning_on_assistant_messages"] else "optional"))
            for key, theirs in pairs:
                ours = e.get(key)
                if ours is not None and theirs is not None and ours != theirs:
                    out.append("%s %s %s: %s %s (recorded, %s; wins) / %s (pi)" % (e["vendor"], e["protocol"], mid, key, ours, e["name"], theirs))
    return out


def apply(check=False):
    """T-0174: the table also carries the layers of tools/models_sources.py on top of this one; `apply`
    goes through it, so that running this alone never takes them off."""
    import models_sources

    return models_sources.apply(["apply"] + (["--check"] if check else []))


def apply_pi_only(check=False):
    import models_facts
    with open(FACTS, encoding="utf-8") as f:
        before = f.read()
    table, unmatched = layer(json.loads(before), load_snapshot())
    unmatched["recorded_conflicts"] = recorded_conflicts(table)
    out = models_facts.render({k: v for k, v in table.items() if k != "providers"}, table["providers"])
    un = json.dumps(unmatched, ensure_ascii=False, sort_keys=True, indent=1) + "\n"
    if check:
        cur_un = open(UNMATCHED, encoding="utf-8").read() if os.path.exists(UNMATCHED) else ""
        if out != before or un != cur_un:
            print("models_pi: configs/models-facts.json or configs/sources/pi-ai-unmatched.json would change", file=sys.stderr)
            return 1
        print("models_pi: OK (current)")
        return 0
    with open(FACTS, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    with open(UNMATCHED, "w", encoding="utf-8", newline="\n") as f:
        f.write(un)
    n = sum(1 for p in table["providers"].values() for m in p.get("models", {}).values() if "interface" in m)
    print("models_pi: %d models have pi's interface layer; %d pi models and %d pi providers unmatched; %d differences with models.dev and %d with the recorded table listed"
          % (n, len(unmatched["models"]), len(unmatched["providers_without_preset"]), len(unmatched["differences"]), len(unmatched["recorded_conflicts"])))
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "snapshot":
        out = snapshot(argv[1])
        print("models_pi: snapshot of %s %s" % (out["package"], out["version"]))
        return 0
    if argv and argv[0] == "apply":
        return apply(check="--check" in argv)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
