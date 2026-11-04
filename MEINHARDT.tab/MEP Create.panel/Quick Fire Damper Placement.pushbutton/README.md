# Quick Fire / Smoke Damper Placement

Places a selected duct-accessory family at actual duct crossings with explicitly rated walls in the active view.

## Configuration
- `NWB_Material` / `NWB_MATERIAL` is read from the wall instance and then its type. Only explicit fire, smoke, or FRL classifications are included; ambiguous and explicitly non-rated values are excluded.
- Select one loaded duct accessory or mechanical family symbol.
- Detected wall families and types are shown in a read-only inventory; all listed candidates are included automatically.
- Damper family and symbol selections are remembered per open Revit project.

## Behavior
- Host walls and visible linked walls are collected from the active view; linked geometry is transformed into host coordinates.
- Placement checks duct-curve/ wall-solid intersections directly.
- Placement runs in transactions of up to ten ducts. Cancellation keeps completed batches.
- Existing instances of the selected symbol within 50 mm in the active view prevent duplicate placement.

## Safety
- This tool only places the selected family; it does not determine legal damper requirements.
- Verify the selected family category and physical placement behavior before production use.
- Linked models are never modified.
