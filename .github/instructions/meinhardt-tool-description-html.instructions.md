---
applyTo: "MeinhardtTabTools.html"
description: "Use when editing the main Meinhardt tool-description page so tool cards, screenshots, captions, and layout stay consistent with the MHTTools documentation standard."
---
Follow docs/MHTTools-Tool-Description-Standard.md as the source of truth for tool-description structure.

Key rules:
- Keep the current card-based layout language: section.panel, article.tool, tool-head, panel-intro, and the existing screenshot wrappers.
- Every tool with a real UI must include an actual UI screenshot.
- Use the existing screenshot display protocol instead of ad hoc image styling:
  - shot-ui for compact dialogs/forms
  - filename containing LargeUI for large full-width interfaces
  - steps-layout for multi-step workflows
  - tool-split for copy + screenshot side-by-side layouts
  - panel-shot or shot-panel-ribbon for ribbon/panel images
- Captions must describe what the screenshot proves, not repeat the tool name.
- Preserve the blue-led Meinhardt theme and its accent variety; do not flatten the page into a monochrome redesign.
- If a tool’s UI does not fit an existing pattern, extend the standard deliberately and document the new pattern in docs/MHTTools-Tool-Description-Standard.md.
