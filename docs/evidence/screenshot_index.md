# Screenshot Index

## Purpose

This index organizes curated reference evidence without treating screenshots as algorithmic proof. Each image must have a row in references/screenshot_manifest.csv and a stable ID.

## Sequence groups

| Group | Intended use | Required caution |
|---|---|---|
| A | Establish a baseline visual state | Do not infer earlier or later behavior |
| B | Compare apparent consecutive states | Sequence order and interval must be verified |
| C | Compare zoom or viewport changes | Screen scale can change apparent line length and density |
| D | Compare timeframe views | Label and timeframe semantics must be independently verified |
| E | Compare display-module toggle states | Visibility changes do not prove generation logic |

Images in the same group may represent:

- the same market over consecutive time;
- different zoom levels;
- different timeframes;
- different display-module switch states.

The manifest must state which relationship is known, inferred, or unknown. Do not assign a chronological order from filenames alone.

## Storage policy

Only selected evidence may enter Git under references/screenshots_curated/. Large raw screenshot collections must remain external, preferably under MSA_DATA/reference_screenshots_raw/ or an equivalent local data directory.

Curated files must avoid secrets and personal information. Their source path, curated path, description, and evidence value belong in the manifest.

## Evidence limitation

Screenshots can document what was visible in one captured state. They cannot prove no-repaint behavior, ConfirmTime, algorithm identity, or performance. All interpretations require later timestamped data experiments.
