param(
    [Parameter(Mandatory=$true)][string]$TitlePrefix,
    [Parameter(Mandatory=$true)][string]$OutputPath
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -AssemblyName System.Web
Add-Type -AssemblyName System.Net.Http
$utf8=New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding=$utf8
$windows=[System.Windows.Automation.AutomationElement]::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children,[System.Windows.Automation.Condition]::TrueCondition)
$matches=@($windows | Where-Object {
    $_.Current.Name.StartsWith($TitlePrefix) -and
    (Get-Process -Id $_.Current.ProcessId -ErrorAction SilentlyContinue).ProcessName -eq 'ima.copilot'
})
if ($matches.Count -ne 1) { throw 'Expected one selected IMA reader window' }
$window=$matches[0]
$c=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty,'RootWebArea')
$document=$window.FindFirst([System.Windows.Automation.TreeScope]::Descendants,$c)
$address=([System.Windows.Automation.ValuePattern]$document.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)).Current.Value
$reader=[Uri]$address
if ($reader.Scheme -ne 'chrome-extension' -or -not (($reader.Host -eq 'cbgfjbdckbpenliighcjcbjfiihnnkfe' -and $reader.AbsolutePath -eq '/markdown.html') -or ($reader.Host -eq 'jmfjadjclplhcchkjjnjoinbfmdhjkhh' -and $reader.AbsolutePath -eq '/template/doc.html'))) { throw 'Unexpected reader origin' }
$parameters=[System.Web.HttpUtility]::ParseQueryString($reader.Query)
$origin=[Uri]$parameters['originUrl']
if (-not $origin -or $origin.Scheme -ne 'https' -or $origin.Host -ne 'res-skb.ima.qq.com') { throw 'Reader did not expose an official document resource' }
$handler=New-Object System.Net.Http.HttpClientHandler
$handler.AllowAutoRedirect=$false
$client=New-Object System.Net.Http.HttpClient($handler)
$client.Timeout=[TimeSpan]::FromSeconds(25)
$response=$null
try {
    $response=$client.GetAsync($origin,[System.Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
    if ([int]$response.StatusCode -ne 200) { throw ('Reader resource returned HTTP '+[int]$response.StatusCode) }
    if ($response.Content.Headers.ContentLength -gt 52428800) { throw 'Document exceeds 50 MB capture limit' }
    $stream=$response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
    $memory=New-Object System.IO.MemoryStream
    try {
        $buffer=New-Object byte[] 65536
        while (($length=$stream.Read($buffer,0,$buffer.Length)) -gt 0) {
            if ($memory.Length+$length -gt 52428800) { throw 'Document exceeds 50 MB capture limit' }
            $memory.Write($buffer,0,$length)
        }
        $bytes=$memory.ToArray()
    } finally { $stream.Dispose(); $memory.Dispose() }
    if ($bytes.Length -lt 100) { throw 'Document resource is unexpectedly short' }
    $path=[System.IO.Path]::GetFullPath($OutputPath)
    [System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($path)) | Out-Null
    [System.IO.File]::WriteAllBytes($path,$bytes)
    $hash=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    @{title=$window.Current.Name;bytes=$bytes.Length;path=$path;sha256=$hash;source_host=$origin.Host;reader_path=$reader.AbsolutePath;media_type=$response.Content.Headers.ContentType.MediaType} | ConvertTo-Json -Compress
} finally {
    if ($response) { $response.Dispose() }
    $client.Dispose()
    $handler.Dispose()
}
