# Reference evidence

This directory stores manifests and a small set of curated evidence used to formulate MSA research questions.

## What belongs in Git

- references/screenshot_manifest.csv;
- selected, reviewable files under references/screenshots_curated/;
- documentation needed to understand provenance and limitations.

## What stays external

Large raw screenshot collections must not enter Git. Store them under MSA_DATA/reference_screenshots_raw/ or an equivalent local data directory and record their local source path in the manifest without assuming that path is portable.

## Evidence handling

Do not infer private source code, no-repaint behavior, ConfirmTime, or verified effectiveness from a screenshot. Remove secrets and personal information before curating any image.
