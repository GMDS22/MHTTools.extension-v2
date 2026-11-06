# NWB AutoFill Update Record

## Purpose

This file records the requested NWB AutoFill changes and the validation plan so future maintainers can understand why the tools behave this way. It is an implementation record, not a replacement for the NWB workbook specification.

## Conversation and requirements recorded

The user asked for improvements to the NWB parameter and dimension AutoFill tools:

1. Provide an asset-authoring discipline input in the parameter tool's Project Information area. Use the user's selection for `NWB_Discipline`; do not infer the authoring team from asset type. If no discipline is supplied, make the required action clear rather than silently writing an inferred discipline.
2. Expose manual overrides for all NWB parameters handled by Parameter AutoFill. A nonblank override takes precedence; a blank override uses the existing automatic mapping.
3. Allow users to choose which NWB parameters are updated. Selecting only one parameter (for example `NWB_Discipline`) should not write other parameters and should avoid calculations unrelated to the selected targets. Default behavior should remain compatible by selecting all targets initially.
4. Improve dimension writes in Dimension AutoFill based on the workbook's definitions: values are millimetres; height is vertical; width is the least relevant body dimension; length is horizontal start-to-end length. Avoid guessing fitting body dimensions from unrelated or unequal connector sizes.
5. Preserve actionable audit/log information so users can identify override, automatic, and unresolved values.
6. Do not write invalid placeholder prose into an NWB parameter. For missing discipline, leave the target untouched and clearly instruct the user to enter a valid discipline in the tool UI.

## Workbook facts reviewed

Workbook: `NWB-WAL-GEN-DE-REG-0003.xlsx`.

- `Model Data Spec` defines `NWB_Discipline` as the discipline of the team that created the asset and marks it mandatory.
- `Disciplines` supplies the allowed codes and descriptions.
- `Asset Master` describes asset classes; that value is not proof of which team authored an individual model element.
- `NWB_DimDiameter`, `NWB_DimHeight`, `NWB_DimLength`, and `NWB_DimWidth` are specified in millimetres.
- Width is defined as the lesser relevant body dimension; height is vertical; length is horizontal from asset start to end.
- The workbook contains a spelling mismatch for ICT: Asset Master uses `ICT Communications Technology`, whereas the Disciplines sheet has `ICT Communcations Technology`. Any description-based matching must normalize/reconcile this or use the discipline code.

## Existing implementation facts reviewed

- Parameter AutoFill has 22 target parameters and currently derives all targets for each processed element before looping through all 22 write attempts.
- The existing setup UI has detected project information and only a few contextual manual overrides (site, building, WBS01, design package, building permit package).
- Discipline derivation currently prefers the matched Asset Master discipline, then an existing element value, heuristics, and ultimately a `ME` fallback. The tool has no input identifying the authoring team.
- Dimension AutoFill previously parsed text size strings by choosing the largest-area rectangular connector pair, used the first available diameter marker, and read numeric dimension parameters by extracting the first number from formatted text. This can both select the wrong fitting dimension and fail to convert document units to the workbook's millimetres.
- Historical audit rows showed examples of unequal connector sizes and a rectangular duct fitting size `1800x200-...` resulting in width `1800`, demonstrating that automatic connector-size guessing is not reliable for every fitting.

## Implementation decisions

- Use a workbook-backed discipline code choice in the Parameter AutoFill modal UI. It is a run input in the tool's Project Information section; it does not silently edit Revit's Project Information element.
- A missing discipline is unresolved: skip only that target, make the required UI input visible/actionable, and report it in logs/audit. Never store explanatory prose in `NWB_Discipline`.
- Add direct, optional override inputs for every target. Nonblank values override automatic calculation; blank values use the existing derivation. Validate constrained/code fields before opening a transaction. Overrides only apply to checked target parameters.
- Add per-parameter selection with select-all/select-none behavior. All parameters are checked by default. Only checked targets may be calculated where dependencies permit, written, counted, or audited as target writes. Derived prerequisites are allowed only where required by a selected target.
- Preserve existing chunked transactions and complete all prompts before transaction processing. Do not perform UI interaction while a Revit transaction is open.
- For dimensions, use numeric Revit parameter values and Revit unit conversion to millimetres when a reliable length source exists. Prefer explicit semantic dimension parameters. For fitting cases where body dimension/length or the correct run/branch diameter cannot be determined unambiguously, skip that target and explain the reason rather than writing a plausible but unverified connector value.

## Detailed implementation and validation checklist

### A. Parameter AutoFill behavior

