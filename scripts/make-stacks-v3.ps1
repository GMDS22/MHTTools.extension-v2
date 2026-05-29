$ext = "C:\Users\Gino Moreno\AppData\Roaming\pyRevit\Extensions\MHTTools.extension\MEINHARDT.tab"

# --- Documentation: move ToolsDescription into Docs.stack ---
Move-Item "$ext\Documentation.panel\ToolsDescription.pushbutton" "$ext\Documentation.panel\Docs.stack\ToolsDescription.pushbutton"
Write-Host "OK: ToolsDescription -> Docs.stack"

# --- MEP Create: move 03 Unified Create into Pipe Tools.stack ---
Move-Item "$ext\MEP Create.panel\03 Unified Create (Rooms-Areas-Spaces-Zones).pushbutton" "$ext\MEP Create.panel\Pipe Tools.stack\03 Unified Create (Rooms-Areas-Spaces-Zones).pushbutton"
Write-Host "OK: 03 Unified Create -> Pipe Tools.stack"

# --- MEP Modify: create Modify.stack, move RemoveDuplicates + 04 Color ---
New-Item -ItemType Directory -Path "$ext\MEP Modify.panel\Modify.stack" -Force | Out-Null
Move-Item "$ext\MEP Modify.panel\RemoveDuplicates.pushbutton" "$ext\MEP Modify.panel\Modify.stack\RemoveDuplicates.pushbutton"
Move-Item "$ext\MEP Modify.panel\Color.stack\04 Color by Value (Export-Import).pushbutton" "$ext\MEP Modify.panel\Modify.stack\04 Color by Value (Export-Import).pushbutton"
Write-Host "OK: Modify.stack created (RemoveDuplicates + 04 Color)"

# --- MEP Data: create Space.stack, move RoomToSpace + RenumberBySpline ---
New-Item -ItemType Directory -Path "$ext\MEP Data.panel\Space.stack" -Force | Out-Null
Move-Item "$ext\MEP Data.panel\RoomToSpace.pushbutton" "$ext\MEP Data.panel\Space.stack\RoomToSpace.pushbutton"
Move-Item "$ext\MEP Data.panel\Place Tools.stack\RenumberBySpline.pushbutton" "$ext\MEP Data.panel\Space.stack\RenumberBySpline.pushbutton"
Write-Host "OK: Space.stack created (RoomToSpace + RenumberBySpline)"

# --- MEP Manage: create Manage.stack, move GM Filters + FamilyReLoad ---
New-Item -ItemType Directory -Path "$ext\MEP Manage.panel\Manage.stack" -Force | Out-Null
Move-Item "$ext\MEP Manage.panel\GM Filters by Value.pushbutton" "$ext\MEP Manage.panel\Manage.stack\GM Filters by Value.pushbutton"
Move-Item "$ext\MEP Manage.panel\Family Tools.stack\FamilyReLoad.pushbutton" "$ext\MEP Manage.panel\Manage.stack\FamilyReLoad.pushbutton"
Write-Host "OK: Manage.stack created (GM Filters + FamilyReLoad)"

Write-Host ""
Write-Host "All moves complete."
