param(
    [string]$JenkinsUrl = 'http://localhost:8088',
    [string]$Job = 'QE_PerfTest',
    [string]$Build = 'lastCompletedBuild',
    [string]$Username = 'Pedram',
    [string]$Output = 'target/analysis/report.html',
    [string[]]$InputFiles,
    [switch]$NoOpen,
    [ValidatePattern('^[A-Za-z0-9-]+$')]
    [string]$RunId = ([guid]::NewGuid().ToString())
)

$ErrorActionPreference = 'Stop'
$previousToken = $env:JENKINS_API_TOKEN
$previousUser = $env:JENKINS_USER
$credential = $null
$locationChanged = $false
$exitCode = 1
$statusPath = $null
try {
    Push-Location (Split-Path $PSScriptRoot -Parent)
    $locationChanged = $true
    $reportPath = [IO.Path]::GetFullPath($Output)
    $reportDirectory = Split-Path $reportPath -Parent
    $null = New-Item -ItemType Directory -Path $reportDirectory -Force
    $statusPath = Join-Path $reportDirectory ($RunId + '.status.json')
    @{ run_id = $RunId; status = 'running'; started = (Get-Date).ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    if ($InputFiles) {
        python -m Analysis --output $reportPath --input @InputFiles
    } else {
        if (-not $env:JENKINS_USER -or -not $env:JENKINS_API_TOKEN) {
            $credential = Get-Credential -UserName $Username -Message 'Enter your Jenkins login ID. Paste the raw Jenkins API token into the Password field.'
            if ($null -eq $credential) { throw 'Login cancelled.' }
            $env:JENKINS_USER = $credential.UserName
            $env:JENKINS_API_TOKEN = $credential.GetNetworkCredential().Password
            if ([string]::IsNullOrWhiteSpace($env:JENKINS_API_TOKEN)) { throw 'The API token is empty.' }
        }
        python -m Analysis --jenkins-url $JenkinsUrl --job $Job --build $Build --output $reportPath
    }
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed. See the message above.' }
    $summaryPath = [IO.Path]::ChangeExtension($reportPath, '.json')
    $summary = Get-Content -Raw -LiteralPath $summaryPath | ConvertFrom-Json
    if (-not (Test-Path -LiteralPath $reportPath) -or $summary.overall.samples -lt 1) { throw 'Report verification failed.' }
    $browserOpened = $false
    if (-not $NoOpen) {
        try { Start-Process -FilePath $reportPath; $browserOpened = $true }
        catch { Write-Warning 'Report generated, but the browser could not be opened. Open the report path below.' }
    }
    @{ run_id = $RunId; status = 'succeeded'; finished = (Get-Date).ToString('o'); report = $reportPath; summary = $summaryPath; browser_opened = $browserOpened; source = $summary.metadata.source; build = $summary.metadata.build; samples = $summary.overall.samples } |
        ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Host ('Report ready: ' + $reportPath) -ForegroundColor Green
    $exitCode = 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($statusPath) {
        @{ run_id = $RunId; status = 'failed'; finished = (Get-Date).ToString('o'); message = $_.Exception.Message } |
            ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
    }
} finally {
    $env:JENKINS_API_TOKEN = $previousToken
    $env:JENKINS_USER = $previousUser
    $credential = $null
    $previousToken = $null
    if ($locationChanged) { Pop-Location }
}
exit $exitCode
