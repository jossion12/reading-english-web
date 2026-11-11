<#
  Reading-English-Web 状态检查
#>
$root = Split-Path -Parent $PSScriptRoot

function Probe($name, $url) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
        Write-Host ("  {0,-22} {1,-38} HTTP {2}" -f $name, $url, $r.StatusCode) -ForegroundColor Green
    } catch {
        Write-Host ("  {0,-22} {1,-38} 不可达" -f $name, $url) -ForegroundColor DarkYellow
    }
}

Write-Host "服务状态" -ForegroundColor Cyan
Probe "前端"          "http://127.0.0.1:5173/"
Probe "采集服务"      "http://127.0.0.1:8020/health"
Probe "采集管理台"    "http://127.0.0.1:8020/"
Probe "生成服务"      "http://127.0.0.1:8010/health"
Probe "Supabase API"  "http://127.0.0.1:54321/rest/v1/"
Probe "SearXNG"       "http://127.0.0.1:8080/"

Write-Host "`n容器" -ForegroundColor Cyan
$containers = docker ps --format "{{.Names}}`t{{.Status}}" 2>$null
if ($containers) { $containers | ForEach-Object { Write-Host "  $_" } }
else { Write-Host "  （无运行中的容器）" -ForegroundColor DarkGray }

Write-Host "`nOllama 模型" -ForegroundColor Cyan
$models = (ollama list 2>$null | Select-Object -Skip 1)
if ($models) { $models | ForEach-Object { Write-Host "  $_" } }
else { Write-Host "  （未检测到 ollama）" -ForegroundColor DarkGray }
