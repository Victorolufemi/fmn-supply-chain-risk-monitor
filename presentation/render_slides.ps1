# Export every slide to PNG using the installed PowerPoint.
# This is a true render — the same engine that will display the deck — so it is
# more faithful than a LibreOffice preview, which substitutes fonts.
param(
    [string]$Deck = "D:\work\FMN1\presentation\Supply-Chain-Risk-Monitor.pptx",
    [string]$Out  = "D:\work\FMN1\presentation\render"
)

if (Test-Path $Out) { Remove-Item -Recurse -Force $Out }
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$ppt = New-Object -ComObject PowerPoint.Application
try {
    # 24 = msoFalse for WithWindow is not permitted for PowerPoint; open normally but hidden-ish
    $deckObj = $ppt.Presentations.Open($Deck, $true, $false, $false)  # ReadOnly, Untitled, WithWindow=false
    $i = 1
    foreach ($slide in $deckObj.Slides) {
        $name = "{0}\slide-{1:D2}.png" -f $Out, $i
        $slide.Export($name, "PNG", 1600, 900)
        $i++
    }
    Write-Output "exported $($deckObj.Slides.Count) slides to $Out"
    $deckObj.Close()
}
finally {
    $ppt.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
}
