from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, status, WebSocket, WebSocketDisconnect, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, desc, extract
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import date, datetime, timedelta
import os
import shutil
import secrets
import requests
import json
import hashlib
import time
from sqlalchemy.exc import SQLAlchemyError

# ==========================================
# 0. 环境准备
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
MESSAGES_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "messages")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)
if not os.path.exists(MESSAGES_UPLOAD_DIR):
    os.makedirs(MESSAGES_UPLOAD_DIR)

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB

DB_PATH = os.path.join(BASE_DIR, "family_fund.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 1. 数据库模型定义
# ==========================================
class DBTransaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    tx_date = Column(Date, nullable=False, default=date.today)
    tx_type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String, nullable=False)

class DBRequest(Base):
    __tablename__ = "requests"
    id = Column(Integer, primary_key=True, index=True)
    req_date = Column(Date, nullable=False, default=date.today)
    req_type = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    reason = Column(String, nullable=False)
    proof_image = Column(String, nullable=True)
    status = Column(String, nullable=False, default="PENDING") 

class DBAssetAllocation(Base):
    __tablename__ = "asset_allocations"
    id = Column(Integer, primary_key=True, index=True)
    asset_name = Column(String, nullable=False)
    allocated_amount = Column(Float, nullable=False)

class DBMessage(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    created_date = Column(DateTime, nullable=False, default=datetime.now)
    content = Column(String, nullable=False)
    attachment_url = Column(String, nullable=True)
    reply = Column(String, nullable=True)
    reply_time = Column(DateTime, nullable=True)

class DBQuarterlyEvent(Base):
    __tablename__ = "quarterly_events"
    id = Column(Integer, primary_key=True, index=True)
    issued_at = Column(DateTime, default=datetime.now) 
    status = Column(String, default="ACTIVE")          
    claimed_at = Column(DateTime, nullable=True)       

class DBNotice(Base):
    __tablename__ = "notices"
    id = Column(Integer, primary_key=True, index=True)
    publish_time = Column(DateTime, default=datetime.now)
    content = Column(String, nullable=False)

class DBNotificationLog(Base):
    __tablename__ = "notification_logs"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    channel = Column(String, nullable=False, default="pushplus")
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)
    status = Column(String, nullable=False)  # SUCCESS / FAILED
    response_msg = Column(String, nullable=True)

# ── 博彩系统模型 ────────────────────────────────
class DBLotteryPrize(Base):
    __tablename__ = "lottery_prizes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    prize_type = Column(String, nullable=False)   # CASH / MULTIPLIER / NOTHING / SPECIAL
    value = Column(Float, nullable=False, default=0.0)
    weight = Column(Integer, nullable=False, default=10)
    is_active = Column(Integer, nullable=False, default=1)
    icon = Column(String, nullable=False, default="🎁")

class DBLotteryRecord(Base):
    __tablename__ = "lottery_records"
    id = Column(Integer, primary_key=True, index=True)
    draw_time = Column(DateTime, nullable=False, default=datetime.now)
    cost = Column(Float, nullable=False)
    prize_name = Column(String, nullable=False)
    prize_value = Column(Float, nullable=False, default=0.0)
    result_type = Column(String, nullable=False)   # WIN / LOSE / JACKPOT

class DBSystemConfig(Base):
    __tablename__ = "system_config"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)

class DBWebAuthnCred(Base):
    __tablename__ = "webauthn_creds"
    id = Column(Integer, primary_key=True, index=True)
    credential_id = Column(String, unique=True, nullable=False)
    public_key_x = Column(String, nullable=False)   # hex encoded
    public_key_y = Column(String, nullable=False)   # hex encoded
    sign_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

Base.metadata.create_all(bind=engine)

# ==========================================
# 数据库迁移：检查并添加缺失的列
# ==========================================
def ensure_db_schema():
    """检查数据库表结构，添加缺失的列"""
    from sqlalchemy import inspect, text
    
    inspector = inspect(engine)
    db = SessionLocal()
    
    try:
        # 检查 messages 表是否有 attachment_url 列
        if "messages" in inspector.get_table_names():
            columns = {col['name'] for col in inspector.get_columns('messages')}
            
            if 'attachment_url' not in columns:
                print("🔧 检测到缺失列：messages.attachment_url，正在自动修复...")
                db.execute(text("ALTER TABLE messages ADD COLUMN attachment_url VARCHAR"))
                db.commit()
                print("✅ 数据库迁移完成：已添加 attachment_url 列")
    except Exception as e:
        print(f"⚠️  数据库迁移出现警告（可忽略）：{e}")
        db.rollback()
    finally:
        db.close()

# 启动时执行迁移
ensure_db_schema()

app = FastAPI(title="家庭高净值资产控制台")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.add_middleware(GZipMiddleware, minimum_size=500)


