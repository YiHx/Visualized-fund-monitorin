# 通话功能部署检查清单

## ✅ 后端实现完成

### 文件结构
```
main.py                    # 主应用程序
video_call_api.py         # 通话 API 和逻辑模块
dashboard.html            # 乙方（前台）UI
admin.html               # 甲方（后台）UI  
video_call.html          # 通话界面
```

### 核心实现
- ✅ `video_call_api.py` 包含：
  - `CallRequest` 类：通话请求对象，具有 30 秒超时机制
  - `CallManager` 类：管理待处理和活跃通话
  - `setup_video_call_routes()` 函数：注册所有 API 路由

- ✅ `main.py` 修复完成：
  - ✅ 删除破坏的代码（行 127-271）
  - ✅ 导入 `video_call_api` 模块
  - ✅ 调用 `setup_video_call_routes()` 注册路由
  - ✅ Python 语法验证通过

### API 端点
1. **`POST /api/v1/lp/initiate_call`** - 发起通话
   - 请求体：无
   - 响应：`{ status, call_id, message }`
   - 功能：创建通话请求，发送微信通知，返回 call_id

2. **`POST /api/v1/check_call_status/{call_id}`** - 检查状态
   - 请求体：无
   - 响应：`{ status, call_id }`
   - 状态值：WAITING、ACCEPTED、TIMEOUT
   - 用途：乙方轮询（500ms）查询甲方是否接听

3. **`POST /api/v1/gp/accept_call/{call_id}`** - 接受通话
   - 请求体：无
   - 响应：`{ status, message, call_url }`
   - 功能：标记请求已接受，取消超时定时器

4. **`WebSocket /ws/video_call/{call_id}/{user_type}`** - 信号交换
   - 用途：WebRTC SDP offer/answer 和 ICE candidate 交换

## ✅ 前端实现完成

### dashboard.html（乙方界面）
- ✅ 添加"🎥 发起通话"按钮
- ✅ `initiateCall()` 函数实现：
  ```javascript
  1. POST /api/v1/lp/initiate_call → 获得 call_id
  2. 显示提示："已发送通话请求给甲方，正在等待接听..."
  3. 打开通话窗口：window.open(/video_call?call_id=XXX&user_type=lp)
  4. 每 500ms 轮询一次 /api/v1/check_call_status/{call_id}
  5. 若 30s 内无响应 → 显示"对方可能正在忙，请稍后再拨"，关闭窗口
  6. 若甲方接受 → 轮询停止，进入 WebRTC 通话
  ```

### admin.html（甲方界面）
- ✅ 移除"🎥 发起通话"按钮
- ✅ 移除 `initiateCall()` 函数
- ✅ 甲方无法主动发起通话（只能接听）

### video_call.html（通话界面）
- ✅ 新增 GP（甲方）接受流程：
  ```javascript
  if (userType === 'gp') {
      await fetch(/api/v1/gp/accept_call/{call_id})
      // 检查响应，若失败则显示"通话请求已过期或不存在"
  }
  ```
- ✅ WebRTC 初始化
- ✅ 媒体控制（麦克风、摄像头、挂断）
- ✅ 实时统计（延迟、分辨率、帧率）

## 🔄 通话流程验证

### 完整流程（成功路径）
```
[乙方] 点击"🎥 发起通话"
  ↓
[后端] POST /api/v1/lp/initiate_call
  → 生成 call_id
  → 创建 CallRequest，启动 30s 计时器
  → 存入 pending_requests 字典
  → 发送微信通知给甲方
  ↓
[乙方] 收到响应，显示等待提示，打开通话窗口
[乙方] 开始轮询 /api/v1/check_call_status/{call_id}（每 500ms）
  ↓
[甲方] 收到微信消息，点击链接
  → 打开 /video_call?call_id=XXX&user_type=gp
  ↓
[甲方窗口] 发送 POST /api/v1/gp/accept_call/{call_id}
  ← [后端] 设置 status='ACCEPTED'，取消计时器
  ↓
[乙方轮询] 获得 status='ACCEPTED'，停止轮询
  ↓
[乙方 & 甲方] 双方进入 WebRTC 通话
  ↓
WebSocket /ws/video_call/{call_id}/lp ← → /ws/video_call/{call_id}/gp
  (SDP offer/answer, ICE candidates)
  ↓
✅ 语音视频通话建立
```

