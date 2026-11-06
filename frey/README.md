# frey/ — Frey's part of this fork

This fork of [models.dev](https://github.com/anomalyco/models.dev) (MIT) is where Frey's model facts are
reviewed before any client uses them for prices (AD132 ⑤). Upstream's files are never edited here.

| File | What |
|---|---|
| `models_facts.py` | The generator: models.dev's TOML → Frey's facts table (the same file as Frey's `src/frey/tools/models_facts.py`) |
| `vendors.toml` | Frey's presets and the models.dev provider each maps to (the same file as Frey's `src/frey/configs/vendors.toml`) |
| `facts-1.schema.json` | The table's schema (the same file as Frey's `src/frey/schemas/models/facts-1.schema.json`) |
| `overrides/models-facts-overrides.toml` | Our corrections over models.dev's data |
| `facts_report.py`, `test_facts_report.py` | What a sync changes: prices moved by more than 30 %, models removed, new models; the schema |
| `sync.sh` | The weekly sync, run by `.github/workflows/frey-sync.yml` (or by hand: `git remote add upstream …; git switch -c frey-sync/x; bash frey/sync.sh /tmp/sync`) |

`dev` is the reviewed branch: the sync opens a pull request into it; a person reads the report and merges.
`lannerk/agent-catalog` builds `catalog/models-facts.json` from `dev` every week. The skeleton of this
directory is in Frey's own repository (`ops/release/models.dev/`): change it there, then push here.
