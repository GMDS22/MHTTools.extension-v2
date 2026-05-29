$b = "C:\Users\Gino Moreno\AppData\Roaming\pyRevit\Extensions\MHTTools.extension\MEINHARDT.tab"

# === 1. Sheets and Views: merge 3 stacks -> View Manage.pulldown ===
Write-Host "[Sheets and Views]"
$panel = "$b\Sheets and Views.panel"
$dest  = "$panel\View Manage.pulldown"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
foreach ($s in @("Sheet Tools.stack","View Tools.stack","Room Links.stack")) {
    Get-ChildItem "$panel\$s" -Directory | ForEach-Object {
        Write-Host "  MOVE $($_.Name)"
        Move-Item -Path $_.FullName -Destination "$dest\$($_.Name)"
    }
    Remove-Item -Path "$panel\$s" -Recurse -Force
    Write-Host "  DEL $s"
}

# === 2. MEP Modify: move Filter.stack items into All Modify.pulldown, keep Color.stack ===
Write-Host "[MEP Modify]"
$panel = "$b\MEP Modify.panel"
$dest  = "$panel\All Modify.pulldown"
foreach ($btn in @("08 Selection Filter.pushbutton","GreyOutElements.pushbutton","GreyOutElements_reset.pushbutton")) {
    $src = "$panel\Filter.stack\$btn"
    if (Test-Path $src) {
        Write-Host "  MOVE $btn"
        Move-Item -Path $src -Destination "$dest\$btn"
    }
}
Remove-Item -Path "$panel\Filter.stack" -Recurse -Force
Write-Host "  DEL Filter.stack"

# === 3. MEP Data: merge Linked Params.stack + Materials.stack -> Data Manage.pulldown ===
Write-Host "[MEP Data]"
$panel = "$b\MEP Data.panel"
$dest  = "$panel\Data Manage.pulldown"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
foreach ($s in @("Linked Params.stack","Materials.stack")) {
    Get-ChildItem "$panel\$s" -Directory | ForEach-Object {
        Write-Host "  MOVE $($_.Name)"
        Move-Item -Path $_.FullName -Destination "$dest\$($_.Name)"
    }
    Remove-Item -Path "$panel\$s" -Recurse -Force
    Write-Host "  DEL $s"
}

# === 4. Audit and Exchange: create Audit.stack, move SpaceVsRoom+Excel+MultiIFC ===
Write-Host "[Audit and Exchange]"
$panel = "$b\Audit and Exchange.panel"
$dest  = "$panel\Audit.stack"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
foreach ($btn in @("SpaceVsRoom.pushbutton","Excel.pushbutton","MultiIFC.pushbutton")) {
    if (Test-Path "$panel\$btn") {
        Write-Host "  MOVE $btn"
        Move-Item -Path "$panel\$btn" -Destination "$dest\$btn"
    }
}

# === 5. Documentation: create Docs.stack, move FamilyNamingConvention+About ===
Write-Host "[Documentation]"
$panel = "$b\Documentation.panel"
$dest  = "$panel\Docs.stack"
New-Item -ItemType Directory -Path $dest -Force | Out-Null
foreach ($btn in @("FamilyNamingConvention.pushbutton","About.pushbutton")) {
    if (Test-Path "$panel\$btn") {
        Write-Host "  MOVE $btn"
        Move-Item -Path "$panel\$btn" -Destination "$dest\$btn"
    }
}

Write-Host ""
Write-Host "All done."
