# Quick Fire / Smoke Damper Placement

Places a selected Duct Accessory type at actual crossings between selected duct curves and explicitly fire- or smoke-rated walls in the active view.

## Workflow
- Preselect duct curves before running the command. If the preselection has no duct curves, pick duct curves in the active view.
- Choose a loaded Duct Accessory family type, then enter the duplicate spacing in millimeters (default 200 mm) and choose rated-wall-only or force placement at every actual wall crossing.
- Only the selected ducts are checked. Nearby host walls are filtered by each duct's bounding box; loaded, visible linked walls are queried in link coordinates and their solids are transformed into host coordinates for intersection checks.
- Rated-only mode classifies host and linked walls using their type name, structural material, and instance/type `NWB_Material` / `NWB_MATERIAL` values. Explicit fire, smoke, F/FR/FRL/FRR, and recognized fire-resistance standards qualify; ambiguous and explicitly non-rated values are excluded. Force mode bypasses this classification only and still requires a real duct-curve/wall-solid crossing.
- Connected duct elbows are identified through duct connector references and the fitting `PartType`. Crossings within 300 mm of the connected elbow connector are moved along the same wall-solid intersection curve when a clear point exists; otherwise that crossing is skipped and reported.
- All duct/wall geometry checks complete before any transaction starts. Each duct with placements gets one short rollback-safe transaction; a failed duct is reported and does not prevent later ducts from being attempted.
- Existing instances of the selected type hosted on the same duct within the configured 3D radius prevent duplicate placement.

## Safety
- The tool only places the selected family; it does not determine legal damper requirements.
- Verify the selected family's hosting and physical placement behavior before production use.
- Linked models are read for wall geometry and are never modified.
- UI prompts and geometry scanning run outside transactions. The active project and view are checked again before each duct transaction commits.
