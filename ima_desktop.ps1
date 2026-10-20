param(
    [Parameter(Mandatory=$true)][ValidateSet('search','open','capture','close','results')][string]$Action,
    [string]$Query,
    [string]$TitlePrefix,
    [string]$MediaId,
    [string]$OutputPath,
    [int]$OpenRetries=3,
    [ValidateSet('MD','WORD','PDF')][string]$DocumentType='MD',
    [string]$Library='孟哥火火小红书AI电商知识库'
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Web
$utf8=New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding=$utf8

function Find-Name($parent,$name) {
    $c=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::NameProperty,$name)
    return $parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$c)
}
function Find-Id($parent,$id) {
    $c=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,$id)
    return $parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$c)
}
function Descendants($parent) {
    return $parent.FindAll([System.Windows.Automation.TreeScope]::Descendants,[System.Windows.Automation.Condition]::TrueCondition)
}
function Invoke-Nearest($element) {
    for ($i=0;$i -lt 6;$i++) {
        if (-not $element) { break }
        $pattern=$null
        if ($element.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)) { $pattern.Invoke(); return }
        $element=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($element)
    }
    throw 'No supported action on selected element'
}
function Get-Windows {
    return @([System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition) | Where-Object {
        (Get-Process -Id $_.Current.ProcessId -ErrorAction SilentlyContinue).ProcessName -eq 'ima.copilot'
    })
}
$windows=Get-Windows
$main=@($windows | Where-Object { $_.Current.Name -eq 'ima' })
if ($main.Count -ne 1) { throw 'Expected one running IMA main window' }
$main=$main[0]
if ($Action -in @('search','open','results')) {
    $doc=Find-Id $main 'RootWebArea'
    if ($doc.Current.Name -ne $Library) { throw 'The selected IMA library does not match the requested library' }
}
if ($Action -eq 'search') {
    if (-not $Query -or $Query.Length -gt 250) { throw 'Use a search phrase of 1 to 250 characters' }
    $literalQuery=[regex]::Replace($Query,'([+^%~(){}\[\]])','{$1}')
    # The actual reader has a contenteditable Group under the library content header.
    $r=$main.Current.BoundingRectangle
    $groups=@(Descendants $main | Where-Object {
        $b=$_.Current.BoundingRectangle
        $p=$null
        $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Group -and
        $b.X -gt ($r.X+80) -and $b.X -lt ($r.X+900) -and
        $b.Y -gt ($r.Y+200) -and $b.Y -lt ($r.Y+400) -and
        $b.Width -gt 100 -and $b.Height -lt 80 -and
        $_.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern,[ref]$p)
    })
    if ($groups.Count -ne 1) { throw 'Open the library content search first; its editor must be uniquely identified' }
    for ($attempt=0; $attempt -lt 3; $attempt++) {
        $groups[0].SetFocus()
        Start-Sleep -Milliseconds 150
        if ([System.Windows.Automation.AutomationElement]::FocusedElement.Current.ProcessId -eq $main.Current.ProcessId) { break }
    }
    if ([System.Windows.Automation.AutomationElement]::FocusedElement.Current.ProcessId -ne $main.Current.ProcessId) { throw 'IMA lost keyboard focus' }
    [System.Windows.Forms.SendKeys]::SendWait('^a')
    [System.Windows.Forms.SendKeys]::SendWait($literalQuery)
    [System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
    @{action='search';query=$Query} | ConvertTo-Json -Compress
} elseif ($Action -eq 'open') {
    if (-not $TitlePrefix) { throw 'TitlePrefix is required' }
    if ($MediaId) {
        # This ID is observed on real result rows and comes from the official catalog.
        $target=Find-Id $main ('knowledge-'+$MediaId)
        if (-not $target) {
            if ($OpenRetries -gt 0) { Start-Sleep -Milliseconds 700; & $PSCommandPath -Action open -TitlePrefix $TitlePrefix -MediaId $MediaId -Library $Library -DocumentType $DocumentType -OpenRetries ($OpenRetries-1); exit }
            throw 'Selected catalog resource has no matching result row'
        }
        $tp=[System.Windows.Automation.TextPattern]$doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
        if ($tp.RangeFromChild($target).GetText(-1) -notmatch ('(?m)^'+$DocumentType+'\r?$')) { throw 'Selected resource type differs from requested type' }
        if ($target.Current.IsOffscreen) {
            ([System.Windows.Automation.ScrollItemPattern]$target.GetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern)).ScrollIntoView()
        }
        $cards=@($target.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition) | Where-Object {
            $pattern=$null
            $_.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern) -and
            $_.Current.BoundingRectangle.Width -ge ($target.Current.BoundingRectangle.Width * .8)
        })
        if ($cards.Count -ne 1) { throw 'Resource row has no unique content action' }
        Invoke-Nearest $cards[0]
        @{action='open';prefix=$TitlePrefix;matched_catalog_id=$true} | ConvertTo-Json -Compress
        exit
    }
    $matches=@(Descendants $main | Where-Object {
        $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Text -and
        ([string]$_.Current.Name).StartsWith($TitlePrefix)
    })
    if ($matches.Count -lt 1) {
        if ($OpenRetries -gt 0) { Start-Sleep -Milliseconds 700; & $PSCommandPath -Action open -TitlePrefix $TitlePrefix -Library $Library -DocumentType $DocumentType -OpenRetries ($OpenRetries-1); exit }
        throw "No result matches $TitlePrefix"
    }
    $tp=[System.Windows.Automation.TextPattern]$doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    $selected=$null
    foreach ($match in $matches) {
        # Highlighted search text is also a Text node. Exclude input editors
        # before looking for a result's invokable ancestor.
        $ancestor=$match
        $insideEditor=$false
        for ($depth=0;$depth -lt 8 -and $ancestor;$depth++) {
            $editorPattern=$null
            if ($ancestor.Current.ControlType -eq [System.Windows.Automation.ControlType]::Group -and
                $ancestor.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern,[ref]$editorPattern)) {
                $insideEditor=$true
                break
            }
            $ancestor=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($ancestor)
        }
        if ($insideEditor) { continue }
        $candidate=$match
        for ($i=0;$i -lt 6;$i++) {
            $pattern=$null
            if (([string]$candidate.Current.AutomationId).StartsWith('knowledge-') -and $candidate.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern)) {
                $rowText=$tp.RangeFromChild($candidate).GetText(-1)
                if ($rowText.Length -lt 3000 -and $rowText -match ('(?m)^'+$DocumentType+'\r?$')) { $selected=$candidate; break }
                break
            }
            $candidate=[System.Windows.Automation.TreeWalker]::ControlViewWalker.GetParent($candidate)
        }
        if ($selected) { break }
    }
    if (-not $selected) {
        if ($OpenRetries -gt 0) { Start-Sleep -Milliseconds 700; & $PSCommandPath -Action open -TitlePrefix $TitlePrefix -Library $Library -DocumentType $DocumentType -OpenRetries ($OpenRetries-1); exit }
        throw 'No matching Markdown result; images and PDFs were excluded'
    }
    if ($selected.Current.IsOffscreen) {
        ([System.Windows.Automation.ScrollItemPattern]$selected.GetCurrentPattern([System.Windows.Automation.ScrollItemPattern]::Pattern)).ScrollIntoView()
    }
    $cards=@($selected.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition) | Where-Object {
        $pattern=$null
        $_.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern,[ref]$pattern) -and
        $_.Current.BoundingRectangle.Width -ge ($selected.Current.BoundingRectangle.Width * .8)
    })
    if ($cards.Count -ne 1) { throw 'Resource row has no unique content action' }
    Invoke-Nearest $cards[0]
    @{action='open';prefix=$TitlePrefix} | ConvertTo-Json -Compress
} elseif ($Action -eq 'results') {
    $r=$main.Current.BoundingRectangle
    @(Descendants $main | Where-Object {
        $b=$_.Current.BoundingRectangle
        $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Text -and
        $b.X -ge ($r.X+360) -and $b.X -lt ($r.X+748) -and $b.Y -ge ($r.Y+300)
    } | ForEach-Object { $_.Current.Name }) | ConvertTo-Json -Compress
} else {
    if (-not $TitlePrefix) { throw 'TitlePrefix is required' }
    $readers=@($windows | Where-Object { ([string]$_.Current.Name).StartsWith($TitlePrefix) -and $_.Current.Name -ne 'ima' })
    if ($readers.Count -ne 1) { throw 'Expected a unique matching course reader window' }
    $reader=$readers[0]
    if ($Action -eq 'close') {
        $closingTitle=$reader.Current.Name
        ([System.Windows.Automation.WindowPattern]$reader.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern)).Close()
        @{action='close';title=$closingTitle} | ConvertTo-Json -Compress
        exit
    }
    if (-not $OutputPath) { throw 'OutputPath is required' }
    $doc=Find-Id $reader 'RootWebArea'
    $pane=Find-Id $doc 'markdown-viewer-container'
    if (-not $pane) { throw 'This reader is not the verified Markdown viewer' }
    $url=([System.Windows.Automation.ValuePattern]$doc.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).Current.Value
    $uri=[Uri]$url
    if ($uri.Scheme -ne 'chrome-extension' -or $uri.Host -ne 'cbgfjbdckbpenliighcjcbjfiihnnkfe' -or $uri.AbsolutePath -ne '/markdown.html') { throw 'Unexpected IMA Markdown reader address' }
    $tp=[System.Windows.Automation.TextPattern]$doc.GetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern)
    $range=$tp.RangeFromChild($pane)
    $content=$range.GetText(-1).Trim()
    if ($content.Length -lt 100) { throw 'Reader contains too little text' }
    $imageDescriptions=@(Descendants $pane | Where-Object { $_.Current.ControlType -eq [System.Windows.Automation.ControlType]::Image } | ForEach-Object { $_.Current.Name })
    $queryParams=[System.Web.HttpUtility]::ParseQueryString($uri.Query)
    $queryShapes=@($queryParams.AllKeys | ForEach-Object {
        $paramValue=$queryParams[$_]; $paramUri=$null; $isUri=[Uri]::TryCreate($paramValue,[UriKind]::Absolute,[ref]$paramUri)
        @{key=$_;length=$paramValue.Length;scheme=$(if($isUri){$paramUri.Scheme}else{''});host=$(if($isUri){$paramUri.Host}else{''})}
    })
    $hash=[System.Security.Cryptography.SHA256]::Create()
    $sha=([BitConverter]::ToString($hash.ComputeHash($utf8.GetBytes($content)))).Replace('-','').ToLowerInvariant()
    $hash.Dispose()
    $record=@{
        title=$reader.Current.Name;library=$Library;content=$content;
        url=($uri.Scheme+'://'+$uri.Host+$uri.AbsolutePath);
        captured_at=[DateTime]::UtcNow.ToString('o');content_sha256=$sha;
        coverage='visible_text_excerpt';capture_method='windows_uia';
        images_in_pane=$imageDescriptions.Count;image_descriptions=$imageDescriptions;
        reader_container='markdown-viewer-container';application='ima.copilot';reader_query_shapes=$queryShapes
    }
    $full=[System.IO.Path]::GetFullPath($OutputPath)
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($full)) | Out-Null
    [System.IO.File]::WriteAllText($full,($record | ConvertTo-Json -Depth 6),$utf8)
    $check=[System.IO.File]::ReadAllText($full,$utf8) | ConvertFrom-Json
    if ($check.content -cne $content) { throw 'Capture verification failed' }
    @{title=$record.title;characters=$content.Length;images=$imageDescriptions.Count;path=$full;sha256=$sha} | ConvertTo-Json -Compress
}
