param(
    [string]$OutputDirectory = "artifacts",
    [string]$PythonVersion = "3.14.7",
    [string]$PythonSha256 = "d297e5ff019966817ad8502465176139f2d3d840fa4ed84b13bed399a6ab1f15"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$OutputRoot = [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutputDirectory))
if (-not $OutputRoot.StartsWith($RepoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputDirectory must stay inside the repository."
}

$BuildId = [Guid]::NewGuid().ToString("N")
$Stage = Join-Path $OutputRoot ".portable-$BuildId"
$App = Join-Path $Stage "Video Grabber"
$PythonDir = Join-Path $App "runtime\python"
New-Item -ItemType Directory -Force -Path $PythonDir | Out-Null

try {
    $PythonZip = Join-Path $Stage "python.zip"
    $PythonUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    Write-Host "Downloading official Python $PythonVersion embeddable runtime..."
    Invoke-WebRequest -UseBasicParsing -Uri $PythonUrl -OutFile $PythonZip
    $ActualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $PythonZip).Hash.ToLowerInvariant()
    if ($ActualHash -ne $PythonSha256.ToLowerInvariant()) {
        throw "Python SHA-256 mismatch. Expected $PythonSha256, got $ActualHash"
    }
    Expand-Archive -LiteralPath $PythonZip -DestinationPath $PythonDir

    $Pth = Get-ChildItem -LiteralPath $PythonDir -Filter "python*._pth" | Select-Object -First 1
    if (-not $Pth) { throw "Embedded Python _pth file was not found." }
    $PthLines = Get-Content -LiteralPath $Pth.FullName
    $PthLines = $PthLines | Where-Object { $_ -ne "#import site" -and $_ -ne "import site" -and $_ -ne "Lib\site-packages" }
    @($PthLines) + "Lib\site-packages" + "import site" | Set-Content -LiteralPath $Pth.FullName -Encoding ASCII

    $SitePackages = Join-Path $PythonDir "Lib\site-packages"
    New-Item -ItemType Directory -Force -Path $SitePackages | Out-Null
    $BuilderPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $BuilderPython)) { $BuilderPython = "python" }
    & $BuilderPython -m pip install --disable-pip-version-check --upgrade --target $SitePackages pip
    if ($LASTEXITCODE -ne 0) { throw "Could not bundle pip into embedded Python." }

    $Files = @(
        "grab.py", "grab_config.py", "grab_models.py", "grab_sites.py", "grab_state.py", "grab_storage.py",
        "webui.py", "portable_bootstrap.py", "portable_launcher.py", "portable_manifest.json", "README.md",
        "THIRD_PARTY_NOTICES.md"
    )
    foreach ($File in $Files) {
        Copy-Item -LiteralPath (Join-Path $RepoRoot $File) -Destination (Join-Path $App $File)
    }
    Copy-Item -Recurse -LiteralPath (Join-Path $RepoRoot "webui_dist") -Destination (Join-Path $App "webui_dist")
    Get-ChildItem -LiteralPath (Join-Path $RepoRoot "portable") -Filter "*.cmd" | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $App $_.Name)
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $App "downloads"), (Join-Path $App "data\config") | Out-Null

    $ZipName = "video-grabber-windows-x64-portable.zip"
    $ZipPath = Join-Path $OutputRoot $ZipName
    if (Test-Path -LiteralPath $ZipPath) { Remove-Item -LiteralPath $ZipPath }
    Compress-Archive -LiteralPath $App -DestinationPath $ZipPath -CompressionLevel Optimal
    $ZipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZipPath).Hash.ToLowerInvariant()
    Set-Content -LiteralPath ($ZipPath + ".sha256") -Encoding ASCII -Value "$ZipHash  $ZipName"
    Write-Host "Created $ZipPath"
    Write-Host "SHA-256 $ZipHash"
}
finally {
    $ResolvedOutput = [System.IO.Path]::GetFullPath($OutputRoot)
    $ResolvedStage = [System.IO.Path]::GetFullPath($Stage)
    if ($ResolvedStage.StartsWith($ResolvedOutput + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $ResolvedStage)) {
        Remove-Item -Recurse -Force -LiteralPath $ResolvedStage
    }
}
