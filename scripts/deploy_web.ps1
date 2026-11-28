# 构建并部署 Web 客户端到线上服务器
# 用法：powershell -ExecutionPolicy Bypass -File scripts/deploy_web.ps1
param(
    [string]$Server = "root@39.99.41.233",
    [string]$KeyPath = "$env:USERPROFILE\.ssh\ali_mcp",
    [string]$RemoteDir = "/www/wwwroot/GradeManager/web"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$web = Join-Path $root "web"
$tar = Join-Path $env:TEMP "gm_web_dist.tar.gz"

Write-Host "== build ==" -ForegroundColor Cyan
Push-Location $web
npm run build
if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
if (Test-Path $tar) { Remove-Item $tar -Force }
tar -czf $tar -C (Join-Path $web "dist") .
Pop-Location

Write-Host "== upload ==" -ForegroundColor Cyan
scp -i $KeyPath $tar "${Server}:/tmp/gm_web_dist.tar.gz"

Write-Host "== deploy ==" -ForegroundColor Cyan
ssh -i $KeyPath $Server "mkdir -p $RemoteDir/dist && find $RemoteDir/dist -mindepth 1 -maxdepth 1 ! -name .user.ini -exec rm -rf {} + && tar -xzf /tmp/gm_web_dist.tar.gz -C $RemoteDir/dist && chown -R grademanager:grademanager $RemoteDir 2>/dev/null || true; grep -o '<title>[^<]*</title>' $RemoteDir/dist/index.html"
if ($LASTEXITCODE -ne 0) { throw "remote deploy failed" }

Write-Host "done: https://grade.yfy0109.top" -ForegroundColor Green
