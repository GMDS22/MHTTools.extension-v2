---
description: "Use when syncing tool metadata between ribbon bundles, MeinhardtTabTools.html, and metadata snippets so documentation and actual tools stay aligned."
applyTo: "MeinhardtTabTools.html,docs/all-tools-metadata-snippet.html,MEINHARDT.tab/**/bundle.yaml"
---
# MHTTools Metadata Sync Rules

Always load these references:
- MeinhardtTabTools.html
- docs/all-tools-metadata-snippet.html
- docs/MHTTools-Tool-Description-Standard.md
- docs/MHTTools-UI-Screenshot-Audit.md

## Sync Rules
- Keep tool names, panel placement, and descriptions aligned with bundle.yaml sources.
- Keep HTML cards aligned with real tool availability and current behavior.
- Keep screenshot references accurate and point to existing files.
- Update metadata snippets when adding, renaming, or deprecating tools.

## Consistency Rules
- Avoid duplicate cards for the same tool.
- Preserve existing HTML card structure and class naming.
- Ensure captions describe what the image proves, not only the tool name.

## Validation
- Confirm each referenced tool path exists.
- Confirm each referenced screenshot file exists.
- Confirm no broken references after renames.
