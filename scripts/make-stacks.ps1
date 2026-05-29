$b = "C:\Users\Gino Moreno\AppData\Roaming\pyRevit\Extensions\MHTTools.extension\MEINHARDT.tab"

function Move-ToStack([string]$panel, [string]$stack, [string[]]$tools) {
    $stackPath = Join-Path $b "$panel.panel\$stack.stack"
    New-Item -ItemType Directory $stackPath -Force | Out-Null
    foreach ($t in $tools) {
        $src = Join-Path $b "$panel.panel\$t.pushbutton"
        $dst = Join-Path $stackPath "$t.pushbutton"
        if (Test-Path $src) {
            Move-Item $src $dst -Force
            Write-Host "  MOVED  $t  ->  $stack"
        } else {
            Write-Host "  SKIP   $t  (not found at $src)"
        }
    }
}

# ─── Sheets and Views ───────────────────────────────────────────────────────────
Write-Host "`n[Sheets and Views]"
Move-ToStack "Sheets and Views" "View Tools" @("QUICK FORMAT","Hide Grids","Views Links Manager")
Move-ToStack "Sheets and Views" "Room Links" @("Plan Link Setup","Auto Room Names","Copy Room Tags")

# ─── MEP Create ─────────────────────────────────────────────────────────────────
Write-Host "`n[MEP Create]"
Move-ToStack "MEP Create" "Sections" @("CreateSection","QuickDimension","HOST")
Move-ToStack "MEP Create" "Link Flow"  @("LINK","S2A","BatchCreateSystems")
Move-ToStack "MEP Create" "Batch"    @("BatchDependentViewCreation","BatchWorksetCreation","PipeTypeFromCSV")

# ─── MEP Modify ─────────────────────────────────────────────────────────────────
Write-Host "`n[MEP Modify]"
Move-ToStack "MEP Modify" "Split"    @("SplitPipes","SplitSelectedPipes")
Move-ToStack "MEP Modify" "Connect"  @("ConnectTo","DisConnect")
Move-ToStack "MEP Modify" "Align"    @("MakeParallel","Element3DRotation","FlexFlatten")
Move-ToStack "MEP Modify" "Delete"   @("FamilyDelete","FamilyTypeDelete","ParameterDelete","SystemDelete")
Move-ToStack "MEP Modify" "Move"     @("MoveLabelToOrigin","MoveSpaceToRoom","MoveTitleBlockToOrigin")
Move-ToStack "MEP Modify" "Grey"     @("GreyOutElements","GreyOutElements_reset")

# ─── MEP Data ───────────────────────────────────────────────────────────────────
Write-Host "`n[MEP Data]"
Move-ToStack "MEP Data" "Linked Params" @("Linked Elements Parameter","Linked Room Parameter","Linked Type Overlay")
Move-ToStack "MEP Data" "Materials"     @("ExportMaterialsGraphics","UpdateMaterials")
Move-ToStack "MEP Data" "Level Change"  @("ElementChangeLevel","ElevationUnder")

# ─── MEP Manage ─────────────────────────────────────────────────────────────────
Write-Host "`n[MEP Manage]"
Move-ToStack "MEP Manage" "Family Tools"   @("FamilyReLoad","07 Family Renamer","09 Family Convention Converter","Callout Riser Renamer")
Move-ToStack "MEP Manage" "Parameters"     @("ManageDocumentParameters","ManageSharedParameter","ParameterTransfer")
Move-ToStack "MEP Manage" "Copy"           @("CopyPipeType","CopyProjectUnits","CopyViewRange","CopyViewType")
Move-ToStack "MEP Manage" "Fluid"          @("FluidCreate","ReplaceFluid")

Write-Host "`nAll stacks created."
