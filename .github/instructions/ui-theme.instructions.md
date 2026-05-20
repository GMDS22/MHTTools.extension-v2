---
description: "Apply Meinhardt UI theme rules when editing tool interfaces, XAML styles, visual tokens, and related UI copy."
applyTo: "MEINHARDT.tab/**/*.xaml,MEINHARDT.tab/**/*.py,docs/theme-system.md,README.md"
---
# Meinhardt UI Theme Rules

Use docs/theme-system.md as the single source of truth for theme tokens and usage rules.

## Core Rules
- Keep a 3-color role system:
  - Primary: Blue
  - Secondary: Teal
  - Accent: Amber
- Prefer tokenized colors and shared style keys over hardcoded per-control values.
- Preserve behavior and event wiring when adjusting UI visuals.
- Improve hierarchy and readability: spacing, contrast, panel structure, and action emphasis.
- Avoid monochromatic-only styling.

## Editing Expectations
- When touching XAML, align controls to shared style patterns (buttons, cards, list rows, labels, hints).
- When touching Python UI text, align labels/tooltips with current theme terminology and clarity.
- Update docs/theme-system.md first when introducing visual changes, then propagate.
- In README.md, reference docs/theme-system.md rather than duplicating token tables.

## Validation Checklist
- Theme still uses only the documented 3 role colors for core identity.
- Contrast and readability improved over prior version.
- Similar UI sections across tools look consistent.
- No broken event handlers or renamed control mismatches.
