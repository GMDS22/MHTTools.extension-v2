# Quick Fire / Smoke Damper Placement

Places a selected duct-accessory family at actual duct crossings with selected rated wall types visible or used in the active view.

## Configuration
- `NWB_Material` is used on each wall or wall type to identify fire, smoke, and fire/smoke values.
- Select one loaded duct accessory or mechanical family symbol.
- Select multiple wall types from the active-view list.
- Family, symbol, and wall-type selections are remembered per open Revit project.

## Behavior
- Host walls are collected from the active view.
- Loaded architectural links are scanned for matching wall types and transformed into host coordinates.
- Bounding-box checks are performed before solid intersections.
- Placement runs in one transaction.
- Existing accessories can prevent duplicate placement where supported.

## Safety
- This tool only places the selected family; it does not determine legal damper requirements.
- Verify the selected family category and physical placement behavior before production use.
- Linked models are never modified.
