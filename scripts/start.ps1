<#
  Reading-English-Web 一键启动
  用法：.\scripts\start.ps1  [-SkipContainers]

  启动前会先把占用 5173 / 8010 / 8020 的残留进程清掉，
  启动后逐个探活，失败的服务会直接点名并提示看日志。
#>
param(
    [switch]$SkipContainers
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root ".runtime\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Free-Port($port) {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        & taskkill /PID $c.OwningProcess /T /F 2>$null | Out-Null
        Write-Host "    端口 $port 已被占用，残留进程 PID $($c.OwningProcess) 已清理" -ForegroundColor DarkGray
    }
}

function Start-Proc($name, $workdir, $exe, $argList) {
    $out = Join-Path $logs "$name.out.log"
    $err = Join-Path $logs "$name.err.log"
    $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $workdir `
        -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
    Set-Content -Path (Join-Path $logs "$name.pid") -Value $p.Id
    Write-Host "    $name -> PID $($p.Id)   日志: $out" -ForegroundColor DarkGray
}

function Probe($name, $url, $errLog) {
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10
        Write-Host ("    {0,-12} OK   HTTP {1}" -f $name, $r.StatusCode) -ForegroundColor Green
    } catch {
        Write-Host ("    {0,-12} 启动失败！看日志: {1}" -f $name, $errLog) -ForegroundColor Red
    }
}

Write-Step "0/5 清理端口占用"
foreach ($port in @(5173, 8010, 8020)) { Free-Port $port }

Write-Step "1/5 数据底座 Supabase"
Push-Location (Join-Path $root "Reading-DB-Supabase")
try {
    $running = docker ps --filter "name=supabase_db" --format "{{.Names}}" 2>$null
    if ($running) {
        Write-Host "    已在运行，跳过" -ForegroundColor DarkGray
    } else {
        supabase start | Out-Host
    }
} finally { Pop-Location }

if (-not $SkipContainers) {
    Write-Step "2/5 外部依赖 SearXNG / Crawl4AI"
    # 这两个服务由本机的共享栈 searxng-crawl4ai 提供，这里只探活，
    # 不代管它们的生命周期 —— 那是共享栈自己的事。
    foreach ($dep in @(
        @{ Name = "SearXNG";  Url = "http://127.0.0.1:8080/" },
        @{ Name = "Crawl4AI"; Url = "http://127.0.0.1:11235/health" }
    )) {
        try {
            $r = Invoke-WebRequest -Uri $dep.Url -UseBasicParsing -TimeoutSec 5
            Write-Host ("    {0,-10} OK   HTTP {1}" -f $dep.Name, $r.StatusCode) -ForegroundColor Green
        } catch {
            Write-Host ("    {0,-10} 不可达（{1}）" -f $dep.Name, $dep.Url) -ForegroundColor Yellow
            Write-Host "        在共享栈目录执行： docker compose up -d" -ForegroundColor DarkGray
        }
    }
    Write-Host "    缺失不阻塞：检索有 RSS 兜底通道，网页清洗有内置降级提取器" -ForegroundColor DarkGray
} else {
    Write-Step "2/5 外部依赖（跳过）"
}

Write-Step "3/5 采集服务 :8020"
$py = Join-Path $root "Reading-Material-Crawler-Service\.venv\Scripts\python.exe"
if (Test-Path $py) {
    Start-Proc "crawler" (Join-Path $root "Reading-Material-Crawler-Service") $py `
        @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8020")
} else {
    Write-Host "    缺少虚拟环境，请先在 Reading-Material-Crawler-Service 里建 .venv" -ForegroundColor Yellow
}

Write-Step "4/5 生成服务 :8010"
$py2 = Join-Path $root "Reading-Article-Generate-Service\.venv\Scripts\python.exe"
if (Test-Path $py2) {
    Start-Proc "generator" (Join-Path $root "Reading-Article-Generate-Service") $py2 `
        @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8010")
} else {
    Write-Host "    缺少虚拟环境，请先在 Reading-Article-Generate-Service 里建 .venv" -ForegroundColor Yellow
}

Write-Step "5/5 前端 :5173"
$npm = (Get-Command npm -ErrorAction SilentlyContinue)
if ($npm) {
    $out = Join-Path $logs "frontend.out.log"
    $err = Join-Path $logs "frontend.err.log"
    $p = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") `
        -WorkingDirectory (Join-Path $root "Reading-Web-Frontend") `
        -RedirectStandardOutput $out -RedirectStandardError $err -PassThru -WindowStyle Hidden
    Set-Content -Path (Join-Path $logs "frontend.pid") -Value $p.Id
    Write-Host "    frontend -> PID $($p.Id)" -ForegroundColor DarkGray
} else {
    Write-Host "    未找到 npm" -ForegroundColor Yellow
}

Write-Step "等待服务就绪"
Start-Sleep -Seconds 6
Probe "前端"       "http://127.0.0.1:5173/"         (Join-Path $logs "frontend.err.log")
Probe "采集服务"   "http://127.0.0.1:8020/health"  (Join-Path $logs "crawler.err.log")
Probe "生成服务"   "http://127.0.0.1:8010/health"  (Join-Path $logs "generator.err.log")
Probe "Supabase"   "http://127.0.0.1:54321/rest/v1/" (Join-Path $logs "supabase.log")

Write-Step "启动完成"
Write-Host "  前端      http://127.0.0.1:5173/" -ForegroundColor Green
Write-Host "  采集管理台 http://127.0.0.1:8020/" -ForegroundColor Green
Write-Host "  生成服务文档 http://127.0.0.1:8010/docs" -ForegroundColor Green
Write-Host "  停止全部：.\scripts\stop.ps1" -ForegroundColor DarkGray
