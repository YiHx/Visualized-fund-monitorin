#!/bin/bash
set -euo pipefail

# ============================================
# 家庭基金监控系统 —— 一键部署脚本
# ============================================
# 用法:
#   ./deploy.sh                    # 部署到已配置的服务器
#   ./deploy.sh --dry-run          # 预览将要同步的文件
#   ./deploy.sh --skip-restart     # 只上传文件，不重启服务

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- 加载配置 ----------
DEPLOY_SERVER="${DEPLOY_SERVER:-}"
DEPLOY_PATH="${DEPLOY_PATH:-/root}"
DEPLOY_PORT="${DEPLOY_PORT:-22}"
DEPLOY_KEY="${DEPLOY_KEY:-}"
DRY_RUN=false
SKIP_RESTART=false

# 从 .env.deploy 加载覆盖（如果存在）
if [ -f "$SCRIPT_DIR/.env.deploy" ]; then
    set -a
    source "$SCRIPT_DIR/.env.deploy"
    set +a
fi

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case "$1" in
        --server) DEPLOY_SERVER="$2"; shift 2 ;;
        --path)   DEPLOY_PATH="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --skip-restart) SKIP_RESTART=true; shift ;;
        --help|-h)
            echo "用法: ./deploy.sh [选项]"
            echo "  默认服务器: $DEPLOY_SERVER"
            echo "  默认路径:   $DEPLOY_PATH"
            echo ""
            echo "  --server HOST        服务器地址"
            echo "  --path PATH          远程路径"
            echo "  --dry-run            预览模式"
            echo "  --skip-restart       只上传，不重启"
            echo ""
            echo "创建 .env.deploy 可自定义默认值"
            exit 0 ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

# ---------- SSH 选项 ----------
SSH_OPTS="-p $DEPLOY_PORT -o StrictHostKeyChecking=no -o ConnectTimeout=10"
if [ -n "$DEPLOY_KEY" ]; then
    SSH_OPTS="$SSH_OPTS -i $DEPLOY_KEY"
fi

RSYNC_OPTS="-avz --progress --exclude-from=.deployignore"
if [ -n "$DEPLOY_KEY" ]; then
    RSYNC_RSH="ssh -p $DEPLOY_PORT -i $DEPLOY_KEY -o StrictHostKeyChecking=no"
else
    RSYNC_RSH="ssh -p $DEPLOY_PORT -o StrictHostKeyChecking=no"
fi

# ---------- 执行 ----------
echo "=========================================="
echo "  家庭基金监控系统 · 部署"
echo "=========================================="
echo "  服务器: $DEPLOY_SERVER"
echo "  路径:   $DEPLOY_PATH"
echo "  模式:   $([ "$DRY_RUN" = true ] && echo '🔍 预览' || echo '🚀 部署')"
echo ""

# 测试连接
echo "🔗 测试 SSH..."
if ! ssh $SSH_OPTS "$DEPLOY_SERVER" "echo 'OK'" 2>/dev/null; then
    echo "❌ SSH 连接失败！"
    echo "   请先运行: ssh-copy-id $DEPLOY_SERVER"
    exit 1
fi
echo "✅ 连接成功"
echo ""

if [ "$DRY_RUN" = true ]; then
    rsync $RSYNC_OPTS --dry-run -e "$RSYNC_RSH" ./ "$DEPLOY_SERVER:/tmp/deploy_preview/"
    echo ""
    echo "🔍 以上是将要同步的文件（未实际部署）"
    exit 0
fi

# 上传到临时目录
echo "📦 上传文件..."
TMPDIR="/tmp/fund_deploy_$(date +%s)"
ssh $SSH_OPTS "$DEPLOY_SERVER" "mkdir -p $TMPDIR"
rsync $RSYNC_OPTS -e "$RSYNC_RSH" ./ "$DEPLOY_SERVER:$TMPDIR/"

# 远程操作：部署 + 重启
echo ""
echo "🔧 安装文件并重启..."

ssh $SSH_OPTS "$DEPLOY_SERVER" bash -s << REMOTE
set -e
TMPDIR="$TMPDIR"
TARGET="$DEPLOY_PATH"

echo "备份旧文件..."
sudo cp \$TARGET/main.py \$TARGET/main.py.bak.\$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
sudo cp \$TARGET/admin.html \$TARGET/admin.html.bak.\$(date +%Y%m%d_%H%M%S) 2>/dev/null || true

echo "同步文件（保留数据库和上传文件）..."
sudo rsync -av --exclude='family_fund.db' --exclude='uploads/messages/' --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \$TMPDIR/ \$TARGET/

# 修复 Linux 文件名大小写: Main.py → main.py
if [ -f "\$TARGET/Main.py" ]; then
    echo "修复文件名: Main.py → main.py"
    sudo mv "\$TARGET/Main.py" "\$TARGET/main.py"
fi
sudo chown -R root:root \$TARGET/main.py \$TARGET/video_call_api.py \$TARGET/*.html \$TARGET/deploy.sh \$TARGET/restart_server.sh 2>/dev/null || true

echo "语法检查..."
cd \$TARGET
sudo python3 -m py_compile main.py video_call_api.py && echo "✅ 通过"

# 修复日志权限
sudo touch \$TARGET/server.log 2>/dev/null || true
sudo chmod 666 \$TARGET/server.log 2>/dev/null || true

if [ "$SKIP_RESTART" = "true" ]; then
    echo "⏭️ 跳过重启"
else
    echo "🔄 重启服务..."
    sudo pkill -f "uvicorn main:app" 2>/dev/null || true
    sleep 2
    cd \$TARGET
    sudo bash -c 'nohup python3 -m uvicorn main:app --host 127.0.0.1 --port 8000 > server.log 2>&1 &'
    sleep 3
    PID=\$(pgrep -f "uvicorn main:app" || echo "")
    if [ -z "\$PID" ]; then
        echo "❌ 启动失败！"
        sudo tail -30 \$TARGET/server.log
        exit 1
    fi
    echo "✅ 已启动 PID=\$PID"
fi

# 清理临时目录
rm -rf \$TMPDIR

echo ""
echo "📋 验证关键端点..."
echo -n "  GP verify:  "
curl -s -X POST http://127.0.0.1:8000/api/v1/gp/verify -H "Content-Type: application/json" -d '{"pin":"0828"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ 正常' if d.get('status')=='success' else '❌ 异常')" 2>/dev/null || echo "❌ 异常"

echo -n "  GP API 鉴权: "
RES=\$(curl -s http://127.0.0.1:8000/api/v1/gp/pending_requests)
if echo "\$RES" | grep -q "身份验证失败"; then
    echo "✅ 鉴权生效"
else
    echo "❌ 未保护"
fi

echo -n "  Dashboard: "
curl -s http://127.0.0.1:8000/api/v1/dashboard | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'✅ NAV=¥{d[\"nav\"][\"R_total\"]}')" 2>/dev/null || echo "❌"

REMOTE

echo ""
echo "=========================================="
echo "  ✨ 部署完成！"
echo "=========================================="
echo ""
echo " 前台: https://${DEPLOY_SERVER#*@}/"
echo " 后台: https://${DEPLOY_SERVER#*@}/admin"
echo ""
