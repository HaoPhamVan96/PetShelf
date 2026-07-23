$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git was not found in PATH. Install Git for Windows first."
}

$versionLine = Select-String -Path "pyproject.toml" -Pattern '^version = "([^"]+)"$'
if (-not $versionLine) {
    throw "Could not read version from pyproject.toml."
}

$currentVersion = $versionLine.Matches.Groups[1].Value
$parts = $currentVersion.Split('.')
if ($parts.Count -ne 3) {
    throw "Expected a three-part version such as 1.0.0, got $currentVersion."
}
$nextVersion = "{0}.{1}.{2}" -f [int]$parts[0], [int]$parts[1], ([int]$parts[2] + 1)
$tag = "v$nextVersion"

$pendingChanges = @(git status --porcelain)
Write-Host "Current version: $currentVersion"
Write-Host "New version:     $nextVersion"
if ($pendingChanges.Count -gt 0) {
    Write-Host "Pending changes detected: they will be included in the release commit."
} else {
    Write-Host "No pending source changes: only the version bump will be committed."
}

$answer = Read-Host "Create and push release $tag? [Y/N]"
if ($answer -notmatch '^(y|yes)$') {
    Write-Host "Cancelled."
    exit 0
}

$pyprojectPath = Join-Path $Root "pyproject.toml"
$pyproject = Get-Content -Raw $pyprojectPath
$pyproject = [regex]::Replace($pyproject, '(?m)^version = "[^"]+"$', "version = `"$nextVersion`"", 1)
[IO.File]::WriteAllText($pyprojectPath, $pyproject, [Text.UTF8Encoding]::new($false))

$initPath = Join-Path $Root "pet_shelf\__init__.py"
$init = Get-Content -Raw $initPath
$init = [regex]::Replace($init, '__version__ = "[^"]+"', "__version__ = `"$nextVersion`"", 1)
[IO.File]::WriteAllText($initPath, $init, [Text.UTF8Encoding]::new($false))

git add -A
if ($LASTEXITCODE -ne 0) { throw "git add failed." }

git commit -m "Release $tag"
if ($LASTEXITCODE -ne 0) { throw "git commit failed. The tag was not created." }

git push origin HEAD
if ($LASTEXITCODE -ne 0) { throw "Code push failed. The tag was not created." }

if (git tag --list $tag) {
    throw "Tag $tag already exists locally. No duplicate tag was pushed."
}
git tag $tag
if ($LASTEXITCODE -ne 0) { throw "Tag creation failed." }

git push origin $tag
if ($LASTEXITCODE -ne 0) { throw "Tag push failed." }

Write-Host ""
Write-Host "Release $tag pushed successfully."
Write-Host "GitHub Actions will now build Windows and macOS packages."
