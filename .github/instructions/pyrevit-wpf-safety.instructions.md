---
description: "Use when editing pyRevit WPF/XAML and related UI Python handlers to prevent crashes, stale window state, unsafe selection flows, and transaction misuse."
applyTo: "MEINHARDT.tab/**/*.xaml,MEINHARDT.tab/**/*.py"
---
# pyRevit WPF Safety Rules

Always load these references first:
- /memories/repo/pyrevit-wpf-safety.md
- docs/theme-system.md
- Relevant tool-local safety notes (for example SAFE_USAGE.md or CRASH_FIXES.md if present)

## Safety Rules
- Wrap WPF window creation and show logic in defensive try/except with user-visible alerts.
- Avoid stale global/modeless window references when reopening tools.
- Use modal flow by default unless an external-event pattern is explicitly required.
- Hide/restore windows correctly around PickObject/PickObjects operations.
- Do not mix unsafe modeless UI callbacks with direct model transactions.
- Keep selection filtering constrained to active context where required.

## Transaction Rules
- Keep transactions short and deterministic.
- Use rollback-safe patterns for cross-document or multi-step operations.
- Do not hold transactions open during user selection prompts.

## Validation
- Ensure XAML control names still match Python references.
- Ensure control state transitions (enabled/visible) never orphan required inputs.
- Ensure error messages are actionable and non-technical for users.
