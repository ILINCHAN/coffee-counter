# ============================================================
# 一键注册"每10分钟自动唤醒 Render"的 Windows 计划任务
# 以管理员身份运行本脚本一次即可 (右键 -> 使用 PowerShell 运行)
# ============================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$WakeScript = Join-Path $ScriptDir "wake_render.ps1"
$TaskName   = "CoffeeCounterWakeRender"

if (-not (Test-Path $WakeScript)) {
    Write-Host "❌ 找不到 $WakeScript" -ForegroundColor Red
    pause
    exit 1
}

# 创建任务: 每 10 分钟跑一次, 不论是否登录、最高权限
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WakeScript`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action `
    -Trigger $Trigger -Settings $settings -Force

Write-Host "✅ 已创建计划任务 '$TaskName'，每 10 分钟自动唤醒。" -ForegroundColor Green
Write-Host "日志在: $ScriptDir\wake_render.log" -ForegroundColor Cyan
pause
