# 咖啡机计数 - 自动唤醒 + 使用说明

## 一、现状
- 主链接(免费, 7×24 数据, 偶尔休眠): **https://coffee-counter-qxim.onrender.com**
- 中央数据库: Turso 免费云 SQLite (数据永久不丢, 已验证累计 48 次)
- 免费版 Render 每 15 分钟无访问会休眠 → 打开会卡几秒或显示 000, 访问一次即醒

## 二、自动唤醒 (推荐: GitHub Actions, 零成本, 不需你电脑开机)

文件: `.github/workflows/keepalive.yml` 已在本仓库。

步骤(你来做, 一次性):
1. 在 GitHub 仓库 `ILINCHAN/coffee-counter` 里, 确认 `.github/workflows/keepalive.yml` 已存在
   (若没有, 就在仓库里新建该路径文件, 内容见本仓库同路径)
2. 打开仓库页面 → 顶部 **Actions** 标签 → 若提示 "Workflows aren't enabled", 点 **I understand... enable** 启用
3. 左侧找到 **Keep Render Alive** → 右侧 **Run workflow** 手动跑一次测试
4. 之后每 10 分钟 GitHub 自动访问你的 Render, 它就不会睡了
   (public 仓库 Actions 免费无限; private 仓库每月 2000 分钟也够用)

验证: 跑完一次后, 访问 https://coffee-counter-qxim.onrender.com/api/health
应返回 `{"db":"turso","turso_ok":true,...}`

## 三、备选: 你家 Windows 电脑常开时

文件: `wake_render.ps1` + `setup_task.ps1`
1. 把这俩文件放同一文件夹 (如 C:\wake\)
2. **右键 setup_task.ps1 → 使用 PowerShell 运行(管理员)** → 自动注册"每10分钟"计划任务
3. 日志在 C:\wake\wake_render.log
注意: 电脑关机/睡眠时此方案不生效, 优先用上面的 GitHub Actions。

## 四、图标(添加到主屏幕) 老是不显示小猫?

iOS 缓存问题, 不是代码问题。图标文件已验证是小猫 (apple-touch-icon.png = 21053 字节)。
解决:
1. 长按主屏上的旧图标 → 移除
2. 设置 → Safari → 清除历史记录与网站数据
3. 用 Safari 重新打开 https://coffee-counter-qxim.onrender.com
4. 底部分享 → 添加到主屏幕 → 这次是小猫

## 五、最终链接

👉 **https://coffee-counter-qxim.onrender.com**

数据所有人共享、永久保存(Beijing 时间)、支持备注。
