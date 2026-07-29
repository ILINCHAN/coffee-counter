#!/bin/bash
# 本地启动脚本：读取 .env.local 的 Turso 配置，启动 gunicorn
# 用法：bash start_local.sh
cd "$(dirname "$0")"

# 读取 .env.local
if [ -f .env.local ]; then
  export $(grep -v '^#' .env.local | grep -E 'TURSO_URL|TURSO_TOKEN' | xargs)
fi

# 若 token 还是占位符，提示但未阻断（会用本地 SQLite fallback）
if [ "$TURSO_TOKEN" = "在这里粘贴你的token" ] || [ -z "$TURSO_TOKEN" ]; then
  echo "⚠️  未配置 TURSO_TOKEN，将使用本地 SQLite（数据不持久）"
  echo "   编辑 .env.local 填入你的 token 后重新运行"
fi

export PATH="/root/.pyenv/versions/3.11.1/bin:$PATH"
pkill -f "gunicorn app:app" 2>/dev/null
sleep 1
nohup gunicorn app:app --bind 0.0.0.0:5000 --workers 1 --timeout 30 \
  --log-file /tmp/g_local.log --pid /tmp/g_local.pid > /dev/null 2>&1 &
sleep 2
echo "=== health ==="
curl -s --max-time 5 http://127.0.0.1:5000/api/health
echo ""
echo "本地服务已启动：http://127.0.0.1:5000"
