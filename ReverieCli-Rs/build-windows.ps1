param(
    [switch]$Release,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $root
$profile = if ($Release) { "release" } else { "debug" }
$cargoArgs = @("build", "-p", "reverie-cli")
if ($Release) {
    $cargoArgs += "--release"
}

Push-Location $root
try {
    cargo fmt --check
    if (-not $SkipTests) {
        cargo test --workspace
    }
    cargo @cargoArgs

    $source = Join-Path $root "target\$profile\reverie.exe"
    if (-not (Test-Path $source)) {
        throw "Cargo completed without producing $source"
    }

    $dist = Join-Path $repoRoot "dist"
    New-Item -ItemType Directory -Force -Path $dist | Out-Null
    Copy-Item -LiteralPath $source -Destination (Join-Path $dist "reverie.exe") -Force
    & (Join-Path $dist "reverie.exe") --version
}
finally {
    Pop-Location
}
