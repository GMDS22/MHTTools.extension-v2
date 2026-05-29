$b = "C:\Users\Gino Moreno\AppData\Roaming\pyRevit\Extensions\MHTTools.extension\MEINHARDT.tab"
$panels = Get-ChildItem $b -Directory | Sort-Object Name
foreach ($p in $panels) {
    Write-Host "=== $($p.Name) ==="
    Get-ChildItem $p.FullName -Directory | ForEach-Object { "  [D] $($_.Name)" }
    Get-ChildItem $p.FullName -File -Filter "bundle.yaml" | ForEach-Object {
        Get-Content $_.FullName | ForEach-Object { "      $_" }
    }
    Write-Host ""
}
