# MHTTools Agent Router

Use this routing table to choose the primary agent for each request.

## Primary Routing
- Create a new pyRevit tool or update tool workflow/UI logic under MEINHARDT.tab -> pyRevit Tool Developer
- Audit or harden WPF safety, selection flow, or transaction safety -> pyRevit WPF Safety Auditor
- Unify theme across tools or propagate visual tokens -> Meinhardt UI Theme Unifier
- Audit UI quality and compliance only (no edits preferred) -> Meinhardt UI QA
- Update MeinhardtTabTools.html cards, captions, or description structure -> MHTTools Tool Description Curator
- Capture/refresh screenshot assets and close coverage gaps -> MHTTools Screenshot Capture Conductor
- Sync tool metadata/cards/snippets with bundle.yaml sources -> MHTTools Tool Metadata Registry
- Refactor shared libraries in lib/ and update dependent callsites -> pyRevit Library Refactor Assistant

## Suggested Handoffs
- pyRevit Tool Developer -> pyRevit WPF Safety Auditor for safety-critical window/selection changes
- pyRevit Tool Developer -> MHTTools Tool Description Curator when tool docs/screenshots must be updated
- MHTTools Tool Description Curator -> MHTTools Screenshot Capture Conductor for missing UI captures
- MHTTools Tool Description Curator -> MHTTools Tool Metadata Registry for large metadata alignment changes
- Meinhardt UI Theme Unifier -> Meinhardt UI QA for audit pass before finalizing broad theme updates

## Invocation Examples
- "Use pyRevit Tool Developer to scaffold a new pushbutton under MEP Data.panel"
- "Use pyRevit WPF Safety Auditor to review this selection workflow"
- "Use MHTTools Screenshot Capture Conductor to close screenshot gaps from the audit doc"
- "Use MHTTools Tool Metadata Registry to sync HTML cards with new bundle entries"

## Operating Policy
- Keep one primary writer agent per file family at a time.
- Use supporting/auditor agents for review or focused follow-up patches.
- Follow strict always-load references defined inside each agent.
