"""
实时音视频通话相关的 API 路由和逻辑
—— 重构版：标准 WebRTC 呼叫流程
"""
import asyncio
from datetime import datetime, timedelta
from fastapi import WebSocket, WebSocketDisconnect, Form, Request
import secrets
import os


class CallRequest:
    """代表一个通话请求"""
    def __init__(self, call_id: str, requestor: str):
        self.call_id = call_id
        self.requestor = requestor  # "lp" 或 "gp"
        self.status = "WAITING"     # WAITING → ACCEPTED / REJECTED / TIMEOUT
        self.created_at = datetime.now()
        self.timeout_seconds = 60   # 1 分钟超时
        self._timeout_task = None   # asyncio.Task

    @property
    def expires_at(self):
        return self.created_at + timedelta(seconds=self.timeout_seconds)

    @property
    def seconds_left(self):
        return max(0, (self.expires_at - datetime.now()).total_seconds())


class CallManager:
    """管理 WebRTC 通话请求和连接"""
    def __init__(self):
        self.pending_requests = {}   # {"call_id": CallRequest}
        self.active_calls = {}       # {"call_id": {"lp": ws, "gp": ws}}
        self.pending_signals = {}    # {"call_id": {"lp": [msg], "gp": [msg]}}
        self.user_to_call = {}       # {ws_id: call_id}

    # ── 通话请求生命周期 ──────────────────────────

    async def create_call_request(self, call_id: str, requestor: str) -> CallRequest:
        """创建通话请求并启动异步超时定时器（纯 asyncio，无 threading）"""
        req = CallRequest(call_id, requestor)
        self.pending_requests[call_id] = req

        # 用 asyncio.create_task 替代 threading.Timer
        async def _timeout_after(seconds: int):
            await asyncio.sleep(seconds)
            self._mark_timeout(call_id)

        req._timeout_task = asyncio.create_task(_timeout_after(req.timeout_seconds))
        return req

    def _mark_timeout(self, call_id: str):
        """原子标记超时"""
        if call_id in self.pending_requests:
            req = self.pending_requests[call_id]
            if req.status == "WAITING":
                req.status = "TIMEOUT"
                print(f"⏰ 通话请求 {call_id} 已超时")

    def _cancel_timeout(self, call_id: str):
        """取消超时定时器"""
        if call_id in self.pending_requests:
            req = self.pending_requests[call_id]
            if req._timeout_task:
                req._timeout_task.cancel()
                req._timeout_task = None

    def accept_call_request(self, call_id: str) -> bool:
        """受邀方接受通话请求，返回是否成功"""
        if call_id in self.pending_requests:
            req = self.pending_requests[call_id]
            if req.status == "WAITING":
                req.status = "ACCEPTED"
                self._cancel_timeout(call_id)
                return True
        return False

    def decline_call_request(self, call_id: str) -> bool:
        """受邀方拒绝通话请求"""
        if call_id in self.pending_requests:
            req = self.pending_requests[call_id]
            if req.status == "WAITING":
                req.status = "REJECTED"
                self._cancel_timeout(call_id)
                return True
        return False

    def get_incoming_call(self) -> dict | None:
        """返回 GP 当前最早的来电（用于 admin 页面轮询）"""
        for call_id, req in self.pending_requests.items():
            if req.requestor == "lp" and req.status == "WAITING":
                return {
                    "call_id": call_id,
                    "status": req.status,
                    "seconds_left": int(req.seconds_left),
                    "created_at": req.created_at.strftime("%H:%M:%S"),
                }
        return None

    # ── WebRTC 对等连接管理 ────────────────────────

    async def create_rtc_peer(self, call_id: str, user_type: str, websocket: WebSocket) -> bool:
        """为通话注册 WebSocket 对等端点"""
        await websocket.accept()

        if call_id not in self.active_calls:
            self.active_calls[call_id] = {}

        if user_type not in self.active_calls[call_id]:
            self.active_calls[call_id][user_type] = websocket
            self.user_to_call[id(websocket)] = call_id

            if call_id not in self.pending_signals:
                self.pending_signals[call_id] = {"lp": [], "gp": []}

            # 双方都连接后清理 pending_requests
            if call_id in self.pending_requests and len(self.active_calls[call_id]) >= 2:
                del self.pending_requests[call_id]

            # 补发对端先到达的信令（防止 ICE candidate 在 WebSocket 连接前到达）
            to_user = "gp" if user_type == "lp" else "lp"
            queued = self.pending_signals.get(call_id, {}).get(to_user, [])
            if queued:
                for msg in queued:
                    try:
                        await websocket.send_json(msg)
                    except Exception:
                        pass
                self.pending_signals[call_id][to_user] = []

            # 如果是对端先缓存了给当前用户的信号，也一并推送
            my_queued = self.pending_signals.get(call_id, {}).get(user_type, [])
            if my_queued:
                for msg in my_queued:
                    try:
                        await websocket.send_json(msg)
                    except Exception:
                        pass
                self.pending_signals[call_id][user_type] = []

            return True

        # 重复连接：替换旧连接
        old_ws = self.active_calls[call_id].get(user_type)
        if old_ws:
            try:
                await old_ws.close()
            except Exception:
                pass
        self.active_calls[call_id][user_type] = websocket
        return True

    async def broadcast_to_peer(self, call_id: str, from_user: str, message: dict) -> bool:
        """广播信令消息到对端（含暂存兜底）"""
        to_user = "gp" if from_user == "lp" else "lp"

        if call_id in self.active_calls and to_user in self.active_calls[call_id]:
            try:
                await self.active_calls[call_id][to_user].send_json(message)
                return True
            except Exception:
                pass

        # 对端未连接时暂存，等连接后补发
        if call_id not in self.pending_signals:
            self.pending_signals[call_id] = {"lp": [], "gp": []}
        self.pending_signals[call_id][to_user].append(message)
        return True

    async def close_call(self, websocket: WebSocket):
        """清理通话连接"""
        ws_id = id(websocket)
        if ws_id in self.user_to_call:
            call_id = self.user_to_call[ws_id]
            if call_id in self.active_calls:
                for user_type in list(self.active_calls[call_id].keys()):
                    if id(self.active_calls[call_id][user_type]) == ws_id:
                        del self.active_calls[call_id][user_type]
                        # 通知对端对方已挂断
                        peer = "gp" if user_type == "lp" else "lp"
                        if peer in self.active_calls[call_id]:
                            try:
                                await self.active_calls[call_id][peer].send_json({"type": "peer-disconnected"})
                            except Exception:
                                pass
                        break

                if not self.active_calls[call_id]:
                    del self.active_calls[call_id]
                    if call_id in self.pending_signals:
                        del self.pending_signals[call_id]

                    # 清理可能残留的 pending request
                    if call_id in self.pending_requests:
                        del self.pending_requests[call_id]

            del self.user_to_call[ws_id]


