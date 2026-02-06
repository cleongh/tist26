#
# Narrative Logic Engine - Full Experiment Runner (OpenAI API)
# =============================================================
#
# This script runs the complete narrative experiment pipeline using OpenAI API.
#
# Prerequisites:
#   1. Set your OpenAI API key:
#      $env:OPENAI_API_KEY = "your-api-key"
#
#   2. Install Python dependencies:
#      pip install -r requirements.txt
#
# Usage:
#   .\run_experiment_openai.ps1 [experiment_name] [options]
#
# Options:
#   -Stories "Story1","Story2"    Process specific stories (default: all)
#   -MaxChapters N                Limit chapters per story (default: all)
#   -Model MODEL                  OpenAI model (default: gpt-4o)
#   -ApiDelay SECONDS             Delay between API calls (default: 0.5)
#   -SkipStep1                    Skip Step 1 (LLM-only evaluation)
#   -SkipStep2                    Skip Step 2 (Logic evaluation)
#   -Quick                        Quick test: 3 chapters only
#
# Examples:
#   .\run_experiment_openai.ps1 my_experiment
#   .\run_experiment_openai.ps1 test_run -Quick
#   .\run_experiment_openai.ps1 hp_only -Stories "Harry Potter" -MaxChapters 5
#

param(
    [Parameter(Position=0)]
    [string]$ExperimentName = "openai_experiment_$(Get-Date -Format 'yyyyMMdd_HHmmss')",
    
    [string]$Model = "gpt-4o",
    
    [double]$ApiDelay = 0.5,
    
    [int]$MaxChapters = 0,
    
    [string[]]$Stories = @(),
    
    [switch]$SkipStep1,
    
    [switch]$SkipStep2,
    
    [switch]$Quick,
    
    [int]$LlmTimeout = 300,
    
    [int]$IlaspTimeout = 60,
    
    [switch]$NoSplit
)

# =============================================================================
# CONFIGURATION
# =============================================================================

$ErrorActionPreference = "Stop"

if ($Quick) {
    $MaxChapters = 3
}

$UseSplitExtraction = -not $NoSplit

# =============================================================================
# VALIDATION
# =============================================================================

# Check for OpenAI API key
if (-not $env:OPENAI_API_KEY) {
    Write-Host "ERROR: OPENAI_API_KEY environment variable not set" -ForegroundColor Red
    Write-Host ""
    Write-Host "Set it with:"
    Write-Host '  $env:OPENAI_API_KEY = "your-api-key"'
    Write-Host ""
    exit 1
}

# Get script directory and repo root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Check Python dependencies
Write-Host "Checking Python dependencies..."
try {
    python -c "import openai" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "openai not found"
    }
} catch {
    Write-Host "ERROR: openai package not installed" -ForegroundColor Red
    Write-Host "Install with: pip install openai"
    exit 1
}

# =============================================================================
# BUILD COMMAND OPTIONS
# =============================================================================

$CmdOpts = @(
    "--api-mode", "openai",
    "--api-model", $Model,
    "--api-delay", $ApiDelay,
    "--llm-timeout", $LlmTimeout,
    "--ilasp-timeout", $IlaspTimeout
)

if ($MaxChapters -gt 0) {
    $CmdOpts += "--max-chapters"
    $CmdOpts += $MaxChapters
}

# =============================================================================
# RUN EXPERIMENT
# =============================================================================

Write-Host ""
Write-Host "============================================================"
Write-Host "  NARRATIVE LOGIC ENGINE - OPENAI EXPERIMENT"
Write-Host "============================================================"
Write-Host ""
Write-Host "  Experiment:   $ExperimentName"
Write-Host "  Model:        $Model"
Write-Host "  API Delay:    ${ApiDelay}s"
Write-Host "  Max Chapters: $(if ($MaxChapters -gt 0) { $MaxChapters } else { 'all' })"
Write-Host "  Stories:      $(if ($Stories.Count -gt 0) { $Stories -join ', ' } else { 'all' })"
Write-Host "  Split Extract: $UseSplitExtraction"
Write-Host "  LLM Timeout:  ${LlmTimeout}s"
Write-Host "  ILASP Timeout: ${IlaspTimeout}s"
Write-Host ""
Write-Host "============================================================"
Write-Host ""

$StartTime = Get-Date

# Step 1: LLM-only evaluation
if (-not $SkipStep1) {
    Write-Host ""
    Write-Host "[STEP 1] LLM-Only Evaluation"
    Write-Host "------------------------------------------------------------"
    
    $Step1Args = @(
        "scripts/run_narrative_experiment_refactored.py",
        "--experiment-name", $ExperimentName,
        "--step", "1"
    ) + $CmdOpts
    
    if ($Stories.Count -gt 0) {
        $Step1Args += "--stories"
        $Step1Args += $Stories
    }
    
    python @Step1Args
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Step 1 failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    
    Write-Host ""
    Write-Host "[STEP 1] Complete"
    Write-Host ""
}

# Step 2: Logic-based evaluation with engine
if (-not $SkipStep2) {
    Write-Host ""
    Write-Host "[STEP 2] Logic-Based Evaluation (Engine Mode)"
    Write-Host "------------------------------------------------------------"
    
    $Step2Args = @(
        "scripts/run_narrative_experiment_refactored.py",
        "--experiment-name", $ExperimentName,
        "--step", "2",
        "--engine"
    )
    
    if ($UseSplitExtraction) {
        $Step2Args += "--split-extraction"
    }
    
    $Step2Args += $CmdOpts
    
    if ($Stories.Count -gt 0) {
        $Step2Args += "--stories"
        $Step2Args += $Stories
    }
    
    python @Step2Args
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Step 2 failed with exit code $LASTEXITCODE" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    
    Write-Host ""
    Write-Host "[STEP 2] Complete"
    Write-Host ""
}

# Generate summary
Write-Host ""
Write-Host "[SUMMARY] Generating Experiment Summary"
Write-Host "------------------------------------------------------------"

python scripts/run_narrative_experiment_refactored.py `
    --experiment-name $ExperimentName `
    --summarize

$EndTime = Get-Date
$Duration = $EndTime - $StartTime
$Minutes = [math]::Floor($Duration.TotalMinutes)
$Seconds = $Duration.Seconds

Write-Host ""
Write-Host "============================================================"
Write-Host "  EXPERIMENT COMPLETE"
Write-Host "============================================================"
Write-Host ""
Write-Host "  Duration:     ${Minutes}m ${Seconds}s"
Write-Host "  Results:      experiments/$ExperimentName/"
Write-Host ""
Write-Host "  Key files:"
Write-Host "    - step1_llm_results.json    (LLM-only errors)"
Write-Host "    - step2_logic_results.json  (Logic-based errors)"
Write-Host "    - experiment_summary.json   (Comparison)"
Write-Host "    - full_console_log.txt      (Complete log)"
Write-Host ""
Write-Host "============================================================"
