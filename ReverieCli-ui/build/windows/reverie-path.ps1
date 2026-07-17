param(
    [Parameter(Mandatory = $true)][string]$InstallDir,
    [switch]$Remove
)

function Normalize-PathEntry([string]$Value) {
    try {
        return [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($Value)).TrimEnd('\')
    }
    catch {
        return $Value.Trim().TrimEnd('\')
    }
}

$normalized = Normalize-PathEntry $InstallDir
$current = [Environment]::GetEnvironmentVariable('Path', 'User')
$entries = @($current -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
$entries = @($entries | Where-Object {
    -not [string]::Equals((Normalize-PathEntry $_), $normalized, [StringComparison]::OrdinalIgnoreCase)
})
if (-not $Remove) {
    $entries += $normalized
}
[Environment]::SetEnvironmentVariable('Path', ($entries -join ';'), 'User')
