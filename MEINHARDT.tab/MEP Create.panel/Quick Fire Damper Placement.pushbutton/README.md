# Quick Fire / Smoke Damper Placement

Places a selected duct-accessory family at actual duct crossings with explicitly rated walls in the active view.

## Configuration
- `NWB_Material` / `NWB_MATERIAL` is read from the wall instance and then its type. Only explicit fire, smoke, or FRL classifications are included; ambiguous and explicitly non-rated values are excluded.
- Select one loaded duct accessory or mechanical family symbol.
- Select one or more duct targets in Revit before opening the tool, or use **Pick duct targets**. Placement is disabled until at least one active-view duct is targeted.
- Only the selected duct targets are checked for intersections and processed. A changed active view or missing selected duct stops the run instead of widening its scope.
- Detected wall families and types are shown in a read-only inventory; all listed candidates are included automatically.
- Damper family and symbol selections are remembered per open Revit project.

## Behavior
- Host walls and visible linked walls are collected from the active view; linked geometry is transformed into host coordinates.
- Placement checks duct-curve/ wall-solid intersections directly.
- Each selected duct is processed in its own committed transaction. Cancel is handled between ducts and keeps completed placements.
- Existing instances of the selected symbol within 50 mm in the active view prevent duplicate placement.
- When enabled, the isolation option temporarily isolates placed dampers, their host ducts, and intersecting host walls after processing.

## Safety
- This tool only places the selected family; it does not determine legal damper requirements.
- Verify the selected family category and physical placement behavior before production use.
- Linked models are never modified.
