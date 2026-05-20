---
description: "Update Meinhardt UI theme tokens from docs/theme-system.md and propagate them across selected tools."
mode: "agent"
tools: [read, search, edit, todo]
argument-hint: "Scope (all tools / panel / file glob), token changes, and rollout mode"
---
Update Meinhardt UI theme tokens and propagate safely.

Inputs:
- Scope: ${input:scope:all MEINHARDT.tab tools}
- Token changes: ${input:changes:Primary Blue #0E639C; Secondary Teal #1FA6A6; Accent Amber #F2B134}
- Rollout mode: ${input:mode:docs-first then code propagation}

Workflow:
1. Open docs/theme-system.md and apply token updates there first.
2. Find affected XAML and UI-related Python files inside ${input:scope}.
3. Replace hardcoded values with token-aligned values/styles where practical.
4. Keep behavior unchanged; only update visual/theme concerns.
5. Summarize:
   - files changed
   - tokens updated
   - any remaining outliers requiring manual follow-up

Constraints:
- Do not invent a new color role beyond the 3 role system unless explicitly requested.
- Do not duplicate full token tables into README.md; link to docs/theme-system.md.
