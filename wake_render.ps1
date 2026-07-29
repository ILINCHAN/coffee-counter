# ============================================================
# 咖啡机计数 - Render 自动唤醒脚本 (Windows)
# 作用: 每 10 分钟检查一次, 若 Render 处于休眠(无响应)就自动访问首页唤醒
# 用法:
#   1. 把本文件保存到任意位置, 例如 C:\wake\wake_render.ps1
#   2. 右键"使用 PowerShell 运行"  (或直接双击若已关联)
#   3. 想 24h 自动跑: 用任务计划程序设为"每隔 10 分钟"启动本脚本
# ============================================================

$URL      = "https://coffee-counter-qxim.onrender.com"
$LOG      = "$PSScriptRoot\wake_render.log"
$Timeout  = 12   # 秒, 超过这个时间没响应就认为是休眠

function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Tee-Object -FilePath $LOG -Append
}

try {
    Log "检查 $URL ..."
    $r = Invoke-WebRequest -Uri $URL -TimeoutSec $Timeout -UseBasicParsing -ErrorAction Stop
    if ($r.StatusCode -eq 200) {
        Log "✅ 在线 (HTTP $($r.StatusCode))，无需唤醒"
    } else {
        Log "⚠️ 返回 $($r.StatusCode)，尝试唤醒..."
        # 再次访问一次触发冷启动
        Invoke-WebRequest -Uri $URL -TimeoutSec 40 -UseBasicParsing -ErrorAction Stop | Out-Null
        Log "🔄 已触发唤醒请求"
    }
}
catch {
    # 超时 / 连接失败 = 休眠中, 触发一次访问让它冷启动
    Log "😴 疑似休眠/无响应，正在唤醒..."
    try {
        Invoke-WebRequest -Uri $URL -TimeoutSec 45 -UseBasicParsing -ErrorAction Stop | Out-Null
        Log "🔄 唤醒请求已发出（约 30-60 秒后上线）"
    }
    catch {
        Log "❌ 唤醒失败: $($_.Exception.Message)"
    }
}

# 顺便验证中央数据库(Turso)是否通
try {
    $h = Invoke-WebRequest -Uri "$URL/api/health" -TimeoutSec $Timeout -UseBasicParsing -ErrorAction Stop
    Log "健康检查: $($h.Content)"
}
catch {
    Log "⚠️ /api/health 暂不可达（可能还在冷启动）"
}
