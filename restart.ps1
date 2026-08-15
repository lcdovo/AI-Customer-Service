# 一键重启 - 智能客服系统
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  智能客服系统 - 一键重启脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host ">>> 正在停止服务..." -ForegroundColor Yellow
& "$PSScriptRoot\stop.ps1"

Write-Host ""
Write-Host ">>> 等待服务完全停止..." -ForegroundColor Gray
Start-Sleep -Seconds 3

Write-Host ""
Write-Host ">>> 正在启动服务..." -ForegroundColor Yellow
& "$PSScriptRoot\start.ps1"