app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# ==========================================
# 导入通话管理模块
# ==========================================
from video_call_api import call_manager, setup_video_call_routes

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# ==========================================
# 2. 核心算法与引擎
# ==========================================
def log_notification_event(title: str, content: str, status: str, response_msg: str = ""):
    """统一记录微信通知发送结果。"""
    db = SessionLocal()
    try:
        db.add(DBNotificationLog(
            channel="pushplus",
            title=title,
            content=content,
            status=status,
            response_msg=response_msg[:1000] if response_msg else None
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"通知日志写入失败: {e}")
    finally:
        db.close()

def notify_gp_wechat(title: str, content: str):
    """通过 PushPlus 发送微信通知。"""
    url = "https://www.pushplus.plus/send"
    token = os.environ.get("PUSHPLUS_TOKEN", "e92ace8deade436093a43798c81ecddc")

    if not token:
        print("微信通知发送失败: 未配置 PUSHPLUS_TOKEN")
        log_notification_event(title, content, "FAILED", "未配置 PUSHPLUS_TOKEN")
        return False

    data = {
        "token": token,
        "title": title,
        "content": content,
        "template": "txt"
    }

    try:
        # 给微信发信号，超时时间设为 2 秒，防止卡顿
        resp = requests.post(url, json=data, timeout=2)
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != 200:
            msg = payload.get('msg', 'unknown error')
            print(f"微信通知发送失败: {msg}")
            log_notification_event(title, content, "FAILED", msg)
            return False
        log_notification_event(title, content, "SUCCESS", payload.get("msg", "ok"))
        return True
    except Exception as e:
        print(f"微信通知发送失败: {e}")
        log_notification_event(title, content, "FAILED", str(e))
        return False

# 注册视频通话路由（绑定真实微信通知实现）
setup_video_call_routes(app, notify_gp_wechat)

def get_dynamic_monthly_limit():
    BASE_LIMIT = 100.0
    today = date.today()
    current_year = today.year
    if current_year < 2027: return BASE_LIMIT
    years_passed = current_year - 2026
    if today < date(current_year, 4, 3): years_passed -= 1
    if years_passed <= 0: return BASE_LIMIT
    return round(BASE_LIMIT * ((1.1) ** years_passed), 2)

def get_current_month_used(db: Session):
    today = date.today()
    used_tx = db.query(DBTransaction).filter(DBTransaction.tx_type == 'WITHDRAWAL', extract('year', DBTransaction.tx_date) == today.year, extract('month', DBTransaction.tx_date) == today.month).all()
    pending_req = db.query(DBRequest).filter(DBRequest.req_type == 'WITHDRAWAL_REQ', DBRequest.status == 'PENDING', extract('year', DBRequest.req_date) == today.year, extract('month', DBRequest.req_date) == today.month).all()
    return sum([t.amount for t in used_tx]) + sum([r.amount for r in pending_req])

def calculate_system_nav(db: Session, current_date: date):
    HURDLE_RATE = 0.015 
    txs = db.query(DBTransaction).order_by(DBTransaction.tx_date.asc()).all()
    total_principal, total_alpha, total_interest = 0.0, 0.0, 0.0
    withdrawals = [t.amount for t in txs if t.tx_type in ['WITHDRAWAL', 'QUARTERLY_PAYOUT', 'ADJUST_DOWN']]
    inflows = [t for t in txs if t.tx_type in ['PRINCIPAL', 'ALPHA', 'ADJUST_UP']]
    for inflow in inflows:
        days_held = (current_date - inflow.tx_date).days
        if days_held < 0: continue
        effective_amount = inflow.amount
        while withdrawals and effective_amount > 0:
            w = withdrawals[0]
            if effective_amount >= w: effective_amount -= w; withdrawals.pop(0) 
            else: withdrawals[0] -= effective_amount; effective_amount = 0 
        interest = effective_amount * ((1 + HURDLE_RATE) ** (days_held / 365.0) - 1)
        total_interest += interest
        if inflow.tx_type in ['PRINCIPAL', 'ADJUST_UP']: total_principal += effective_amount
        else: total_alpha += effective_amount
    r_total = total_principal + total_alpha + total_interest
    return { "R_total": round(r_total, 4), "effective_principal": round(total_principal, 2), "total_alpha": round(total_alpha, 2), "total_compound_interest": round(total_interest, 4) }

def get_display_allocations(db: Session, nav_total: float):
    """Build allocation view with cash reserve and proportional shrink on NAV drawdown."""
    raw_allocations = db.query(DBAssetAllocation).all()
    positive_allocs = [a for a in raw_allocations if a.allocated_amount and a.allocated_amount > 0]
    raw_total = sum(a.allocated_amount for a in positive_allocs)

    # No configured assets: the whole NAV is treated as idle cash.
    if not positive_allocs:
        cash_only = round(max(0.0, nav_total), 2)
        return {
            "allocations": ([{"asset": "现金仓", "amount": cash_only}] if cash_only > 0 else []),
            "meta": {
                "configured_total": 0.0,
                "display_total": cash_only,
                "cash_reserve": cash_only,
                "scale_factor": 1.0,
                "is_scaled": False
            }
        }

    if nav_total <= 0:
        zero_allocs = [{"asset": a.asset_name, "amount": 0.0} for a in positive_allocs]
        return {
            "allocations": zero_allocs,
            "meta": {
                "configured_total": round(raw_total, 2),
                "display_total": 0.0,
                "cash_reserve": 0.0,
                "scale_factor": 0.0,
                "is_scaled": True
            }
        }

    if raw_total <= nav_total:
        cash_reserve = round(nav_total - raw_total, 2)
        allocs = [{"asset": a.asset_name, "amount": round(a.allocated_amount, 2)} for a in positive_allocs]
        if cash_reserve > 0:
            allocs.append({"asset": "现金仓", "amount": cash_reserve})
        return {
            "allocations": allocs,
            "meta": {
                "configured_total": round(raw_total, 2),
                "display_total": round(sum(item["amount"] for item in allocs), 2),
                "cash_reserve": cash_reserve,
                "scale_factor": 1.0,
                "is_scaled": False
            }
        }

    scale = nav_total / raw_total
    allocs = [{"asset": a.asset_name, "amount": round(a.allocated_amount * scale, 2)} for a in positive_allocs]
    return {
        "allocations": allocs,
        "meta": {
            "configured_total": round(raw_total, 2),
            "display_total": round(sum(item["amount"] for item in allocs), 2),
            "cash_reserve": 0.0,
            "scale_factor": round(scale, 6),
            "is_scaled": True
        }
    }

def get_quarterly_info(db: Session):
    event = db.query(DBQuarterlyEvent).order_by(desc(DBQuarterlyEvent.id)).first()
    if not event: return {"status": "INACTIVE", "show_expired": False}
    now = datetime.now()
    if event.status == "ACTIVE" and now > event.issued_at + timedelta(hours=72):
        event.status = "EXPIRED"; db.commit()
    hours_left = 0
    show_expired = False
    if event.status == "ACTIVE":
        seconds_left = (event.issued_at + timedelta(hours=72) - now).total_seconds()
        hours_left = round(max(0, seconds_left) / 3600, 1)
    elif event.status == "EXPIRED":
        if now <= event.issued_at + timedelta(hours=72) + timedelta(hours=72): show_expired = True
    return { "status": event.status, "hours_left": hours_left, "show_expired": show_expired, "issued_at": event.issued_at.strftime("%Y-%m-%d %H:%M"), "claimed_at": event.claimed_at.strftime("%Y-%m-%d %H:%M") if event.claimed_at else None }

# ==========================================
# 3. 接口路由
# ==========================================
# 2.5 博彩抽奖引擎
# ==========================================
import random

def _get_config(db: Session, key: str, default: str = "") -> str:
    row = db.query(DBSystemConfig).filter(DBSystemConfig.key == key).first()
    return row.value if row else default

def _set_config(db: Session, key: str, value: str):
    row = db.query(DBSystemConfig).filter(DBSystemConfig.key == key).first()
    if row:
        row.value = value
    else:
        db.add(DBSystemConfig(key=key, value=value))
    db.commit()

def _ensure_default_prizes(db: Session):
    if db.query(DBLotteryPrize).count() > 0:
        return
    defaults = [
        DBLotteryPrize(name="\U0001f3c6 头等大奖", prize_type="CASH", value=200.0, weight=1, icon="\U0001f3c6"),
        DBLotteryPrize(name="\U0001f48e 钻石奖", prize_type="CASH", value=50.0, weight=3, icon="\U0001f48e"),
        DBLotteryPrize(name="\U0001f4b0 现金红包", prize_type="CASH", value=10.0, weight=8, icon="\U0001f4b0"),
        DBLotteryPrize(name="\U0001f504 双倍返还", prize_type="MULTIPLIER", value=2.0, weight=5, icon="\U0001f504"),
        DBLotteryPrize(name="\U0001f519 1.5倍返还", prize_type="MULTIPLIER", value=1.5, weight=10, icon="\U0001f519"),
        DBLotteryPrize(name="\U0001f3ab 再来一次", prize_type="SPECIAL", value=0.0, weight=7, icon="\U0001f3ab"),
        DBLotteryPrize(name="\U0001f4a8 谢谢参与", prize_type="NOTHING", value=0.0, weight=50, icon="\U0001f4a8"),
        DBLotteryPrize(name="\U0001f31f 幸运星", prize_type="CASH", value=5.0, weight=10, icon="\U0001f31f"),
    ]
    for p in defaults:
        db.add(p)
    db.commit()

def _ensure_default_config(db: Session):
    if not db.query(DBSystemConfig).filter(DBSystemConfig.key == "LOTTERY_COST").first():
        _set_config(db, "LOTTERY_COST", "5.00")
    if not db.query(DBSystemConfig).filter(DBSystemConfig.key == "LOTTERY_ENABLED").first():
        _set_config(db, "LOTTERY_ENABLED", "1")

def execute_lottery_draw(db: Session, nav_total: float) -> dict:
    cost = float(_get_config(db, "LOTTERY_COST", "5.00"))
    enabled = _get_config(db, "LOTTERY_ENABLED", "1")

    if enabled != "1":
        raise HTTPException(status_code=403, detail="博彩系统当前已关闭。")
    if nav_total < cost:
        raise HTTPException(status_code=403, detail=f"余额不足！当前净值 ¥{nav_total:.2f}，单次抽奖 ¥{cost:.2f}。")

    prizes = db.query(DBLotteryPrize).filter(DBLotteryPrize.is_active == 1).all()
    if not prizes:
        raise HTTPException(status_code=400, detail="奖品池为空，请等待GP配置奖品。")

    total_weight = sum(p.weight for p in prizes)
    roll = random.randint(1, total_weight)
    cumulative = 0
    won_prize = prizes[-1]
    for p in prizes:
        cumulative += p.weight
        if roll <= cumulative:
            won_prize = p
            break

    prize_value = 0.0
    if won_prize.prize_type == "CASH":
        prize_value = won_prize.value
    elif won_prize.prize_type == "MULTIPLIER":
        prize_value = round(cost * won_prize.value, 2)

    db.add(DBTransaction(tx_type="ADJUST_DOWN", amount=cost, description=f"\U0001f3b0 博彩抽奖：{won_prize.name}"))

    if prize_value > 0:
        db.add(DBTransaction(tx_type="ADJUST_UP", amount=prize_value, description=f"\U0001f3b0 博彩中奖：{won_prize.name}，奖金 ¥{prize_value:.2f}"))

    if won_prize.prize_type == "SPECIAL":
        result_type = "WIN"
    elif prize_value > cost * 5:
        result_type = "JACKPOT"
    elif prize_value > 0:
        result_type = "WIN"
    else:
        result_type = "LOSE"

    db.add(DBLotteryRecord(cost=cost, prize_name=won_prize.name, prize_value=prize_value, result_type=result_type))
    db.commit()

    new_nav = calculate_system_nav(db, date.today())["R_total"]
    if result_type == "JACKPOT":
        msg = f"\U0001f389 天选之人！！中了 {won_prize.name}，净赚 ¥{prize_value:.2f}！"
    elif result_type == "WIN":
        suffix = f"，奖金 ¥{prize_value:.2f}！" if prize_value > 0 else "！"
        msg = f"\U0001f38a 恭喜！中奖 {won_prize.name}{suffix}"
    else:
        msg = f"\U0001f4a8 {won_prize.name}，下次好运！"
    return {
        "status": "success", "cost": cost, "prize_name": won_prize.name, "prize_icon": won_prize.icon,
        "prize_value": prize_value, "result_type": result_type, "roll": roll, "total_weight": total_weight,
        "new_nav": new_nav, "message": msg
    }
# ==========================================
class VerifyReq(BaseModel): pin: str

@app.post("/api/v1/lp/verify")
def verify_lp(req: VerifyReq):
    if req.pin == "0103": return {"status": "success"}
    raise HTTPException(status_code=403, detail="授权码错误。")

# GP 认证 —— 保护后台管理页面
GP_PIN = os.environ.get("GP_PIN", "Yhx2582413!@")
GP_SESSION_SECRET = os.environ.get("GP_SESSION_SECRET", "family-fund-gp-2024-secret")

# 活跃的 GP 会话令牌（简单内存存储，服务重启后全部失效）
_valid_gp_tokens: set = set()

def _make_gp_token(pin: str) -> str:
    """基于 PIN + 密钥 + 时间窗口 生成会话令牌"""
    raw = f"{pin}:{GP_SESSION_SECRET}:{int(time.time())}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]

def verify_gp_token(token: str) -> bool:
    """校验 GP 会话令牌是否有效"""
    return token in _valid_gp_tokens

def require_gp_auth(x_gp_token: str = Header(None)):
    """GP API 端点鉴权 —— 从请求头 X-GP-Token 读取会话令牌"""
    if not x_gp_token or not verify_gp_token(x_gp_token):
        raise HTTPException(status_code=403, detail="GP 身份验证失败，请重新登录后台。")
    return True

class VerifyReq(BaseModel): pin: str

@app.post("/api/v1/lp/verify")
def verify_lp(req: VerifyReq):
    if req.pin == "0103": return {"status": "success"}
    raise HTTPException(status_code=403, detail="授权码错误。")

@app.post("/api/v1/gp/verify")
def verify_gp(req: VerifyReq):
    if req.pin == GP_PIN:
        token = _make_gp_token(req.pin)
        _valid_gp_tokens.add(token)
        return {"status": "success", "gp_token": token}
    raise HTTPException(status_code=403, detail="授权码错误。")

@app.post("/api/v1/gp/logout")
def gp_logout(token: str = Form(...)):
    """GP 主动登出，销毁会话令牌"""
    _valid_gp_tokens.discard(token)
    return {"status": "success"}

# ══════════════════════════════════════════════
# 🔐 WebAuthn 指纹/面容解锁
# ══════════════════════════════════════════════
import struct as _struct
import hashlib as _hashlib
from base64 import urlsafe_b64decode, urlsafe_b64encode

_webauthn_challenges: dict = {}

def _b64_decode(s: str) -> bytes:
    s = s.replace('-', '+').replace('_', '/')
    padding = 4 - len(s) % 4
    if padding != 4: s += '=' * padding
    return urlsafe_b64decode(s.encode() if isinstance(s, str) else s)

def _b64_encode(b: bytes) -> str:
    return urlsafe_b64encode(b).decode().rstrip('=')

def _parse_cose_key(cose_bytes: bytes) -> dict:
    """最小 CBOR 解析：只处理 COSE EC2 P-256 密钥"""
    pos = 0
    data = cose_bytes
    result = {}
    def _read_cbor():
        nonlocal pos
        if pos >= len(data): return None
        fb = data[pos]; pos += 1
        mt = (fb >> 5) & 0x7; ai = fb & 0x1f
        if ai < 24: arg = ai
        elif ai == 24: arg = data[pos]; pos += 1
        elif ai == 25: arg = int.from_bytes(data[pos:pos+2], 'big'); pos += 2
        elif ai == 26: arg = int.from_bytes(data[pos:pos+4], 'big'); pos += 4
        else: raise ValueError(f"unsupported additional info {ai}")
        if mt == 0: return arg       # uint
        if mt == 1: return -1 - arg  # nint
        if mt == 2:                  # bytes
            b = data[pos:pos+arg]; pos += arg; return b
        if mt == 5:                  # map
            m = {}
            for _ in range(arg): m[_read_cbor()] = _read_cbor()
            return m
        return arg
    return _read_cbor()

def _webauthn_verify_assertion(credential_id: str, authenticator_data_b64: str, client_data_json_b64: str, signature_b64: str) -> bool:
    """验证 WebAuthn assertion 签名"""
    global SessionLocal
    db = SessionLocal()
    try:
        rec = db.query(DBWebAuthnCred).filter(DBWebAuthnCred.credential_id == credential_id).first()
        if not rec:
            print(f"WebAuthn: credential not found in DB")
            return False

        # 解码所有 base64url 参数
        authenticator_data = _b64_decode(authenticator_data_b64)
        client_json_raw = _b64_decode(client_data_json_b64)
        sig = _b64_decode(signature_b64)

        # SHA256(clientDataJSON)
        client_hash = _hashlib.sha256(client_json_raw).digest()
        signed_data = authenticator_data + client_hash

        # 重建公钥
        x_bytes = bytes.fromhex(rec.public_key_x)
        y_bytes = bytes.fromhex(rec.public_key_y)
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature, encode_dss_signature

        pub_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b'\x04' + x_bytes + y_bytes)

        # WebAuthn ES256 签名是 ASN.1 DER 编码
        # DER格式: 0x30 len 0x02 r_len r_bytes 0x02 s_len s_bytes
        # 先检查是否是 raw 格式（64字节 = 两个32字节整数）
        if len(sig) == 64:
            sig_r = int.from_bytes(sig[:32], 'big')
            sig_s = int.from_bytes(sig[32:], 'big')
            der_sig = encode_dss_signature(sig_r, sig_s)
        elif len(sig) >= 68 and sig[0] == 0x30:
            # 已经是 DER 格式，直接使用
            r_len = sig[3]
            r_start = 4
            r_end = r_start + r_len
            s_start = r_end + 2  # skip 0x02 tag
            s_len = sig[r_end + 1]
            s_end = s_start + s_len
            sig_r = int.from_bytes(sig[r_start:r_end], 'big')
            sig_s = int.from_bytes(sig[s_start:s_end], 'big')
            der_sig = encode_dss_signature(sig_r, sig_s)
        else:
            print(f"WebAuthn: unknown signature format, len={len(sig)}, first_bytes={sig[:4].hex()}")
            return False

        pub_key.verify(der_sig, signed_data, ec.ECDSA(hashes.SHA256()))
        return True
    except Exception as e:
        print(f"WebAuthn verify error: {type(e).__name__}: {e}")
        import traceback; traceback.print_exc()
        return False
    finally:
        db.close()