- [x] Populate the discipline selector from the active NWB workbook's `Disciplines` table; display code and description, write the code.
- [x] Confirm every workbook discipline code is present exactly once and that the ICT spelling mismatch cannot prevent selecting/writing `IC`.
- [x] Ensure a missing discipline never falls back to Asset Master, heuristics, existing value, or `ME` for the target being written.
- [x] Ensure missing discipline skips `NWB_Discipline`, leaves its current model value unchanged, and reports the missing UI input clearly.
- [x] Add an optional manual override for every item in `TARGET_PARAMETERS`; blank means automatic value. `NWB_Discipline` uses the workbook-backed discipline selector.
- [x] Validate nonblank WBS and package overrides against workbook lists; keep general-text overrides as explicit user text.
- [x] Define and test precedence: per-target manual override, then discipline UI choice for `NWB_Discipline`, then automatic mapping where supported.
- [x] Verify manual overrides are only collected for checked targets and do not write unchecked parameters.
- [x] Warn that a nonblank literal override applies to every processed element for its checked parameter.
- [ ] Confirm the existing write-mode, worksharing, schedule/model view, link selection, audit, and cancellation behavior in Revit.

### B. Selective target execution

- [x] Add one checked control per target plus Select All and Select None actions; initialize all checked.
- [x] Reject a run with no checked targets before any transaction starts.
- [x] Ensure the update loop only submits checked targets to `_set_if_needed`.
- [x] Make target calculation demand-driven: discipline/system-only runs avoid asset matching and linked-room work; room-only runs avoid asset/WBS analysis; selected prerequisites are derived only when required.
- [x] Implement/document dependency closure. For example, `NWB_WBSCode` depends on its WBS components; prerequisites are not written unless selected.
- [x] Make logs, summary, and audit identify checked targets; unselected targets are not submitted as writes or counted as failures/skips.
- [ ] Confirm all-selected behavior matches the previous full-run outputs except for the explicitly corrected discipline rule.

### C. Dimension AutoFill behavior

- [x] Convert numeric length parameters from Revit internal units to millimetres using unit-aware Revit API methods; do not assume formatted `AsValueString()` numerals are millimetres.
- [x] Exercise explicit metric/imperial text and both `UnitTypeId` and legacy `DisplayUnitType` conversion paths with focused helper tests. Live API-version compatibility still requires Revit smoke testing.
- [x] Prefer explicit width, height, diameter, and length parameter sources; distinguish instance from type and log the source selected.
- [x] For rectangular fittings, use explicit body-width and vertical body-height parameters only; ambiguous connector size text is left unresolved.
- [x] For circular fittings with unequal connector diameters, leave diameter unresolved unless an explicit body/run diameter parameter exists; connector sizes are never reduced to a largest-port guess.
- [x] For fitting length, leave the target unresolved because no verified horizontal start-to-end source is established.
- [x] Use converted numeric length parameters or explicitly unit-qualified size text for non-fitting elements; unitless size strings are not assumed to be millimetres.
- [x] Run focused pure-helper checks for rectangular parsing, ambiguous duct/pipe fitting skips, metric/imperial conversion, unitless/invalid data, and source-unit API fallbacks.

### D. UI, API safety, and regression validation

- [x] Parse all changed Python scripts for syntax.
- [x] Parse changed XAML as XML; compare `RunSetupWindow` control references with XAML names and validate event-handler wiring.
- [ ] Check the project information selector and override/target controls remain readable in Revit and scroll safely at typical window sizes.
- [x] Confirm by code path that setup is modal and completes before Revit transactions begin.
- [ ] Verify Revit write/cancellation/rollback behavior in an in-Revit run.
- [x] Run focused pure-helper checks for workbook discipline mapping, override validation/precedence, selective dependency closure, dimensions, and unit conversion.
- [x] Verify audit/log code includes selected targets, override source, unresolved discipline reasons, dimension source, millimetre unit, and skip reasons. A generated Revit audit file remains to be smoke-tested.
- [x] Check `git diff --check` and inspect the final changed-file list; do not stage logs, caches, workbooks' temporary lock files, or unrelated NWB work.
- [ ] Perform an in-Revit smoke test on a disposable/test model: discipline selection, one-target run, all-target run, override run, missing-discipline run, metric and imperial fitting samples, and transaction/cancel behavior.

## Validation status

Implementation is complete. Focused Python helper checks passed, the workbook has 11 unique discipline codes (including `IC`), Python syntax and XAML/control bindings passed, and `git diff --check` passed. Revit is not available in this environment, so visual UI review, live Revit API-version checks, model writes, audit-file review, and transaction/cancel smoke tests remain outstanding.
