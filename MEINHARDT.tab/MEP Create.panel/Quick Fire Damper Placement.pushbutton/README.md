# Quick Fire / Smoke Damper Placement

Places a selected Duct Accessory type at actual crossings between selected duct curves and explicitly fire- or smoke-rated walls in the active view.

## Workflow
- Preselect duct curves before running the command. If the preselection has no duct curves, pick duct curves in the active view.
- Choose a loaded Duct Accessory family type, then enter the duplicate spacing in millimeters (default 200 mm) and choose rated-wall-only or force placement at every actual wall crossing.
- Only the selected ducts are checked. Nearby host walls are filtered by each duct's bounding box; loaded, visible linked walls are queried in link coordinates and their solids are transformed into host coordinates for intersection checks.
- Rated-only mode classifies host and linked walls using their type name, structural material, and instance/type `NWB_Material` / `NWB_MATERIAL` values. Explicit fire, smoke, F/FR/FRL/FRR, and recognized fire-resistance standards qualify; ambiguous and explicitly non-rated values are excluded. Force mode bypasses this classification only and still requires a real duct-curve/wall-solid crossing.
- Connected duct elbows are identified through duct connector references and the fitting `PartType`. The tool first searches the actual wall-intersection curve for a point at least 300 mm from every connected elbow. If none fits, it searches the same duct curve only in directions moving away from all connected elbows, and no farther than 300 mm beyond the wall intersection. Adjusted placements are retained only when the created family's host-coordinate bounding box overlaps the host-coordinate wall bounds (including all eight transformed corners for linked walls); otherwise the candidate is rolled back and another is tried, or the crossing is skipped and reported.
- After creation, the tool retains Revit's host orientation. It does not rotate a hosted inline accessory based only on connector-axis alignment: family-specific roll data is unavailable, and an arbitrary rotation can disconnect the family or give a non-square damper the wrong roll. Verify non-square family orientation in Revit.
- All duct/wall geometry checks complete before any transaction starts. Each duct with placements gets one short rollback-safe transaction with a subtransaction per crossing candidate; failed candidates are confirmed rolled back before retry, and a failed duct is reported without preventing later ducts from being attempted.
- The tool reports placement only after the outer duct transaction returns `Committed` and a persistence check after the verification prompt reacquires each created ID as a valid Duct Accessory hosted on or physically connected to the intended duct. Those instances are selected before the result summary. After that summary is dismissed, the tool reacquires every committed ID again, logs its exact status in the pyRevit output, and alerts if its state changed.
- Existing instances of the selected type hosted on the same duct within the configured 3D radius prevent duplicate placement.

## Safety
- The tool only places the selected family; it does not determine legal damper requirements.
- Verify the selected family's hosting and physical placement behavior before production use.
- Linked models are read for wall geometry and are never modified.
- UI prompts and geometry scanning run outside transactions. The active project and view are checked again before each duct transaction commits.
