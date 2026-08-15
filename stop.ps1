# 一键停止 - 智能客服系统
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  智能客服系统 - 一键停止脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Docker 是否运行
try {
    docker info *> $null
} catch {
    Write-Host "[提示] Docker 未运行，无需停止" -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 0
}

Write-Host "[1/2] 停止所有服务 (保留数据卷)..." -ForegroundColor Yellow
Write-Host ""
docker compose down
if ($LASTEXITCODE -ne 0) {
    Write-Host "[警告] 部分服务停止失败，尝试强制停止..." -ForegroundColor Yellow
    docker compose down --remove-orphans
}

Write-Host ""
Write-Host "[2/2] 清理残留容器..." -ForegroundColor Yellow
$residual = docker ps --filter "name=cs_" --format "{{.Names}}" 2>$null
if ($residual) {
    $residual | ForEach-Object {
        Write-Host "  清理容器: $_" -ForegroundColor Gray
        docker rm -f $_ *> $null
    }
} else {
    Write-Host "  无残留容器" -ForegroundColor Gray
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  系统已停止!" -ForegroundColor Green
Write-Host "----------------------------------------" -ForegroundColor Green
Write-Host "  数据卷已保留，重新启动后数据不变" -ForegroundColor White
Write-Host "  如需彻底清除数据，请运行:" -ForegroundColor White
Write-Host "    docker compose down -v" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Read-Host "按回车键退出"