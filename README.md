# MHTTools pyRevit Extension

Adds a **MEINHARDT** tab to pyRevit with **10 panels** — Project, Sheets & Views, MEP Create, MEP Modify, MEP Data, MEP Manage, Audit & Exchange, Documentation, Search, and Refresh — covering spatial creation, sheet production, MEP modelling, data management, and model QA workflows.

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

## Agent Ecosystem

The repository includes specialized custom agents in [.github/agents](.github/agents) for fast and consistent tool development.

- Core tool implementation: pyRevit Tool Developer
- WPF safety hardening: pyRevit WPF Safety Auditor
- Cross-tool theme modernization: Meinhardt UI Theme Unifier
- UI audit/review: Meinhardt UI QA
- Tool description/content updates: MHTTools Tool Description Curator
- Screenshot orchestration: MHTTools Screenshot Capture Conductor
- Metadata synchronization: MHTTools Tool Metadata Registry
- Shared library refactors: pyRevit Library Refactor Assistant

Routing and invocation guidance is defined in [.github/copilot-instructions.md](.github/copilot-instructions.md).