@app.post("/api/v1/gp/webauthn/register")
def gp_webauthn_register(credential: str = Form(...), x: str = Form(...), y: str = Form(...), token: str = Form(None), pin: str = Form(None), db: Session = Depends(get_db)):
    """注册指纹凭证（需先通过 PIN 或 token 验证）"""
    # 验证身份
    if token and verify_gp_token(token): pass
    elif pin and pin == GP_PIN: pass
    else: raise HTTPException(status_code=403, detail="请先输入PIN验证身份后再注册指纹")

    existing = db.query(DBWebAuthnCred).filter(DBWebAuthnCred.credential_id == credential).first()
    if existing:
        existing.public_key_x = x; existing.public_key_y = y
    else:
        db.add(DBWebAuthnCred(credential_id=credential, public_key_x=x, public_key_y=y))
    db.commit()
    return {"status": "success", "message": "指纹已注册！下次可用指纹解锁。"}

@app.get("/api/v1/gp/webauthn/ready")
def gp_webauthn_ready():
    """检查是否有已注册的指纹凭证，返回凭证ID列表"""
    db = SessionLocal()
    try:
        creds = db.query(DBWebAuthnCred).all()
        return {"has_credential": len(creds) > 0,
                "credential_ids": [c.credential_id for c in creds]}
    finally:
        db.close()

