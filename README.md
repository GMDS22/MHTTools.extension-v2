# MHTTools pyRevit Extension

Adds an **MHT Tools** tab to pyRevit with the **Project** panel tools copied from GMToolbox.

## Install (teammates)

Option A — Copy folder (simplest):

1. Close Revit.
2. Copy the folder `MHTTools.extension` into:
   - `%APPDATA%\pyRevit\Extensions\`
   - Example: `C:\Users\<you>\AppData\Roaming\pyRevit\Extensions\MHTTools.extension`
3. Re-open Revit (or run pyRevit Reload).

Option B — Git (recommended for updates):

1. Put `MHTTools.extension` in a Git repo.
2. Teammates clone it into `%APPDATA%\pyRevit\Extensions\`.
3. Updates = `git pull`.

## Notes

- Icons are original (simple geometric glyphs) using the MHT-style blue + teal + amber system.
- If Revit/pyRevit caches ribbon/availability metadata and a button misbehaves after an update, run **pyRevit Reload** or restart Revit.

## UI Theme System

- Single source of truth: [docs/theme-system.md](docs/theme-system.md)
- Use this document for palette tokens, role usage, and rollout rules before changing tool UI styles.
