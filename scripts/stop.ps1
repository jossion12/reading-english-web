<#
  Reading-English-Web 停止全部
  用法：.\scripts\stop.ps1  [-KeepContainers]

  注意：这里会「杀进程树 + 按端口兜底」两层清理。
  原因：启动器不是服务本身——npm.cmd 的子进程是 node(vite)，
  venv 里的 python.exe 也只是个壳，真正监听端口的是它的子进程。
  只杀 PID 记录会留下占着端口的孤儿进程，下次启动就会报
  「Port 5173 is already in use」。
#>
param(
    [switch]$KeepContainers
)

$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root ".runtime\logs"

# 本项目三个服务独占的端口，停止时按端口再兜一遍
$ServicePorts = @{ frontend = 5173; generator = 8010; crawler = 8020 }

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }

function Stop-Tree($name, $procId) {
    if (-not $procId) { return }
    # /T 连子进程一起杀
    & taskkill /PID $procId /T /F 2>$null | Out-Null
    if (Get-Process -Id $procId -ErrorAction SilentlyContinue) {
        Write-Host "    $name (PID $procId) 停止失败" -ForegroundColor Yellow
    } else {
        Write-Host "    $name (PID $procId) 已停止" -ForegroundColor DarkGray
    }
}

function Stop-ByPort($name, $port) {
    $conns = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    foreach ($c in $conns) {
        & taskkill /PID $c.OwningProcess /T /F 2>$null | Out-Null
        Write-Host "    $name 端口 $port 残留进程 PID $($c.OwningProcess) 已清理" -ForegroundColor DarkGray
    }
}

foreach ($name in @("frontend", "generator", "crawler")) {
    $pidFile = Join-Path $logs "$name.pid"
    if (Test-Path $pidFile) {
        $procId = (Get-Content $pidFile | Select-Object -First 1)
        Stop-Tree $name $procId
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    } else {
        Write-Host "    $name 无 pid 记录" -ForegroundColor DarkGray
    }
    Stop-ByPort $name $ServicePorts[$name]
}

if (-not $KeepContainers) {
    Write-Step "停止容器"
    # 只停本项目「独立部署模式」起的 reading-searxng。
    # 共享栈 searxng-crawl4ai 里的 searxng / crawl4ai 不归本脚本管，别误杀。
    Push-Location (Join-Path $root "Reading-Material-Crawler-Service\deploy")
    try { docker compose --profile standalone stop searxng | Out-Null } catch { } finally { Pop-Location }

    Push-Location (Join-Path $root "Reading-DB-Supabase")
    try { supabase stop | Out-Null } catch { } finally { Pop-Location }
} else {
    Write-Step "容器保持运行（-KeepContainers）"
}

Write-Host "已停止。" -ForegroundColor Cyan
