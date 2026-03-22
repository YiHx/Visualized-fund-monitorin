"""
实时音视频通话相关的 API 路由和逻辑
"""
import asyncio
import threading
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect, Form, Request
import secrets
import os

class CallRequest:
    """代表一个通话请求"""
    def __init__(self, call_id: str, requestor: str):
        self.call_id = call_id
        self.requestor = requestor  # "lp" 或 "gp"
        self.status = "WAITING"  # WAITING, ACCEPTED, REJECTED, TIMEOUT
        self.created_at = datetime.now()
        self.websocket = None
        self.timeout_task = None

class CallManager:
    """管理 WebRTC 通话请求和连接"""
    def __init__(self):
        self.pending_requests = {}  # {"call_id": CallRequest}
        self.active_calls = {}      # {"call_id": {"lp": ws, "gp": ws}}
        self.user_to_call = {}      # 追踪用户当前通话
        self.pending_signals = {}   # {"call_id": {"lp": [msg], "gp": [msg]}}

    def create_call_request(self, call_id: str, requestor: str) -> CallRequest:
        """创建通话请求"""
        request = CallRequest(call_id, requestor)
        self.pending_requests[call_id] = request
        
        # 60秒（1分钟）后自动超时
        def timeout_handler():
            asyncio.run(self.timeout_request(call_id))
        
        timeout_thread = threading.Timer(60, timeout_handler)
        timeout_thread.daemon = True
        timeout_thread.start()
        request.timeout_task = timeout_thread
        
        return request

    async def timeout_request(self, call_id: str):
        """处理通话请求超时"""
        if call_id in self.pending_requests:
            request = self.pending_requests[call_id]
            if request.status == "WAITING":
                request.status = "TIMEOUT"
                print(f"通话请求 {call_id} 已超时")

    def accept_call_request(self, call_id: str) -> bool:
        """受邀方接受通话请求"""
        if call_id in self.pending_requests:
            request = self.pending_requests[call_id]
            if request.status == "WAITING":
                request.status = "ACCEPTED"
                # 取消超时定时器
                if request.timeout_task:
                    request.timeout_task.cancel()
                return True
        return False

    async def create_rtc_peer(self, call_id: str, user_type: str, websocket: WebSocket):
        """创建 RTC 连接"""
        await websocket.accept()
        
        if call_id not in self.active_calls:
            self.active_calls[call_id] = {}
        
        if user_type not in self.active_calls[call_id]:
            self.active_calls[call_id][user_type] = websocket
            self.user_to_call[id(websocket)] = call_id

            if call_id not in self.pending_signals:
                self.pending_signals[call_id] = {"lp": [], "gp": []}

            # 只有当双方都已进入通话后，才清理待处理请求，避免 GP 接听时被误判过期
            if call_id in self.pending_requests and len(self.active_calls[call_id]) >= 2:
                del self.pending_requests[call_id]

            # 对端先发来的信令在这里补发，避免 offer/ice 因时序问题丢失
            queued = self.pending_signals.get(call_id, {}).get(user_type, [])
            if queued:
                for msg in queued:
                    await websocket.send_json(msg)
                self.pending_signals[call_id][user_type] = []
            return True
        return False

    async def broadcast_to_peer(self, call_id: str, from_user: str, message: dict):
        """广播消息到对端"""
        to_user = "gp" if from_user == "lp" else "lp"
        if call_id in self.active_calls and to_user in self.active_calls[call_id]:
            try:
                await self.active_calls[call_id][to_user].send_json(message)
                return True
            except:
                return False
        # 对端尚未连接时暂存信令，等对端连接后补发
        if call_id not in self.pending_signals:
            self.pending_signals[call_id] = {"lp": [], "gp": []}
        self.pending_signals[call_id][to_user].append(message)
        return True

    async def close_call(self, websocket: WebSocket):
        """关闭通话"""
        ws_id = id(websocket)
        if ws_id in self.user_to_call:
            call_id = self.user_to_call[ws_id]
            if call_id in self.active_calls:
                # 找出是谁断连
                for user_type in list(self.active_calls[call_id].keys()):
                    if id(self.active_calls[call_id][user_type]) == ws_id:
                        del self.active_calls[call_id][user_type]
                        break
                
                # 如果通话完全断开，清理
                if not self.active_calls[call_id]:
                    del self.active_calls[call_id]
                    if call_id in self.pending_signals:
                        del self.pending_signals[call_id]
            
            del self.user_to_call[ws_id]

