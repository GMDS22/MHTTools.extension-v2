---
description: "Use when creating or updating pyRevit tools under MEINHARDT.tab so folder structure, script patterns, bundle metadata, and reusable library usage stay consistent."
applyTo: "MEINHARDT.tab/**/*.py,MEINHARDT.tab/**/*.xaml,MEINHARDT.tab/**/bundle.yaml"
---
# pyRevit Tool Development Rules

Use these references before changing tool implementation:
- README.md
- docs/theme-system.md
- FamilyNamingConvention.md
- /memories/repo/pyrevit-wpf-safety.md
- Existing mature examples under MEINHARDT.tab (for example ElementChangeLevel.pushbutton and RoomToSpace.pushbutton)

## Structure
- Keep each tool self-contained in its own *.pushbutton folder.
- Keep script.py as the entry point.
- Keep bundle.yaml accurate for title, tooltip, author, and ordering expectations.
- Keep icon.png and icon.dark.png consistent with existing dimensions and style.

## Coding Rules
- Prefer reusable helpers from lib/pyrevitmep and lib/materialsdb before adding one-off logic.
- Keep UI text clear and task-oriented (what users should do in each step).
- Preserve existing public behavior unless the task explicitly asks for workflow changes.
- Prefer incremental updates over full rewrites for existing tools.

## Validation
- Preserve event bindings between XAML controls and Python handlers.
- Validate changed Python files for syntax and basic runtime safety.
- For multi-step tools, ensure each step has clear scope and no conflicting controls.
