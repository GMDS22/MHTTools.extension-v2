# Quick Fire / Smoke Damper Placement

Places a selected duct-accessory family at actual duct crossings with explicitly rated walls in the active view.

## Configuration
- `NWB_Material` / `NWB_MATERIAL` is read from the wall instance and then its type. Only explicit fire, smoke, or FRL classifications are included; ambiguous and explicitly non-rated values are excluded.
- Select one loaded duct accessory or mechanical family symbol.
- Preselect duct curves before launching the tool; those IDs are captured before its window opens. Or use **Pick duct targets** to replace the target set. Canceling the picker keeps the previous target set. Placement is disabled until at least one active-view duct is targeted.
- Only the selected duct targets are checked for intersections and processed. A changed active view or missing selected duct stops the run instead of widening its scope.
- Detected wall families and types are shown in a read-only inventory; all listed candidates are included automatically.
- Damper family and symbol selections are remembered per open Revit project.

## Behavior
- Host walls and visible linked walls are collected from the active view. Linked wall bounds are transformed to host coordinates and checked against the active crop when enabled.
- Placement checks duct-curve/ wall-solid intersections directly.
- Only IDs and numeric coordinates persist between ExternalEvent callbacks. Wall intersections are checked in chunks of ten wall records; walls and geometry are reacquired within each callback. One short transaction is used per selected duct after intersection checks, so Cancel between callbacks keeps completed placements.
- A Revit-process mutex prevents a second Quick Fire Damper window from running concurrently.
- Only existing instances of the selected symbol at the same target crossing (5 mm tolerance) prevent duplicate placement.
- When enabled, the isolation option temporarily isolates placed dampers, their host ducts, and intersecting host walls in the host model. Linked walls remain visible.

## Safety
- This tool only places the selected family; it does not determine legal damper requirements.
- Verify the selected family category and physical placement behavior before production use.
- Linked models are never modified.