@app.post("/api/v1/gp/webauthn/reset")
def gp_webauthn_reset(db: Session = Depends(get_db)):
    """清除所有已注册的指纹凭证"""
    db.query(DBWebAuthnCred).delete()
    db.commit()
    return {"status": "success", "message": "指纹凭证已全部清除"}

@app.post("/api/v1/gp/webauthn/auth")
async def gp_webauthn_auth(request: Request, db: Session = Depends(get_db)):
    """指纹验证登录"""
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="Invalid request body")

    credential_id = body.get("id")
    authenticator_data_b64 = body.get("authenticatorData")
    client_data_json = body.get("clientDataJSON")
    signature_b64 = body.get("signature")

    if not all([credential_id, authenticator_data_b64, client_data_json, signature_b64]):
        raise HTTPException(status_code=400, detail="缺少认证参数")

    ok = _webauthn_verify_assertion(credential_id, authenticator_data_b64, client_data_json, signature_b64)
    if not ok:
        raise HTTPException(status_code=403, detail="指纹验证失败，请重试或使用PIN登录")

    token = _make_gp_token(GP_PIN)
    _valid_gp_tokens.add(token)
    return {"status": "success", "gp_token": token, "message": "指纹验证通过！"}

@app.get("/api/v1/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    nav = calculate_system_nav(db, date.today())
    allocation_result = get_display_allocations(db, nav["R_total"])
    return {
        "nav": nav,
        "ledger": db.query(DBTransaction).order_by(desc(DBTransaction.tx_date), desc(DBTransaction.id)).limit(20).all(),
        "allocations": allocation_result["allocations"],
        "allocation_meta": allocation_result["meta"],
        "quarterly_info": get_quarterly_info(db)
    }

@app.get("/api/v1/lp/notices")
def lp_get_notices(db: Session = Depends(get_db)):
    notices = db.query(DBNotice).order_by(desc(DBNotice.id)).limit(5).all()
    return [{"id": n.id, "content": n.content, "publish_time": n.publish_time.strftime("%Y-%m-%d %H:%M")} for n in notices]

@app.post("/api/v1/gp/notices")
def gp_post_notice(content: str = Form(...), db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    db.add(DBNotice(content=content))
    db.commit()
    return {"status": "success", "message": "全网通知已强势发布！"}

# 👉 新增：GP 撤回通知的绝杀接口
@app.delete("/api/v1/gp/notices/{notice_id}")
def gp_delete_notice(notice_id: int, db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    notice = db.query(DBNotice).filter(DBNotice.id == notice_id).first()
    if notice:
        db.delete(notice)
        db.commit()
        return {"status": "success", "message": "指令已执行，该通知已从全网彻底抹除！"}
    raise HTTPException(status_code=404, detail="找不到该通知，可能已被撤回。")

@app.get("/api/v1/messages")
def get_messages(db: Session = Depends(get_db)):
    msgs = db.query(DBMessage).order_by(desc(DBMessage.id)).limit(10).all()
    out = []
    for m in msgs:
        out.append({
            "id": m.id,
            "content": m.content,
            "attachment_url": m.attachment_url,
            "created_date": m.created_date.strftime("%Y-%m-%d %H:%M") if m.created_date else None,
            "reply": m.reply,
            "reply_time": m.reply_time.strftime("%Y-%m-%d %H:%M") if m.reply_time else None
        })
    return out

@app.post("/api/v1/lp/messages")
async def post_message(content: str = Form(...), file: UploadFile = File(None), db: Session = Depends(get_db)):
    attachment_url = None
    
    # 如果提供了文件，进行处理
    if file and file.filename:
        file_content = await file.read()
        
        # 获取MIME类型
        mime_type = file.content_type or ""
        
        # 验证文件类型和大小
        if mime_type in ALLOWED_IMAGE_TYPES:
            if len(file_content) > MAX_IMAGE_SIZE:
                raise HTTPException(status_code=400, detail="图片文件过大（最多10MB）。")
        elif mime_type in ALLOWED_VIDEO_TYPES:
            if len(file_content) > MAX_VIDEO_SIZE:
                raise HTTPException(status_code=400, detail="视频文件过大（最多50MB）。")
        else:
            raise HTTPException(status_code=400, detail=f"不支持的文件类型。仅支持 JPG/PNG/GIF/WebP 或 MP4/WebM/MOV。")
        
        # 生成安全的文件名
        file_ext = os.path.splitext(file.filename)[1].lower()
        safe_name = f"{secrets.token_hex(16)}{file_ext}"
        save_path = os.path.join(MESSAGES_UPLOAD_DIR, safe_name)
        
        with open(save_path, "wb") as f:
            f.write(file_content)
        
        attachment_url = f"uploads/messages/{safe_name}"
    
    try:
        db.add(DBMessage(content=content, attachment_url=attachment_url))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="留言写入失败，请检查服务器数据库写权限。")
    
    notify_gp_wechat("💬 家庭办公室新留言", f"乙方有话对你说：\n{content}")
    return {"status": "success"}

@app.get("/api/v1/lp/limit_status")
def get_limit_status(db: Session = Depends(get_db)):
    limit = get_dynamic_monthly_limit()
    used = get_current_month_used(db)
    return {"monthly_limit": limit, "used_amount": used, "remaining": round(limit - used, 2)}

@app.post("/api/v1/lp/request_withdrawal")
def lp_request_withdrawal(amount: float = Form(...), reason: str = Form(...), db: Session = Depends(get_db)):
    limit = get_dynamic_monthly_limit()
    if get_current_month_used(db) + amount > limit: raise HTTPException(status_code=403, detail="触发熔断！超限。")
    try:
        db.add(DBRequest(req_type="WITHDRAWAL_REQ", amount=amount, reason=reason))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="工单写入失败，请检查服务器数据库写权限。")
    notify_gp_wechat("🚨 资金提款申请", f"弟弟申请提取 ¥{amount}\n理由：{reason}") # 👉 新加的这行
    return {"status": "success", "message": "工单提交成功，等待 GP 审核。"}

@app.post("/api/v1/lp/claim_quarterly")
def claim_quarterly(db: Session = Depends(get_db)):
    event = db.query(DBQuarterlyEvent).order_by(desc(DBQuarterlyEvent.id)).first()
    if not event or event.status != "ACTIVE": raise HTTPException(status_code=403, detail="当前没有可领取的派息令。")
    if datetime.now() > event.issued_at + timedelta(hours=72):
        event.status = "EXPIRED"; db.commit()
        raise HTTPException(status_code=403, detail="手慢了！超过72小时，派息令已自动作废。")
    event.status = "CLAIMED"
    event.claimed_at = datetime.now()
    db.add(DBTransaction(tx_type="QUARTERLY_PAYOUT", amount=30.0, description="季度法定流动性派发提取"))
    db.commit()
    return {"status": "success", "message": "30元现钞已落袋为安！"}

@app.post("/api/v1/lp/request_alpha")
async def lp_request_alpha(reason: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 👉 核心升级：读取文件内容并校验大小
    file_content = await file.read()
    
    # 后端硬性规定：大于 5MB (5 * 1024 * 1024 字节) 直接打回！
    if len(file_content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="拦截！后端检测到图片体积超过 5MB 的物理限制。")
        
    # 如果没超标，再安安稳稳地存入硬盘
    safe_name = os.path.basename(file.filename)
    loc = os.path.join(UPLOAD_DIR, safe_name)
    with open(loc, "wb") as f: 
        f.write(file_content)
    proof_url = f"uploads/{safe_name}"
        
    try:
        db.add(DBRequest(req_type="ALPHA_REQ", amount=0.0, reason=reason, proof_image=proof_url))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="工单写入失败，请检查服务器数据库写权限。")
    
    # 顺便把咱们的微信通知也带上
    notify_gp_wechat("📈 阿尔法红利申请", f"弟弟提交了一份奖金凭证\n达标说明：{reason}\n请尽快登录后台查阅图片并核定金额。")
    return {"status": "success", "message": "阿尔法凭证已上传成功！"}

@app.get("/api/v1/lp/my_requests")
def lp_get_my_requests(db: Session = Depends(get_db)):
    """获取乙方提交的最新 10 条工单 (防止历史包袱过重)"""
    # 1. 先从数据库里把原生的数据捞出来
    requests = db.query(DBRequest).order_by(desc(DBRequest.req_date), desc(DBRequest.id)).limit(10).all()
    
    # 2. 手动打包！翻译成前端能看懂的格式
    req_list = []
    for r in requests:
        req_list.append({
            "id": r.id,
            "req_date": str(r.req_date),  # 关键！把日期强制转成字符串，FastAPI 就不懵了
            "req_type": r.req_type,
            "amount": r.amount,
            "reason": r.reason,
            "status": r.status
        })
        
    # 3. 把打包好的漂亮盒子送给前端
    return req_list

# 🎰 博彩：LP 端点

@app.get("/api/v1/lp/lottery_status")
def lp_lottery_status(db: Session = Depends(get_db)):
    _ensure_default_config(db)
    _ensure_default_prizes(db)
    cost = float(_get_config(db, "LOTTERY_COST", "5.00"))
    enabled = _get_config(db, "LOTTERY_ENABLED", "1") == "1"
    nav = calculate_system_nav(db, date.today())["R_total"]
    prizes = db.query(DBLotteryPrize).filter(DBLotteryPrize.is_active == 1).all()
    records = db.query(DBLotteryRecord).order_by(desc(DBLotteryRecord.id)).limit(10).all()
    return {
        "enabled": enabled,
        "cost": cost,
        "current_nav": nav,
        "can_play": enabled and nav >= cost,
        "prizes": [{"id": p.id, "name": p.name, "icon": p.icon, "weight": p.weight, "prize_type": p.prize_type} for p in prizes],
        "recent_records": [{"id": r.id, "draw_time": r.draw_time.strftime("%H:%M:%S") if r.draw_time else "", "cost": r.cost, "prize_name": r.prize_name, "prize_value": r.prize_value, "result_type": r.result_type} for r in records]
    }

@app.post("/api/v1/lp/lottery_draw")
def lp_lottery_draw(db: Session = Depends(get_db)):
    _ensure_default_config(db)
    _ensure_default_prizes(db)
    nav = calculate_system_nav(db, date.today())["R_total"]
    result = execute_lottery_draw(db, nav)
    return result

@app.get("/api/v1/lp/lottery_history")
def lp_lottery_history(db: Session = Depends(get_db)):
    records = db.query(DBLotteryRecord).order_by(desc(DBLotteryRecord.id)).limit(30).all()
    return [{"id": r.id, "draw_time": r.draw_time.strftime("%Y-%m-%d %H:%M:%S") if r.draw_time else "", "cost": r.cost, "prize_name": r.prize_name, "prize_value": r.prize_value, "result_type": r.result_type} for r in records]

@app.post("/api/v1/gp/messages/{msg_id}/reply")
def reply_message(msg_id: int, reply: str = Form(...), db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    msg = db.query(DBMessage).filter(DBMessage.id == msg_id).first()
    if msg:
        msg.reply = reply
        msg.reply_time = datetime.now()
        db.commit()
    return {"status": "success"}

@app.post("/api/v1/gp/inject_funds")
def gp_inject_funds(amount: float = Form(...), tx_type: str = Form(...), description: str = Form(...), db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    db.add(DBTransaction(tx_type=tx_type, amount=amount, description=description)); db.commit()
    return {"status": "success", "message": f"资金注入成功！已将 ¥{amount} 并入 {tx_type} 引擎。"}

@app.post("/api/v1/gp/adjust_funds")
def gp_adjust_funds(action: str = Form(...), amount: float = Form(...), description: str = Form(...), db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    if amount <= 0: raise HTTPException(status_code=400, detail="调整金额必须大于0")
    tx_type = "ADJUST_UP" if action == "UP" else "ADJUST_DOWN"
    db.add(DBTransaction(tx_type=tx_type, amount=amount, description=f"【上帝模式强控】{description}"))
    db.commit()
    verb = "强行注入" if action == "UP" else "强行扣除"
    return {"status": "success", "message": f"强控执行完毕：已从资金池{verb} ¥{amount}。"}

@app.post("/api/v1/gp/toggle_quarterly")
def toggle_quarterly(db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    active = db.query(DBQuarterlyEvent).filter(DBQuarterlyEvent.status == "ACTIVE").all()
    for a in active: a.status = "EXPIRED"
    db.add(DBQuarterlyEvent(issued_at=datetime.now(), status="ACTIVE")); db.commit()
    return {"status": "success", "message": "72小时倒计时派息令已强势发布！"}

@app.get("/api/v1/gp/pending_requests")
def gp_get_pending_requests(db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    requests = db.query(DBRequest).filter(DBRequest.status == "PENDING").order_by(desc(DBRequest.req_date), desc(DBRequest.id)).all()
    return [{
        "id": r.id,
        "req_date": str(r.req_date),
        "req_type": r.req_type,
        "amount": r.amount,
        "reason": r.reason,
        "proof_image": r.proof_image,
        "status": r.status
    } for r in requests]

@app.get("/api/v1/gp/notification_logs")
def gp_get_notification_logs(limit: int = 30, status_filter: str = "ALL", db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    safe_limit = max(1, min(limit, 100))
    query = db.query(DBNotificationLog)
    sf = (status_filter or "ALL").upper()
    if sf in ["SUCCESS", "FAILED"]:
        query = query.filter(DBNotificationLog.status == sf)
    logs = query.order_by(desc(DBNotificationLog.id)).limit(safe_limit).all()
    return [{
        "id": item.id,
        "created_at": item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else None,
        "channel": item.channel,
        "title": item.title,
        "status": item.status,
        "response_msg": item.response_msg,
    } for item in logs]

@app.post("/api/v1/gp/notification_logs/{log_id}/retry")
def gp_retry_notification(log_id: int, db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    item = db.query(DBNotificationLog).filter(DBNotificationLog.id == log_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="通知日志不存在")

    ok = notify_gp_wechat(item.title, item.content)
    if ok:
        return {"status": "success", "message": "重发成功"}
    return {"status": "error", "message": "重发失败，请查看最新日志"}

@app.post("/api/v1/gp/process_request/{req_id}")
def gp_process_request(req_id: int, action: str, final_amount: float = 0.0, reject_reason: str = "", db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    req = db.query(DBRequest).filter(DBRequest.id == req_id).first()
    if action == "REJECT": 
        req.status = "REJECTED"
        req.amount = 0.0 
        if reject_reason: req.reason = req.reason + f" 【GP驳回: {reject_reason}】"
    if action == "APPROVE":
        req.status = "APPROVED"
        actual = final_amount if req.req_type == "ALPHA_REQ" else req.amount
        if req.req_type == "ALPHA_REQ": req.amount = final_amount
        db.add(DBTransaction(tx_type="WITHDRAWAL" if req.req_type == "WITHDRAWAL_REQ" else "ALPHA", amount=actual, description=f"审计批准: {req.reason}"))
    db.commit()
    return {"status": "success", "message": f"工单审批完成！已执行 {action} 指令。"}

@app.post("/api/v1/gp/asset_allocation")
def gp_update_allocation(asset_name: str = Form(...), amount: float = Form(...), db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    nav = calculate_system_nav(db, date.today())
    existing = db.query(DBAssetAllocation).filter(DBAssetAllocation.asset_name == asset_name).first()
    if amount <= 0:
        if existing: db.delete(existing); db.commit()
        return {"status": "success", "message": f"标的 [{asset_name}] 已被清仓。"}
    other_sum = sum([a.allocated_amount for a in db.query(DBAssetAllocation).filter(DBAssetAllocation.asset_name != asset_name).all()])
    if other_sum + amount > nav["R_total"]: raise HTTPException(status_code=400, detail="可分配金额不足，请勿加杠杆！")
    if existing: existing.allocated_amount = amount
    else: db.add(DBAssetAllocation(asset_name=asset_name, allocated_amount=amount))
    db.commit()
    return {"status": "success", "message": f"资产配置已更新: {asset_name} -> ¥{amount}"}

# ── 博彩：GP 控制端点 ──────────────────────

@app.get("/api/v1/gp/lottery_config")
def gp_lottery_config(db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    """GP 查看博彩完整配置"""
    _ensure_default_config(db)
    _ensure_default_prizes(db)
    prizes = db.query(DBLotteryPrize).order_by(DBLotteryPrize.id).all()
    return {
        "cost": float(_get_config(db, "LOTTERY_COST", "5.00")),
        "enabled": _get_config(db, "LOTTERY_ENABLED", "1") == "1",
        "prizes": [{"id": p.id, "name": p.name, "prize_type": p.prize_type, "value": p.value, "weight": p.weight, "is_active": bool(p.is_active), "icon": p.icon} for p in prizes]
    }

@app.post("/api/v1/gp/lottery_config")
def gp_lottery_config_update(
    cost: float = Form(None),
    enabled: int = Form(None),
    prize_id: int = Form(None),
    action: str = Form(None),  # add / edit / delete / toggle
    prize_name: str = Form(None),
    prize_type: str = Form(None),
    prize_value: float = Form(None),
    prize_weight: int = Form(None),
    prize_icon: str = Form(None),
    db: Session = Depends(get_db),
    _: bool = Depends(require_gp_auth)
):
    """GP 管理博彩配置：更新成本/开关/奖品"""
    _ensure_default_config(db)
    _ensure_default_prizes(db)

    # 更新系统参数
    if cost is not None and cost > 0:
        _set_config(db, "LOTTERY_COST", str(round(cost, 2)))
    if enabled is not None:
        _set_config(db, "LOTTERY_ENABLED", "1" if enabled else "0")

    # 奖品管理
    if action == "add" and prize_name and prize_type:
        db.add(DBLotteryPrize(
            name=prize_name, prize_type=prize_type, value=prize_value or 0.0,
            weight=prize_weight or 10, icon=prize_icon or "🎁"
        ))
        db.commit()
        return {"status": "success", "message": f"奖品 [{prize_name}] 已添加"}

    if action == "delete" and prize_id:
        p = db.query(DBLotteryPrize).filter(DBLotteryPrize.id == prize_id).first()
        if p:
            db.delete(p)
            db.commit()
            return {"status": "success", "message": f"奖品 [{p.name}] 已删除"}
        raise HTTPException(status_code=404, detail="奖品不存在")

    if action == "toggle" and prize_id is not None:
        p = db.query(DBLotteryPrize).filter(DBLotteryPrize.id == prize_id).first()
        if p:
            p.is_active = 0 if p.is_active else 1
            db.commit()
            return {"status": "success", "message": f"奖品 [{p.name}] 已{'启用' if p.is_active else '停用'}"}
        raise HTTPException(status_code=404, detail="奖品不存在")

    if action == "edit" and prize_id:
        p = db.query(DBLotteryPrize).filter(DBLotteryPrize.id == prize_id).first()
        if p:
            if prize_name is not None: p.name = prize_name
            if prize_type is not None: p.prize_type = prize_type
            if prize_value is not None: p.value = prize_value
            if prize_weight is not None: p.weight = prize_weight
            if prize_icon is not None: p.icon = prize_icon
            db.commit()
            return {"status": "success", "message": f"奖品 [{p.name}] 已更新"}
        raise HTTPException(status_code=404, detail="奖品不存在")

    return {"status": "success", "message": "配置已更新"}

@app.get("/api/v1/gp/lottery_stats")
def gp_lottery_stats(db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    """GP 查看博彩统计数据"""
    records = db.query(DBLotteryRecord).all()
    total = len(records)
    total_cost = sum(r.cost for r in records)
    total_payout = sum(r.prize_value for r in records)
    wins = len([r for r in records if r.result_type == "WIN"])
    jackpots = len([r for r in records if r.result_type == "JACKPOT"])
    loses = len([r for r in records if r.result_type == "LOSE"])
    return {
        "total_draws": total,
        "total_cost": round(total_cost, 2),
        "total_payout": round(total_payout, 2),
        "net_profit": round(total_cost - total_payout, 2),
        "profit_rate": round((total_cost - total_payout) / total_cost * 100, 1) if total_cost > 0 else 0,
        "wins": wins, "jackpots": jackpots, "loses": loses,
        "recent": [{"id": r.id, "draw_time": r.draw_time.strftime("%m-%d %H:%M") if r.draw_time else "", "cost": r.cost, "prize_name": r.prize_name, "prize_value": r.prize_value, "result_type": r.result_type} for r in records[-10:]]
    }

@app.post("/api/v1/gp/lottery_reset")
def gp_lottery_reset(db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    """GP 清空抽奖记录（保留配置和奖品）"""
    db.query(DBLotteryRecord).delete()
    db.commit()
    return {"status": "success", "message": "抽奖记录已清空"}


# ==========================================
# 4. 页面路由
# ==========================================
@app.get("/", include_in_schema=False)
def index_page():
    return FileResponse(os.path.join(BASE_DIR, "dashboard.html"))


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(os.path.join(BASE_DIR, "admin.html"))


@app.get("/video_call", include_in_schema=False)
def video_call_page():
    return FileResponse(os.path.join(BASE_DIR, "video_call.html"))