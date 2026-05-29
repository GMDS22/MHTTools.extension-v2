# Linked Elements Parameter Tool - Safe Usage Guide

## Quick Summary of Changes

The tool has been fixed to prevent crashes when using "Entire Project" scope. The following safety measures have been added:

### ✅ Now Fixed:
- Tool no longer crashes on large projects
- Auto-detect for entire project now works (with limits)
- Better error handling for complex room boundaries
- User warnings for potentially slow operations
- Element collection limits to prevent memory issues

## How to Use Safely

### Best Practice: Use "Active View Level" (RECOMMENDED)
1. Set detection scope to **"Active View Level"**
2. Open the level/plan view where your elements are
3. Click "Detect Rooms In Current View"
4. Much faster and more reliable than entire project

### For Multiple Levels:
- Run the tool on each level separately
- Combine results from multiple levels as needed
- More reliable than trying entire project at once

### For "Entire Project" Scope:
1. A warning dialog will appear when you select this scope
2. Read the warning carefully
3. Only proceed if necessary
4. Tool will limit to ~5,000 elements to prevent crashes
5. May take 2-5 seconds depending on project size

### To Pre-Select Elements (FASTEST):
1. In your view, select the MEP elements you want to process
2. Click **"Use Current Selection"** button
3. This bypasses the auto-detect completely
4. Fastest and most reliable method

## Scope Options Explained

| Scope | Best For | Speed | Reliability |
|-------|----------|-------|-------------|
| Active View Level | Elements on one level | ⚡ Fast | ✅ Excellent |
| Entire Project | Large multi-level projects | 🐢 Slow | ⚠️ Risky |
| Current Selection | Pre-selected elements | ⚡⚡ Fastest | ✅ Best |

## Troubleshooting

### If "Entire Project" scope is slow:
- Click "Cancel" in the dialog that appears
- Switch to "Active View Level" scope instead
- Or pre-select elements and use "Current Selection"

### If auto-detect finds 0 elements:
- Verify linked rooms exist in the linked model
- Check that categories are selected
- Try "Active View Level" scope with linked model open
- Check that elements are in the same level as rooms

### If transfer takes too long:
- Tool will warn you if processing 1000+ elements
- Consider breaking work into multiple passes
- Use level-by-level approach for large projects

## What Changed Behind The Scenes

1. **Element limits**: Max 5,000 for "Entire Project", prevents memory issues
2. **Better error handling**: Complex boundaries no longer crash the tool
3. **User warnings**: Clear dialog explaining risks of large operations
4. **Confirmation dialogs**: For operations that might be slow
5. **Improved robustness**: Better exception handling throughout

## Performance Tips

- Use "Active View Level" = 0.5-2 seconds
- Use pre-selected elements = 0.1-0.5 seconds  
- Use "Entire Project" small project = 2-5 seconds
- Use "Entire Project" large project = may take 5-30 seconds

## If You Still Experience Issues

1. Check the log file location shown in transfer results
2. Try restarting Revit if tool feels unstable
3. Contact tool maintainer with log file attached
4. Report error message and project size details
