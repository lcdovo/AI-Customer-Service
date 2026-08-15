# 查看服务状态 - 智能客服系统
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  智能客服系统 - 服务状态" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Docker 是否运行
try {
    docker info *> $null
} catch {
    Write-Host "[错误] Docker 未启动" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

Write-Host "--- 容器运行状态 ---" -ForegroundColor Yellow
docker compose ps

Write-Host ""
Write-Host "--- 端口占用 ---" -ForegroundColor Yellow
$ports = @(8000, 3306, 6379, 19531, 9002, 2380)
foreach ($port in $ports) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Write-Host "  端口 $port : 占用中" -ForegroundColor Green
    } else {
        Write-Host "  端口 $port : 空闲" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "--- 健康检查 ---" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 3 -UseBasicParsing
    $content = $response.Content | ConvertFrom-Json
    Write-Host "  应用状态: $($content.status)" -ForegroundColor Green
    Write-Host "  应用名称: $($content.app)" -ForegroundColor Green
    Write-Host "  版本: $($content.version)" -ForegroundColor Green
} catch {
    Write-Host "  应用: 未就绪" -ForegroundColor Red
}

Write-Host ""
Write-Host "--- 知识库统计 ---" -ForegroundColor Yellow
try {
    $response = Invoke-WebRequest -Uri "http://localhost:8000/api/v1/knowledge/stats" -TimeoutSec 3 -UseBasicParsing
    $content = $response.Content | ConvertFrom-Json
    Write-Host "  文档数量: $($content.data.total_documents)" -ForegroundColor Green
    Write-Host "  分块数量: $($content.data.total_chunks)" -ForegroundColor Green
} catch {
    Write-Host "  知识库: 未就绪" -ForegroundColor Red
}

Write-Host ""
Read-Host "按回车键退出"