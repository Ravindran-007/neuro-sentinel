#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Deploy Level 2 NeuroSentinel services with docker-compose
    
.DESCRIPTION
    Starts Redis, Ollama, and FastAPI security service
    Includes health checks and verification steps
    
.EXAMPLE
    .\deploy_level2.ps1
#>

Write-Host "`n╔════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║               🚀 LEVEL 2 DEPLOYMENT - NeuroSentinel Lite                  ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════════════════╝`n" -ForegroundColor Cyan

# Check if docker is running
Write-Host "🔍 Checking Docker daemon..." -ForegroundColor Yellow
try {
    $dockerCheck = docker ps 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ Docker is running`n" -ForegroundColor Green
    } else {
        Write-Host "❌ Docker daemon not responding`n" -ForegroundColor Red
        Write-Host "   Fix: Start Docker Desktop`n" -ForegroundColor Gray
        exit 1
    }
} catch {
    Write-Host "❌ Docker not found`n" -ForegroundColor Red
    exit 1
}

# Check if docker-compose exists
Write-Host "🔍 Checking docker-compose..." -ForegroundColor Yellow
try {
    $composeVersion = docker-compose --version 2>&1
    Write-Host "✅ docker-compose found: $composeVersion`n" -ForegroundColor Green
} catch {
    Write-Host "❌ docker-compose not found`n" -ForegroundColor Red
    exit 1
}

# Navigate to project directory
$projectDir = "e:\neuro_sentinel"
if (-not (Test-Path $projectDir)) {
    Write-Host "❌ Project directory not found: $projectDir`n" -ForegroundColor Red
    exit 1
}

Set-Location $projectDir
Write-Host "📁 Working directory: $projectDir`n" -ForegroundColor Cyan

# Start services
Write-Host "🐳 Starting Level 2 services...`n" -ForegroundColor Yellow
Write-Host "   ├─ Redis (state management)" -ForegroundColor Gray
Write-Host "   ├─ Ollama (LLM inference)" -ForegroundColor Gray
Write-Host "   └─ FastAPI (security service)`n" -ForegroundColor Gray

docker-compose up --build

Write-Host "`n╔════════════════════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║                    ⏹️  SERVICES STOPPED                                    ║" -ForegroundColor Cyan
Write-Host "╚════════════════════════════════════════════════════════════════════════════╝`n" -ForegroundColor Cyan

Write-Host "💡 To verify in a new terminal, run:`n" -ForegroundColor Yellow
Write-Host "   curl http://localhost:8000/api/health`n" -ForegroundColor Cyan
Write-Host "   pytest tests/test_security_service.py -v`n" -ForegroundColor Cyan
Write-Host "   docker ps`n" -ForegroundColor Cyan