# ── 全局实例 ──────────────────────────────────────
call_manager = CallManager()


def resolve_public_base_url(request: Request) -> str:
    """解析用于外部访问的基础地址"""
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

    # ── LP 发起通话 ─────────────────────────────
    @app.post("/api/v1/lp/initiate_call")
    async def initiate_call_request(request: Request):
        """乙方发起通话请求（纯 asyncio，无 threading）"""
        call_id = f"call_{datetime.now().timestamp()}_{secrets.token_hex(8)}"
        await call_manager.create_call_request(call_id, "lp")

        # 通过微信通知甲方（兜底，GP 不在 admin 页面时也能收到）
        base_url = resolve_public_base_url(request)
        call_url = f"{base_url}/video_call?call_id={call_id}&user_type=gp"
        notify_gp_wechat(
            "📞 乙方拨入来电",
            f"乙方发起音视频通话\n\n接听链接：{call_url}\n\n1分钟内请接听"
        )

        return {
            "status": "success",
            "call_id": call_id,
            "message": "通话请求已发送，等待对方接听..."
        }

    # ── GP 轮询检测来电（admin 页面用）───────────
    @app.get("/api/v1/gp/incoming_call")
    def check_incoming_call():
        """GP 轮询：是否有待接听的来电"""
        call_info = call_manager.get_incoming_call()
        if call_info:
            return {"has_call": True, **call_info}
        return {"has_call": False}

    # ── 检查通话状态（LP 轮询，兼容旧逻辑）───────
    @app.get("/api/v1/call_status/{call_id}")
    def check_call_status(call_id: str):
        """检查通话请求状态"""
        if call_id in call_manager.pending_requests:
            req = call_manager.pending_requests[call_id]
            return {"status": req.status, "call_id": call_id, "seconds_left": int(req.seconds_left)}
        return {"status": "NOT_FOUND", "call_id": call_id}

    # ── GP 接受通话 ──────────────────────────────
    @app.post("/api/v1/gp/accept_call/{call_id}")
    def accept_call(call_id: str):
        """甲方接受通话请求"""
        success = call_manager.accept_call_request(call_id)
        if success:
            return {"status": "success", "message": "已接受通话请求"}
        return {"status": "error", "message": "通话请求不存在或已过期"}

    # ── GP 拒绝通话（admin 页面用）───────────────
    @app.post("/api/v1/gp/decline_call/{call_id}")
    def decline_call(call_id: str):
        """甲方拒绝通话请求"""
        success = call_manager.decline_call_request(call_id)
        if success:
            return {"status": "success", "message": "已拒绝通话请求"}
        return {"status": "error", "message": "通话请求不存在或已过期"}

    # ── WebSocket 信令端点 ────────────────────────
    @app.websocket("/ws/video_call/{call_id}/{user_type}")
    async def websocket_video_call(websocket: WebSocket, call_id: str, user_type: str):
        """WebSocket 端点：WebRTC 信令交换（SDP + ICE candidate）"""
        if user_type not in ["lp", "gp"]:
            await websocket.close(code=1008, reason="Invalid user type")
            return

        success = await call_manager.create_rtc_peer(call_id, user_type, websocket)
        if not success:
            await websocket.close(code=1008, reason="Already connected")
            return

        try:
            while True:
                data = await websocket.receive_json()
                await call_manager.broadcast_to_peer(call_id, user_type, data)
        except WebSocketDisconnect:
            await call_manager.close_call(websocket)
        except Exception as e:
            print(f"WebSocket error: {e}")
            await call_manager.close_call(websocket)
