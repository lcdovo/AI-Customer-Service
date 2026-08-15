# 一键启动 - 智能客服系统
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  智能客服系统 - 一键启动脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Docker 是否运行
try {
    docker info *> $null
} catch {
    Write-Host "[错误] Docker 未启动，请先启动 Docker Desktop" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

Write-Host "[1/4] 构建并启动所有服务..." -ForegroundColor Yellow
Write-Host ""
docker compose up -d --build
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 服务启动失败" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

Write-Host ""
Write-Host "[2/4] 等待基础服务就绪..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

Write-Host ""
Write-Host "[3/4] 检查服务健康状态..." -ForegroundColor Yellow
Write-Host ""
docker compose ps

Write-Host ""
Write-Host "[4/4] 验证应用服务..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -UseBasicParsing
    Write-Host "[成功] 应用服务已就绪!" -ForegroundColor Green
} catch {
    Write-Host "[警告] 应用服务可能仍在启动中，请稍候刷新" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  系统启动完成!" -ForegroundColor Green
Write-Host "----------------------------------------" -ForegroundColor Green
Write-Host "  前端页面: http://localhost:8000" -ForegroundColor White
Write-Host "  API 文档: http://localhost:8000/docs" -ForegroundColor White
Write-Host "  用户账号: user001 / password" -ForegroundColor White
Write-Host "  管理员:   admin / admin123" -ForegroundColor White
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "按任意键打开浏览器..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
Start-Process "http://localhost:8000"