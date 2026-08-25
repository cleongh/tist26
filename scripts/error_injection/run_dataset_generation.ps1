<#
.SYNOPSIS
    Runs the error-injection dataset generation pipeline for a predefined set
    of errors-per-story values.

.DESCRIPTION
    Edit $ErrorsPerStoryValues below to change which values get run. Each
    value is passed to:
        python -m scripts.error_injection.dataset_generation <value>
    A run failure is logged and the script continues on to the next value.
#>

# Errors-per-story values to run, in order. Edit this list as needed.
$ErrorsPerStoryValues = @(15, 25, 65, 220)

# Resolve the repository root: scripts/error_injection/ -> scripts/ -> root
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")

Push-Location $RepoRoot
try {
    foreach ($errorsPerStory in $ErrorsPerStoryValues) {
        Write-Host "=== Running dataset_generation with errors_per_story=$errorsPerStory ===" -ForegroundColor Cyan
        python -m scripts.error_injection.dataset_generation $errorsPerStory
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "dataset_generation failed for errors_per_story=$errorsPerStory (exit code $LASTEXITCODE)"
        }
    }
} finally {
    Pop-Location
}
