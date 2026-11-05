# Quick Fire / Smoke Damper Placement

Places a selected Duct Accessory type at actual crossings between selected duct curves and explicitly fire- or smoke-rated walls in the active view.

## Workflow
- Preselect duct curves before running the command. If the preselection has no duct curves, pick duct curves in the active view.
- Choose a loaded Duct Accessory family type, then enter the duplicate spacing in millimeters (default 200 mm).
- Only the selected ducts are checked. Nearby host walls are filtered by each duct's bounding box; loaded, visible linked walls are queried in link coordinates and their solids are transformed into host coordinates for intersection checks.
- `NWB_Material` / `NWB_MATERIAL` is read from the wall instance, falling back to its type. Only explicit fire, smoke, or FRL classifications are included; ambiguous and explicitly non-rated values are excluded.
- All duct/wall geometry checks complete before any transaction starts. Each duct with placements gets one short rollback-safe transaction; a failed duct is reported and does not prevent later ducts from being attempted.
- Existing instances of the selected type hosted on the same duct within the configured 3D radius prevent duplicate placement.

## Safety
- The tool only places the selected family; it does not determine legal damper requirements.
- Verify the selected family's hosting and physical placement behavior before production use.
- Linked models are read for wall geometry and are never modified.
- UI prompts and geometry scanning run outside transactions. The active project and view are checked again before each duct transaction commits.
