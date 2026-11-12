# OpenRouter's models list — terms of use (read 2026-11-12, T-0174)

Source of `openrouter.json`: `GET https://openrouter.ai/api/v1/models` — OpenRouter's public API, no key.
Frey keeps only, per model id: the window, the output limit, `reasoning` (`supported_efforts`,
`default_effort`, `mandatory`, `default_enabled`), `supported_parameters` and `expiration_date`.

What OpenRouter's Terms of Service (https://openrouter.ai/terms, "Last Updated: August 31, 2026") say
that bears on this, in our words:

- **§7 Prohibited Conduct, item 5**: automated means (crawlers, scripts) may not be used to scrape or
  copy information on the Site or the Services; **item 6**: technical measures against that may not be
  bypassed. We call the documented API endpoint once a week (no scraping of pages, no measure bypassed).
- **§12 Ownership; Proprietary Rights**: the "Materials" (including compilation, information and data)
  are OpenRouter's; except as expressly authorized, they may not be used. The terms name no licence to
  republish the models list.
- The terms do not mention `/api/v1/models` or model metadata by name.

**Open question for the requester (not decided by the developer seat):** whether the thinking levels
taken from this list may ship inside Frey's table and the catalog repository. Until it is decided the
layer is built and listed with its source, and `tools/models_sources.py apply --without openrouter`
builds the table without it (one flag, nothing else changes).