### 超时流程（30s 内甲方未接听）
```
[后端] 计时器触发 (30s)
  → 设置 CallRequest.status = 'TIMEOUT'
  → 从 pending_requests 中删除
  ↓
[乙方轮询] 获得 status='TIMEOUT'
  → 关闭通话窗口
  → 显示提示："对方可能正在忙，请稍后再拨"
  → 停止轮询
  ↓
✅ 返回到仪表板
```

## 📋 后续部署步骤

### 1. 本地测试（已完成 ✅）
```bash
python -m py_compile main.py video_call_api.py
# 结果：No errors found ✅
```

### 2. 微信通知集成（待完成）
当前代码框架：`main.py` 中的 `notify_gp_wechat()` 函数为打印日志
- 需要集成实际的微信 API：
  - 企业微信 API（推荐用于企业应用）
  - 个人微信机器人（如钉钉、企业微信）
  - 第三方服务（如阿里云短信提醒）

### 3. 环境变量配置（待完成）
当前代码中使用：
```python
base_url = os.environ.get('BASE_URL', 'http://localhost:8000')
```
需要在生产环境配置：
```bash
export BASE_URL='https://yourdomain.com'
```

### 4. Alibaba Cloud 部署
```bash
# SSH 连接到服务器
ssh user@your_server

# 上传新文件
scp main.py video_call_api.py ... user@server:/path/to/app/

# 重启服务
sudo systemctl restart family_fund.service

# 检查日志
sudo journalctl -u family_fund.service -f
```

### 5. 完整流程测试（Alibaba Cloud）
1. 使用乙方账户登录仪表板
2. 点击"🎥 发起通话"按钮
3. 接收微信通知（甲方）
4. 点击微信通知中的链接
5. 验证两端都能看到对方的音视频
6. 测试麦克风/摄像头开关
7. 测试挂断功能
8. 验证实时统计显示正确的延迟/分辨率/帧率

## 🔧 故障排查

### 问题：乙方发起通话后无法看到"对方可能正在忙"提示
- 原因 1：轮询周期过长或不工作 → 检查浏览器控制台错误
- 原因 2：API 端点未正确注册 → 检查 main.py 中的 setup_video_call_routes() 调用
- 原因 3：call_id 不匹配 → 验证乙方客户端和后端的 call_id 同步

### 问题：甲方看不到接受通话链接
- 原因 1：微信通知函数未集成 → 检查 notify_gp_wechat() 实现
- 原因 2：BASE_URL 配置错误 → 验证生成的链接是否可访问

### 问题：WebRTC 连接失败
- 原因 1：STUN 服务器不可用 → 尝试其他 STUN 服务器（如 coturn）
- 原因 2：防火墙阻止 UDP → 检查服务器防火墙规则
- 原因 3：WebSocket 连接失败 → 检查后端 WebSocket 端点

## ✨ 功能完成清单

- ✅ 后端 API 框架完整
- ✅ 30 秒超时机制（使用 threading.Timer）
- ✅ 乙方轮询机制（500ms 间隔，30s 自动停止）
- ✅ 甲方接受流程（WebSocket 初始化前调用）
- ✅ WebRTC 双向通信
- ✅ 前端 UI 更新（按钮、提示、窗口管理）
- ✅ 语法检查通过
- ⏳ 微信通知集成（框架已准备，待实现具体 API 调用）
- ⏳ Alibaba Cloud 部署测试

## 📞 使用说明

### 乙方（前台）
1. 登录仪表板
2. 看到"🎥 发起通话"按钮
3. 点击按钮 → 发送请求给甲方 → 等待 30 秒
4. 如果甲方接听，进入视频通话
5. 如果 30 秒内无人接听，显示"对方可能正在忙，请稍后再拨"

### 甲方（后台）
1. 登录仪表板（不显示发起通话按钮）
2. 接收微信通知，点击链接
3. 进入视频通话界面 → 音视频自动初始化
4. 与乙方进行对话

---
**部署日期**：[待部署]
**最后更新**：2024-01-XX
**状态**：✅ 代码完成，⏳ 等待微信集成和云部署测试