# 全局通话管理器实例
call_manager = CallManager()


def resolve_public_base_url(request: Request) -> str:
    """解析用于外部访问的基础地址，优先环境变量，其次代理头。"""
    env_base = os.environ.get("BASE_URL", "").strip()
    if env_base:
        return env_base.rstrip("/")

    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")

    host = request.headers.get("host")
    if host:
        proto = request.url.scheme or "http"
        return f"{proto}://{host}".rstrip("/")

    return str(request.base_url).rstrip("/")

def setup_video_call_routes(app, notify_gp_wechat):
    """在 FastAPI app 中注册所有视频通话相关的路由"""
    
    @app.post("/api/v1/lp/initiate_call")
    def initiate_call_request(request: Request):
        """乙方发起通话请求"""
        call_id = f"call_{datetime.now().timestamp()}_{secrets.token_hex(8)}"
        call_manager.create_call_request(call_id, "lp")
        
        # 通过微信通知甲方
        base_url = resolve_public_base_url(request)
        call_url = f"{base_url}/video_call?call_id={call_id}&user_type=gp"
        notify_gp_wechat("📞 乙方拨入来电", f"乙方发起音视频通话\n\n接听链接：{call_url}\n\n1分钟内请接听，否则对方会看到'对方可能正在忙'")
        
        return {
            "status": "success",
            "call_id": call_id,
            "message": "通话请求已发送，等待对方接听..."
        }
    
    @app.post("/api/v1/check_call_status/{call_id}")
    def check_call_status(call_id: str):
        """检查通话请求状态（乙方轮询）"""
        if call_id in call_manager.pending_requests:
            request = call_manager.pending_requests[call_id]
            return {
                "status": request.status,  # WAITING, ACCEPTED, TIMEOUT
                "call_id": call_id
            }
        return {"status": "NOT_FOUND", "call_id": call_id}
    
    @app.post("/api/v1/gp/accept_call/{call_id}")
    def accept_call_request(call_id: str):
        """甲方接受通话请求"""
        success = call_manager.accept_call_request(call_id)
        if success:
            return {
                "status": "success",
                "message": "已接受通话请求",
                "call_url": f"/video_call?call_id={call_id}&user_type=gp"
            }
        return {
            "status": "error",
            "message": "通话请求不存在或已过期"
        }
    
    @app.websocket("/ws/video_call/{call_id}/{user_type}")
    async def websocket_video_call(websocket: WebSocket, call_id: str, user_type: str):
        """WebSocket 端点用于 WebRTC 信号交换"""
        # 只允许 lp 或 gp 用户类型
        if user_type not in ["lp", "gp"]:
            await websocket.close(code=1008, reason="Invalid user type")
            return
        
        # 尝试创建 RTC 连接
        success = await call_manager.create_rtc_peer(call_id, user_type, websocket)
        if not success:
            await websocket.close(code=1008, reason=f"{user_type} already in this call")
            return
        
        try:
            while True:
                # 接收来自前端的消息（SDP offer/answer、ICE candidate）
                data = await websocket.receive_json()
                
                # 广播到对端
                await call_manager.broadcast_to_peer(call_id, user_type, data)
        except WebSocketDisconnect:
            await call_manager.close_call(websocket)
        except Exception as e:
            print(f"WebSocket error: {e}")
            await call_manager.close_call(websocket)
