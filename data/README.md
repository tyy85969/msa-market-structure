# Data policy

The repository does not store private or large raw market datasets.

- raw/ is for local source data and is ignored except for its placeholder.
- processed/ is for reproducible derived data and is ignored except for its placeholder.
- synthetic/ is for small deterministic fixtures suitable for tests and version control when explicitly added.

Every formal dataset must document symbol, provider or provenance, time range, timezone, schema, transformations, and the Development / Validation / Out-of-Sample split. Secrets and API keys belong in local environment configuration and must never be committed.
