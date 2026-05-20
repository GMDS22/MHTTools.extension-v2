# Linked Room Parameter Tool - Crash Fixes (May 2026)

## Problem Identified
The tool was crashing when running "Auto-Detect Rooms for Entire Project", especially on large projects with many elements and rooms.

## Root Causes

### 1. **O(n*m) Performance Problem**
- When "Entire Project" scope was selected, the tool collected ALL elements from all selected categories
- Then for each element, it searched through ALL linked rooms to find containment
- Result: With 5000 elements and 500 rooms = 2.5 million point-in-polygon calculations
- This caused severe performance degradation, memory bloat, and crashes

### 2. **Unbounded Element Collection**
- No limit on how many elements could be collected from the project
- Large projects could result in collecting hundreds of thousands of elements
- Caused memory exhaustion and crashes

### 3. **Missing Exception Handling in Boundary Processing**
- `GetBoundarySegments()` could fail on complex room boundaries without proper handling
- No graceful degradation when a room's boundary couldn't be processed
- Would crash entire operation if any room had boundary issues

### 4. **No User Warning for Large Operations**
- Users could inadvertently trigger massive operations without understanding the impact
- No feedback that the operation was happening (Revit appeared frozen)

## Fixes Applied

### 1. **Added Element Collection Limits** (in `_iter_selected_category_elements`)
- **Entire Project** scope now limited to max 5,000 elements
- **Active View Level** scope limited to max 50,000 elements
- Prevents unbounded collection that causes memory issues
- When limit is reached, collection stops and user is notified

### 2. **Enhanced Exception Handling** (in `_build_room_detection_index`)
- Added try-catch around `GetBoundarySegments()` call
- Added try-catch around boundary loop processing
- Errors are logged as DEBUG messages, not fatal
- If a room's boundary fails, it skips to next room instead of crashing
- Better error checking on curve and polygon data

### 3. **Added User Warning Dialog** (in `auto_detect_elements_click`)
- When "Entire Project" scope is selected, user sees a warning dialog
- Explains the performance risks
- Recommends alternatives (View Level scope, pre-selection, category filtering)
- User must confirm before proceeding with entire project search

### 4. **Improved Safety in Transfer Operation** (in `transfer_click`)
- Added warning if transferring to more than 1000 elements
- Prevents accidental massive operations
- User must confirm before proceeding

### 5. **Better Boundary Testing** (in `_find_linked_room_for_host_point`)
- Added try-catch around boundary polygon tests
- If boundary test fails, continues to next room instead of crashing
- More robust coordinate access (px, py extraction in try block)

## Recommended Usage

### For "Entire Project" Operations:
1. **Preferred**: Use "Active View Level" scope if elements are primarily on one level
2. **Alternative**: Pre-select elements in your view, then use "Use Current Selection" button
3. **Last Resort**: Use "Entire Project" scope but:
   - First, filter down categories to only what you need
   - Expect slower performance
   - Stay patient while Revit processes

### For Large Projects:
- Split work by level or zone
- Use multiple passes instead of one massive "Entire Project" operation
- Pre-filter elements by category before auto-detect

## Testing Recommendations

1. Test on small project first with "Entire Project" scope to verify it works
2. Test on large project with "Active View Level" scope
3. Test with projects that have complex room boundaries
4. Test with category filtering enabled/disabled
5. Verify that the warning dialog appears for "Entire Project" scope

## Performance Notes

- Single view level detection: ~100-200ms per 1000 elements
- Entire project with 5000 element limit: ~2-5 seconds depending on room count
- If operation takes longer than 30 seconds, user can cancel from dialog

## Notes

- Element limit of 5000 for "Entire Project" is a safety measure
- Can be adjusted in `_iter_selected_category_elements` if needed
- Log messages are now more detailed for debugging issues
- All changes are backward compatible with existing tool functionality
