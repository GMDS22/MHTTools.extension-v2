$b = "C:\Users\Gino Moreno\AppData\Roaming\pyRevit\Extensions\MHTTools.extension\MEINHARDT.tab"

# === MEP Create: consolidate Sections + Link Flow + Batch into Design Tools.pulldown ===
Write-Host "[MEP Create]"
$panel = "$b\MEP Create.panel"
$dest = "$panel\Design Tools.pulldown"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
foreach ($stack in @("Sections.stack", "Link Flow.stack", "Batch.stack")) {
    $stackPath = "$panel\$stack"
    Get-ChildItem $stackPath -Directory | ForEach-Object {
        Write-Host "  MOVE $($_.Name)"
        Move-Item -Path $_.FullName -Destination "$dest\$($_.Name)"
    }
    Write-Host "  DEL $stack"
    Remove-Item -Path $stackPath -Recurse -Force
}

# === MEP Modify: consolidate Split + Connect + Align + Delete + Move into All Modify.pulldown ===
Write-Host "[MEP Modify]"
$panel = "$b\MEP Modify.panel"
$dest = "$panel\All Modify.pulldown"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
foreach ($stack in @("Split.stack", "Connect.stack", "Align.stack", "Delete.stack", "Move.stack")) {
    $stackPath = "$panel\$stack"
    Get-ChildItem $stackPath -Directory | ForEach-Object {
        Write-Host "  MOVE $($_.Name)"
        Move-Item -Path $_.FullName -Destination "$dest\$($_.Name)"
    }
    Write-Host "  DEL $stack"
    Remove-Item -Path $stackPath -Recurse -Force
}

# === MEP Manage: consolidate Link Vis + Parameters + Copy + Fluid + Callout Riser Renamer into Admin Tools.pulldown ===
Write-Host "[MEP Manage]"
$panel = "$b\MEP Manage.panel"
$dest = "$panel\Admin Tools.pulldown"
New-Item -ItemType Directory -Path $dest -Force | Out-Null

# Move Callout Riser Renamer out of Family Tools.stack (fixes 4-item stack -> 3-item)
$calloutSrc = "$panel\Family Tools.stack\Callout Riser Renamer.pushbutton"
if (Test-Path $calloutSrc) {
    Write-Host "  MOVE Callout Riser Renamer (from Family Tools.stack)"
    Move-Item -Path $calloutSrc -Destination "$dest\Callout Riser Renamer.pushbutton"
}

foreach ($stack in @("Link Vis.stack", "Parameters.stack", "Copy.stack", "Fluid.stack")) {
    $stackPath = "$panel\$stack"
    Get-ChildItem $stackPath -Directory | ForEach-Object {
        Write-Host "  MOVE $($_.Name)"
        Move-Item -Path $_.FullName -Destination "$dest\$($_.Name)"
    }
    Write-Host "  DEL $stack"
    Remove-Item -Path $stackPath -Recurse -Force
}

Write-Host ""
Write-Host "All done."
