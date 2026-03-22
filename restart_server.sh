#!/bin/bash

# ============================================
# 基金监控服务重启脚本
# ============================================

echo "🔄 开始重启服务..."

# 查找并杀死现有 Python 进程
echo "停止现有进程..."
pkill -f "uvicorn main:app" || echo "没有找到现有进程"

# 等待进程完全关闭
sleep 2

# 进入项目目录（根据实际路径修改）
cd /root/Visualized_fund_monitoring || cd /home/ubuntu/Visualized_fund_monitoring || cd $(pwd)

echo "当前目录: $(pwd)"
echo "项目文件列表:"
ls -la | head -10

# 启动服务
echo "🚀 启动服务..."
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &

# 获取进程 PID
sleep 2
PID=$(pgrep -f "uvicorn main:app")

if [ -z "$PID" ]; then
    echo "❌ 启动失败，检查日志："
    tail -50 app.log
else
    echo "✅ 服务已启动！"
    echo "进程 ID: $PID"
    echo "等待初始化..."
    sleep 3
    
    # 显示服务日志
    echo ""
    echo "📋 实时日志:"
    tail -20 app.log
    
    echo ""
    echo "✨ 服务重启完成！"
    echo "访问地址: http://localhost:8000"
    echo "查看日志: tail -f $(pwd)/app.log"
fi
