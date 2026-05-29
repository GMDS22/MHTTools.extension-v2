$b = "C:\Users\Gino Moreno\AppData\Roaming\pyRevit\Extensions\MHTTools.extension\MEINHARDT.tab"

function mv($src, $dst) {
    if (Test-Path $src) {
        Move-Item $src $dst -Force
        Write-Host "  MOVE $([System.IO.Path]::GetFileName($src)) -> $([System.IO.Path]::GetFileName($dst))"
    } else {
        Write-Host "  SKIP $src (not found)"
    }
}
function rmfile($p) {
    if (Test-Path $p) { Remove-Item $p -Force; Write-Host "  DEL $p" }
}
function rmdir_if_empty($p) {
    if (Test-Path $p) {
        $children = Get-ChildItem $p
        if ($children.Count -eq 0) { Remove-Item $p; Write-Host "  RMDIR $p" }
        else { Write-Host "  KEEP $p (has $($children.Count) children)" }
    }
}

# ════════════════════════════════════════════════════════════════════
# 1. SHEETS AND VIEWS  →  1 large + 3 stacks = 4 cols
#    New: Sheet Tools.stack (FORMAT, RENUMBER_RENAME, AlignViewports)
#    Keep: View Tools.stack, Room Links.stack
# ════════════════════════════════════════════════════════════════════
Write-Host "`n[Sheets and Views]"
$sv = "$b\Sheets and Views.panel"
New-Item "$sv\Sheet Tools.stack" -ItemType Directory -Force | Out-Null
mv "$sv\FORMAT.pushbutton"          "$sv\Sheet Tools.stack\FORMAT.pushbutton"
mv "$sv\RENUMBER_RENAME.pushbutton" "$sv\Sheet Tools.stack\RENUMBER_RENAME.pushbutton"
mv "$sv\AlignViewports.pushbutton"  "$sv\Sheet Tools.stack\AlignViewports.pushbutton"

# ════════════════════════════════════════════════════════════════════
# 2. MEP CREATE  →  1 large + 4 stacks = 5 cols
#    New: Pipe Tools.stack (Transition, Ductulator)
#    Keep: Sections.stack, Link Flow.stack, Batch.stack
# ════════════════════════════════════════════════════════════════════
Write-Host "`n[MEP Create]"
$mc = "$b\MEP Create.panel"
New-Item "$mc\Pipe Tools.stack" -ItemType Directory -Force | Out-Null
mv "$mc\Transition.pushbutton" "$mc\Pipe Tools.stack\Transition.pushbutton"
mv "$mc\Ductulator.pushbutton" "$mc\Pipe Tools.stack\Ductulator.pushbutton"

# ════════════════════════════════════════════════════════════════════
# 3. MEP MODIFY  →  1 large + 7 stacks = 8 cols
#    New: Color.stack (04 Color by Value, 05 Color Scheme, 06 Legend)
#    New: Filter.stack (08 Selection Filter + Grey stack contents)
#    Delete: Grey.stack (absorbed into Filter.stack)
#    Keep: Split, Connect, Align, Delete, Move stacks
# ════════════════════════════════════════════════════════════════════
Write-Host "`n[MEP Modify]"
$mm = "$b\MEP Modify.panel"

# Color.stack
New-Item "$mm\Color.stack" -ItemType Directory -Force | Out-Null
mv "$mm\04 Color by Value (Export-Import).pushbutton" "$mm\Color.stack\04 Color by Value (Export-Import).pushbutton"
mv "$mm\05 Color Scheme Editor.pushbutton"            "$mm\Color.stack\05 Color Scheme Editor.pushbutton"
mv "$mm\06 Legend Creator.pushbutton"                 "$mm\Color.stack\06 Legend Creator.pushbutton"

# Filter.stack = 08 Selection Filter + former Grey.stack contents
New-Item "$mm\Filter.stack" -ItemType Directory -Force | Out-Null
mv "$mm\08 Selection Filter.pushbutton"              "$mm\Filter.stack\08 Selection Filter.pushbutton"
mv "$mm\Grey.stack\GreyOutElements.pushbutton"       "$mm\Filter.stack\GreyOutElements.pushbutton"
mv "$mm\Grey.stack\GreyOutElements_reset.pushbutton" "$mm\Filter.stack\GreyOutElements_reset.pushbutton"
rmfile "$mm\Grey.stack\bundle.yaml"
rmdir_if_empty "$mm\Grey.stack"

# ════════════════════════════════════════════════════════════════════
# 4. MEP DATA  →  1 large + 3 stacks = 4 cols
#    New: Place Tools.stack (RenumberBySpline + Level Change.stack contents)
#    Delete: Level Change.stack (absorbed)
#    Keep: Linked Params.stack, Materials.stack
# ════════════════════════════════════════════════════════════════════
Write-Host "`n[MEP Data]"
$md = "$b\MEP Data.panel"
New-Item "$md\Place Tools.stack" -ItemType Directory -Force | Out-Null
mv "$md\RenumberBySpline.pushbutton"                      "$md\Place Tools.stack\RenumberBySpline.pushbutton"
mv "$md\Level Change.stack\ElementChangeLevel.pushbutton" "$md\Place Tools.stack\ElementChangeLevel.pushbutton"
mv "$md\Level Change.stack\ElevationUnder.pushbutton"     "$md\Place Tools.stack\ElevationUnder.pushbutton"
rmfile "$md\Level Change.stack\bundle.yaml"
rmdir_if_empty "$md\Level Change.stack"

# ════════════════════════════════════════════════════════════════════
# 5. MEP MANAGE  →  1 large + 5 stacks = 6 cols
#    New: Link Vis.stack (LINKS, LINKVIS)
#    Keep: Family Tools, Parameters, Copy, Fluid stacks
# ════════════════════════════════════════════════════════════════════
Write-Host "`n[MEP Manage]"
$mg = "$b\MEP Manage.panel"
New-Item "$mg\Link Vis.stack" -ItemType Directory -Force | Out-Null
mv "$mg\LINKS.pushbutton"   "$mg\Link Vis.stack\LINKS.pushbutton"
mv "$mg\LINKVIS.pushbutton" "$mg\Link Vis.stack\LINKVIS.pushbutton"

Write-Host "`nAll moves complete."
