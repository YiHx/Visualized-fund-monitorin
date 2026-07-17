from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, status, WebSocket, WebSocketDisconnect, Header, Request

# ╔══════════════════════════════════════════════════════════════════╗
# ║    家庭高净值资产控制系统  v2.5                                  ║
# ║    Family High-Net-Worth Asset Control System                   ║
# ║    Backend: FastAPI + SQLAlchemy + SQLite                       ║
# ║    Powered by 远坂凛 の 宝石魔術 ✨                              ║
# ╚══════════════════════════════════════════════════════════════════╝
#
# 　　　　 ∧＿∧
# 　　　（｀・ω・´）  「弟の資産は私が守る！」
# 　　 （つ　　⊂）　　   ── 遠坂 凛 ──
# 　　 と＿)_) ＿)
#
#   (•_•)      「このコード、完璧ね」
#   ( •_•)>⌐■-■   "This code... is perfect."
#   (⌐■_■)
#
#   ★ 宝石剑Zelretch™ · NAV自动守护 ★
#   ～ ビリビリ ビリビリ BILIBILI (゜-゜)つロ 乾杯~ ～
#
#   Architecture:
#   ┌──────────┐    ┌──────────┐    ┌──────────┐
#   │ dashboard │◄──►│  FastAPI  │◄──►│  SQLite   │
#   │  (弟弟)   │    │  (凛守护) │    │  (宝石)   │
#   └──────────┘    └──────────┘    └──────────┘
#         ▲               ▲               ▲
#         │               │               │
#         ▼               ▼               ▼
#   ┌──────────┐    指 紋 認 証    🔐 GP 后台密码保护
#   │  admin    │    (Touch ID)     Yhx2582413!@
#   │  (哥哥)   │
#   └──────────┘
#
#   令咒 Command Spells:
#   💎 /api/v1/dashboard        — NAV计算
#   💎 /api/v1/lp/lottery_draw  — 抽奖引擎
#   💎 /api/v1/gp/lottery_config — GP配置
#   💎 /api/v1/gp/verify        — GP身份验证
#   💎 /ws/video_call/...       — 视频通话
#
#   Developer Notes:
#   このシステムは遠坂凛の宝石魔術によって守られています
#   (This system is protected by Tohsaka Rin's Jewel Magecraft)
#
#   BILIBILI (゜-゜)つロ 乾杯~ ∽∽∽
#
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response, PlainTextResponse
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

# ── 抽奖系统模型 ────────────────────────────────
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



# ── 白客CTF系统模型 ────────────────────────────
class DBCTFFlag(Base):
    __tablename__ = "ctf_flags"
    id = Column(Integer, primary_key=True, index=True)
    flag_key = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    points = Column(Integer, nullable=False, default=10)
    difficulty = Column(String, nullable=False, default="easy")
    found_by = Column(String, nullable=True)
    found_at = Column(DateTime, nullable=True)

class DBCTFHint(Base):
    __tablename__ = "ctf_hints"
    id = Column(Integer, primary_key=True, index=True)
    flag_key = Column(String, nullable=False)
    hint_text = Column(String, nullable=False)
    hint_order = Column(Integer, default=0)

class DBShortcut(Base):
    __tablename__ = "fun_shortcuts"
    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, unique=True, nullable=False)
    title = Column(String, nullable=False)
    target_url = Column(String, nullable=False)
    icon = Column(String, nullable=False, default="🔗")
    description = Column(String, nullable=True)
    category = Column(String, nullable=False, default="other")
    is_active = Column(Integer, nullable=False, default=1)

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

# 🕵️ CTF H# 🕵️ CTF Headers — ASCII only to avoid Unicode errors
@app.middleware("http")
async def ctf_header_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Hint"] = "Try /robots.txt and view page source!"
    response.headers["X-CTF-Challenge"] = "Find all 11 FLAG{...} tokens hidden in this site!"
    response.headers["X-Powered-By"] = "Rin-Tohsaka-Jewel-Magecraft-v2.5"
    response.headers["X-Flag-3"] = "FLAG{http_headers_tell_all}"
    response.headers["X-Next-Step"] = "Check Cookies and source code for more flags"
    return response

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
# 2.5 趣味抽奖引擎
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
        raise HTTPException(status_code=403, detail="抽奖系统当前已关闭。")
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

    db.add(DBTransaction(tx_type="ADJUST_DOWN", amount=cost, description=f"\U0001f3b0 趣味抽奖：{won_prize.name}"))

    if prize_value > 0:
        db.add(DBTransaction(tx_type="ADJUST_UP", amount=prize_value, description=f"\U0001f3b0 抽奖中奖：{won_prize.name}，奖金 ¥{prize_value:.2f}"))

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
    # 🕵️ CTF: SQL injection detection
    pin = req.pin.strip()
    sqli = ["' OR '1'='1", "' OR 1=1", '" OR "1"="1', "OR 1=1", "'--", "admin'--"]
    if any(p.lower() in pin.lower() for p in sqli):
        return {"status": "ctf_detected", "message": "🕵️ SQL注入检测！思路正确！Flag: FLAG{sql_injection_is_still_a_thing}", "flag": "FLAG{sql_injection_is_still_a_thing}"}
    if pin == "0103": return {"status": "success"}
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
    """GP API endpoint auth — read session token from X-GP-Token header"""
    if not x_gp_token or not verify_gp_token(x_gp_token):
        raise HTTPException(status_code=403, detail="GP identity verification failed. Please log in again.")
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

# 🎰 抽奖：LP 端点

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

# ── 抽奖：GP 控制端点 ──────────────────────

@app.get("/api/v1/gp/lottery_config")
def gp_lottery_config(db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    """GP 查看抽奖完整配置"""
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
    """GP 管理抽奖配置：更新成本/开关/奖品"""
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
    """GP 查看抽奖统计数据"""
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
# 🎉 趣味页面 + 下载 + 短链接管理
# ==========================================

FUN_FILES_DIR = os.path.join(BASE_DIR, "funfiles")
if not os.path.exists(FUN_FILES_DIR):
    os.makedirs(FUN_FILES_DIR)

# 自动生成趣味下载文件
def _ensure_fun_files():
    files = {
        "navy_secret.txt": "🤫 绝密文件 — 仅供弟弟查阅 🤫\n\n═══════════════════════════════════\n  家庭基金 · 最高机密卷宗 #42\n═══════════════════════════════════\n\n致 弟弟：\n\n  经过我方情报人员的长期观察（其实就是GP本人），\n  现确认以下事实：\n\n  1. 你的NAV目前已突破 ¥1,000 大关\n  2. 你的抽奖运势评级：★★★★★（五星）\n  3. GP对你的评价：『唯一的缺点就是太乖了』\n  4. 本文件将在阅读后60秒内自动销毁（并不会）\n\n签名：\n  远坂 凛 (GP 资产守护灵)\n  2026年7月17日\n\n═══════════════════════════════════════\n  🦭 盖章：弟弟最棒！认证完毕 🦭\n═══════════════════════════════════════",
        "rin_blessing.txt": "💎 遠坂凛 · NAV祝福之詩 💎\n\n　　✨　 ／＼／＼／＼　✨\n　 ＜  NAVよ、上がれ！  ＞\n　　✨　 ＼／＼／＼／　✨\n\n　　「私の宝石魔術で、\n　　　 この資産を守り抜く！」\n\n　　　　─ 遠坂 凛 ─\n\n　　＊　＊　＊　＊　＊\n\n　弟よ、このお守りを\n　受け取りなさい 💎\n\n　効能：NAV増加 · 抽選運UP\n　有効期限：永遠\n\n　＊　＊　＊　＊　＊",
        "easter_eggs.txt": "🥚 网站彩蛋大全 🥚\n\n键盘输入:\n  42 → 全屏🐬\n  help → 伪终端\n  ↑↑↓↓←→←→BA → 大撒花\n\n鼠标操作:\n  连击NAV 5次 → 彩蛋\n  滚到底 → 🍪提醒\n\n网址彩蛋:\n  /42 → 生命宇宙的答案\n  /rickroll → 你懂的\n  /secret → 后台入口\n\n更多隐藏彩蛋等你发现 🔍\n(温馨提示: F12有惊喜)",
        "bitcoin_wallet.txt": "⚠️ 比特币私钥（绝对机密）⚠️\n\n钱包地址: 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa\n私钥: L2... 哈哈哈哈骗你的 😂\n\n真实情况：\n  你没有任何比特币\n  但是你有 ¥{nav} 的家庭基金！\n  这比比特币靠谱多了 💪\n\n  — GP 留",
    }
    for name, content in files.items():
        fpath = os.path.join(FUN_FILES_DIR, name)
        if not os.path.exists(fpath):
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)

_ensure_fun_files()

# 种子短链接数据
def _ensure_default_shortcuts(db: Session):
    if db.query(DBShortcut).count() > 0:
        return
    defaults = [
        DBShortcut(path="bilibili", title="BILIBILI干杯！", target_url="https://www.bilibili.com", icon="📺", description="(゜-゜)つロ 乾杯~", category="entertainment"),
        DBShortcut(path="b", title="B站（短）", target_url="https://www.bilibili.com", icon="📺", description="最快到达B站", category="entertainment"),
        DBShortcut(path="anime", title="番剧区", target_url="https://www.bilibili.com/anime", icon="🎬", description="二次元入口", category="entertainment"),
        DBShortcut(path="rin", title="远坂凛 UBW", target_url="https://www.bilibili.com/video/BV1GJ411x7h7", icon="💎", description="凛の魔術ショー", category="anime"),
        DBShortcut(path="fate", title="Fate/stay night", target_url="https://www.bilibili.com/bangumi/media/md28236452", icon="⚔️", description="聖杯戦争、始まる", category="anime"),
        DBShortcut(path="rickroll", title="Rick Astley", target_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ", icon="🕺", description="Never Gonna Give You Up", category="fun"),
        DBShortcut(path="42", title="生命的答案", target_url="https://en.wikipedia.org/wiki/42_(number)", icon="🐬", description="The Answer to Life, the Universe, and Everything", category="fun"),
        DBShortcut(path="cat", title="吸猫", target_url="https://www.bilibili.com/video/BV1kQ4y1P7Pd", icon="🐱", description="治愈猫咪视频", category="chill"),
        DBShortcut(path="github", title="项目源码", target_url="https://github.com/YiHx/Visualized-fund-monitorin", icon="💻", description="给颗Star吧！", category="tech"),
        DBShortcut(path="secret", title="后台入口", target_url="/admin", icon="👑", description="甲方后台", category="internal"),
        DBShortcut(path="gp", title="GP控制台", target_url="/admin", icon="👑", description="甲方后台", category="internal"),
        DBShortcut(path="lp", title="LP前台", target_url="/", icon="📊", description="乙方前台", category="internal"),
    ]
    for s in defaults:
        db.add(s)
    db.commit()

# 趣味中心页面
@app.get("/fun", include_in_schema=False)
def fun_hub(db: Session = Depends(get_db)):
    _ensure_default_shortcuts(db)
    # 返回一个超炫的HTML页面，列出所有shortcuts
    shortcuts = db.query(DBShortcut).filter(DBShortcut.is_active == 1).order_by(DBShortcut.category, DBShortcut.id).all()
    download_files = [f for f in os.listdir(FUN_FILES_DIR) if os.path.isfile(os.path.join(FUN_FILES_DIR, f))]

    # 按分类整理
    cats = {}
    for s in shortcuts:
        cats.setdefault(s.category, []).append(s)

    sc_html = ""
    cat_icons = {"entertainment":"🎬","anime":"⚔️","fun":"🥚","chill":"☕","tech":"💻","internal":"🔐","other":"🔗"}
    for cat, items in cats.items():
        icon = cat_icons.get(cat, "🔗")
        sc_html += f'<div style="margin-bottom:18px"><h3 style="color:#fbbf24;margin-bottom:8px">{icon} {cat.upper()}</h3><div style="display:flex;flex-wrap:wrap;gap:8px">'
        for s in items:
            sc_html += f'<a href="{s.target_url}" target="_blank" style="display:flex;align-items:center;gap:6px;background:rgba(30,41,59,0.8);padding:8px 14px;border-radius:8px;text-decoration:none;color:#e2e8f0;border:1px solid #334155;transition:all 0.2s;font-size:13px" onmouseover="this.style.borderColor=\'#fbbf24\';this.style.background=\'rgba(251,191,36,0.1)\'" onmouseout="this.style.borderColor=\'#334155\';this.style.background=\'rgba(30,41,59,0.8)\'"><span style="font-size:18px">{s.icon}</span><div><div style="font-weight:bold">{s.title}</div><div style="font-size:10px;color:#94a3b8">{s.description or ""}</div></div></a>'
        sc_html += '</div></div>'

    dl_html = ""
    dl_icons = {"navy_secret.txt":"🤫","rin_blessing.txt":"💎","easter_eggs.txt":"🥚","bitcoin_wallet.txt":"💰"}
    for fname in download_files:
        icon = dl_icons.get(fname, "📄")
        size = os.path.getsize(os.path.join(FUN_FILES_DIR, fname))
        dl_html += f'<a href="/api/v1/fun/download/{fname}" style="display:flex;align-items:center;gap:8px;background:rgba(16,185,129,0.1);padding:10px 16px;border-radius:8px;text-decoration:none;color:#34d399;border:1px solid rgba(16,185,129,0.3);transition:all 0.2s;font-size:13px" onmouseover="this.style.background=\'rgba(16,185,129,0.2)\';this.style.borderColor=\'#34d399\'" onmouseout="this.style.background=\'rgba(16,185,129,0.1)\';this.style.borderColor=\'rgba(16,185,129,0.3)\'"><span style="font-size:20px">{icon}</span><div><div style="font-weight:bold">{fname}</div><div style="font-size:10px;color:#6ee7b7">{size} bytes</div></div><span style="margin-left:auto">⬇️</span></a>'

    return HTMLResponse(content=f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>🎉 趣味中心 | 家庭基金</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0f172a;color:#f8fafc;font-family:'Segoe UI',system-ui,sans-serif;min-height:100vh;padding:24px}}
.container{{max-width:900px;margin:0 auto}}
h1{{font-size:2.5rem;background:linear-gradient(135deg,#fbbf24,#f59e0b,#34d399);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:8px}}
.subtitle{{color:#94a3b8;margin-bottom:24px;font-size:14px}}
.card{{background:rgba(30,41,59,0.5);border:1px solid #1e293b;border-radius:16px;padding:20px;margin-bottom:16px}}
.card h2{{color:#f8fafc;margin-bottom:12px;font-size:18px;display:flex;align-items:center;gap:8px}}
.back-link{{display:inline-flex;align-items:center;gap:4px;color:#94a3b8;text-decoration:none;font-size:13px;margin-bottom:16px;transition:color 0.2s}}
.back-link:hover{{color:#fbbf24}}
footer{{text-align:center;color:#475569;font-size:11px;margin-top:32px;padding:16px 0;border-top:1px solid #1e293b}}
.rainbow{{animation:rainbow 3s linear infinite}}@keyframes rainbow{{0%{{filter:hue-rotate(0deg)}}100%{{filter:hue-rotate(360deg)}}}}
"""+sc_html+dl_html+"""</style></head><body><div class="container">
<a href="/" class="back-link">← 回到监控台</a>
<h1>🎉 趣味中心 <span class="rainbow">🌈</span></h1>
<p class="subtitle">短链接跳转 · 趣味下载 · 更多彩蛋 — 由远坂凛 💎 加持</p>
<div class="card"><h2>🔗 短链接跳转</h2>""" + sc_html + """</div>
<div class="card"><h2>📥 趣味下载</h2>""" + dl_html + """</div>
<footer>💎 凛 Protection Active · yhymoney.asia · (゜-゜)つロ 乾杯~</footer>
</div></body></html>""")

# 趣味下载端点
@app.get("/api/v1/fun/download/{filename}")
def fun_download(filename: str):
    fpath = os.path.join(FUN_FILES_DIR, filename)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(fpath, media_type="application/octet-stream", filename=filename)

# LP 端获取趣味列表
@app.get("/api/v1/fun/list")
def fun_list(db: Session = Depends(get_db)):
    _ensure_default_shortcuts(db)
    shortcuts = db.query(DBShortcut).filter(DBShortcut.is_active == 1).all()
    downloads = [{"name": f, "size": os.path.getsize(os.path.join(FUN_FILES_DIR, f))} for f in os.listdir(FUN_FILES_DIR) if os.path.isfile(os.path.join(FUN_FILES_DIR, f))]
    return {
        "shortcuts": [{"path": s.path, "title": s.title, "target_url": s.target_url, "icon": s.icon, "description": s.description, "category": s.category} for s in shortcuts],
        "downloads": downloads
    }

# GP 短链接管理
@app.get("/api/v1/gp/shortcuts")
def gp_shortcuts(db: Session = Depends(get_db), _: bool = Depends(require_gp_auth)):
    _ensure_default_shortcuts(db)
    shortcuts = db.query(DBShortcut).order_by(DBShortcut.id).all()
    return {"shortcuts": [{"id": s.id, "path": s.path, "title": s.title, "target_url": s.target_url, "icon": s.icon, "description": s.description or "", "category": s.category, "is_active": bool(s.is_active)} for s in shortcuts]}

@app.post("/api/v1/gp/shortcuts")
def gp_shortcuts_manage(
    action: str = Form(...),
    shortcut_id: int = Form(None),
    path: str = Form(None),
    title: str = Form(None),
    target_url: str = Form(None),
    icon: str = Form(None),
    description: str = Form(None),
    category: str = Form(None),
    db: Session = Depends(get_db),
    _: bool = Depends(require_gp_auth)
):
    _ensure_default_shortcuts(db)
    if action == "add" and path and title and target_url:
        db.add(DBShortcut(path=path, title=title, target_url=target_url, icon=icon or "🔗", description=description or "", category=category or "other"))
        db.commit()
        return {"status": "success", "message": f"短链接 /{path} 已添加！"}
    if action in ("delete", "toggle") and shortcut_id:
        s = db.query(DBShortcut).filter(DBShortcut.id == shortcut_id).first()
        if not s: raise HTTPException(status_code=404, detail="不存在")
        if action == "delete": db.delete(s)
        else: s.is_active = 0 if s.is_active else 1
        db.commit()
        return {"status": "success", "message": f"已{'删除' if action == 'delete' else '切换'}"}
    raise HTTPException(status_code=400, detail="参数不足")

# 动态短链接路由（DB驱动的，覆盖已有硬编码）
@app.get("/go/{path:path}", include_in_schema=False)
def go_shortcut(path: str, db: Session = Depends(get_db)):
    s = db.query(DBShortcut).filter(DBShortcut.path == path, DBShortcut.is_active == 1).first()
    if s: return RedirectResponse(url=s.target_url, status_code=302)
    raise HTTPException(status_code=404, detail=f"短链接 /{path} 不存在")



# ==========================================
# 🕵️ 白客训练场 CTF系统
# ==========================================

import random as _random

def _ensure_ctf_seeds(db: Session):
    """Seed 100 CTF challenges"""
    if db.query(DBCTFFlag).count() >= 90:
        return
    db.query(DBCTFFlag).delete()
    db.query(DBCTFHint).delete()
    flags = [
        DBCTFFlag(flag_key='FLAG{welcome_to_ctf}', title='👋 Welcome to CTF!', description='访问 /ctf 页面看看', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{view_source_is_step_one}', title='📜 查看源代码', description='右键→查看网页源代码，永远是你最好的朋友', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{http_headers_tell_all}', title='📨 HTTP响应头藏宝', description='F12→Network→刷新→点第一个请求→Response Headers', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{robots_are_not_your_enemy}', title='🤖 robots.txt 的秘密', description='访问 /robots.txt — 搜索引擎不想让你看的东西', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{source_code_is_your_friend}', title='🔍 HTML注释挖掘', description='查看网页源代码，找HTML注释 <!-- ... -->', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{console_is_your_best_friend}', title='💻 开发者控制台', description='F12→Console标签，看看log消息', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{cookies_are_delicious}', title='🍪 Cookie里藏了什么', description='F12→Application→Cookies→yhymoney.asia', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{meta_tags_hide_secrets}', title='🏷️ Meta标签探秘', description='查看页面 <head> 里的 <meta> 标签', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{f12_is_your_gateway}', title='🚪 F12是万能钥匙', description='Developer Tools是你进入渗透世界的大门', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{every_journey_begins_with_curiosity}', title='🌟 好奇心是最好的老师', description='你已经完成了入门关卡！继续前进吧！', points=10, difficulty="tutorial"),
        DBCTFFlag(flag_key='FLAG{base64_is_not_encryption}', title='🔐 Base64不是加密', description='Q29uZ3JhdHVsYXRpb25zISBZb3UgZm91bmQgaXQh', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{rot13_is_the_original_crypto}', title='🔄 ROT13 — 最原始的加密', description='SYNT{sbg13_vf_gur_bevtvany_pelcgb}', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{hex_is_everywhere}', title='🔢 十六进制解码', description='464c41477b6865785f69735f657665727977686572657d', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{morse_code_is_classic}', title='📡 摩尔斯电码', description='..-. .-.. .- --. -.--. -- --- .-. ... . ..--.- -.-. --- -.. . ..--.- .. ... ..--.- -.-. .-.. .- ... ... .. -.-. -.--.-', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{url_encoding_hides_things}', title='🔗 URL编码解码', description='%46%4C%41%47%7B%75%72%6C%5F%65%6E%63%6F%64%69%6E%67%5F%68%69%64%65%73%5F%74%68%69%6E%67%73%7D', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{binary_is_the_native_tongue}', title='0️⃣1️⃣ 二进制转换', description='01000110 01001100 01000001 01000111 01111011 01100010 01101001 01101110 01100001 01110010 01111001 01011111 01101001 01110011 01011111 01110100 01101000 01100101 01011111 01101110 01100001 01110100 01101001 01110110 01100101 01011111 01110100 01101111 01101110 01100111 01110101 01100101 01111101', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{hidden_in_plain_sight}', title='👁️ 隐藏的颜色', description='查看CSS中的注释或隐藏文字（color: transparent / font-size: 0）', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{http_methods_matter}', title='📮 HTTP方法大冒险', description='试试用 POST/DELETE/PUT/PATCH 访问 /api/v1/ctf/status', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{comment_out_the_truth}', title='💬 JS注释里的秘密', description='查看页面JavaScript源码，找 // 或 /* */ 注释', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{error_pages_tell_stories}', title='⚠️ 404页面也有料', description='访问一个不存在的页面，看404页面说了什么', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{backup_files_are_dangerous}', title='📦 备份文件泄露', description='访问 /backup.zip 或者 /backup.tar.gz', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{hidden_api_endpoints}', title='🗺️ API端点探测', description='访问 /docs 或 /openapi.json 看全部接口', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{jwt_tokens_are_not_magic}', title='🎫 JWT Token解析', description='抓取任意请求的 X-GP-Token，去 jwt.io 看看', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{referer_header_leaks}', title='↩️ Referer头的秘密', description='检查HTTP请求的 Referer 头', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{user_agent_can_lie}', title='🤖 User-Agent伪装', description="试试用 curl -A 'Googlebot' 访问网站", points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{ssti_smells_fishy}', title='🐟 SSTI探测', description='在URL参数中试试 {{7*7}}', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{directory_listing_forbidden}', title='📂 目录遍历尝试', description='访问 /uploads/ /static/ /assets/ /images/', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{xss_is_everywhere}', title='💉 XSS基础', description='在留言板输入 <script>alert(1)</script>', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{csrf_token_missing}', title='🛡️ CSRF Token缺失', description='检查POST请求是否缺乏CSRF保护', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{localstorage_is_not_safe}', title='💾 LocalStorage的秘密', description='F12→Application→Local Storage→yhymoney.asia', points=15, difficulty="easy"),
        DBCTFFlag(flag_key='FLAG{md5_is_broken_use_sha256}', title='🔓 MD5已被破解', description="md5('flag') = ? 研究一下哈希碰撞", points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{xor_with_single_byte}', title='🔮 单字节XOR解密', description='XOR encrypted: 2c0700170b1316591f131f561c0a1c0f561918131e031f570e', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{vigenere_is_classic_crypto}', title='📜 维吉尼亚密码', description="Vigenere with key 'RIN': WFNX{iphertb_fv_phnfprn_wnnqk}", points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{sql_injection_is_still_a_thing}', title='💉 SQL注入入门', description="在PIN输入框输入 ' OR '1'='1", points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{nosql_injection_exists_too}', title='🗄️ NoSQL注入', description='试试在请求中传入 $ne (not equal) 操作符', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{command_injection_backticks}', title='⌨️ 命令注入', description='试试在输入框输入 ; ls 或 `whoami`', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{idor_is_simple_but_deadly}', title='🆔 IDOR — 不安全的直接对象引用', description='试试修改API请求的ID参数：/api/v1/gp/process_request/1 → /2', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{rate_limiting_is_absent}', title='⏱️ 速率限制缺失', description='连续发送100次相同请求，看是否被限流', points=25, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{path_traversal_dot_dot_slash}', title='📁 路径穿越', description='试试 ../../etc/passwd 之类的payload', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{xxe_is_still_relevant}', title='📄 XXE — XML外部实体注入', description='提交XML数据试试外部实体引用', points=25, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{ssrf_is_the_sleeper_threat}', title='🌐 SSRF — 服务端请求伪造', description='试试让服务器访问内部地址 127.0.0.1', points=25, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{deserialization_is_dangerous}', title='🧩 反序列化攻击', description='Python pickle反序列化可以执行任意代码', points=25, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{jwt_none_algorithm_attack}', title='🎫 JWT None算法攻击', description='把JWT的alg改成none会怎样？', points=25, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{timing_attack_is_subtle}', title='⏳ 时序攻击基础', description='比较两个请求的响应时间差异', points=25, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{steganography_in_images}', title='🖼️ 图片隐写术', description='检查网站上的图片，看有没有藏东西', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{strings_command_is_powerful}', title='🔤 strings命令的力量', description='用 strings 命令检查二进制文件', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{metafile_data_leaks}', title='📸 元数据泄露', description='检查上传图片的EXIF数据', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{git_exposed_dot_git}', title='📂 .git泄露', description='访问 /.git/HEAD 或者 /.git/config', points=25, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{env_file_leaked}', title='🟢 .env文件泄露', description='访问 /.env 看环境变量', points=25, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{dockerfile_tells_the_stack}', title='🐳 Dockerfile泄露', description='访问 /Dockerfile 看部署配置', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{cors_misconfiguration}', title='🌍 CORS配置不当', description='检查CORS头是否过于宽松', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{clickjacking_missing_xframe}', title='🖼️ Clickjacking漏洞', description='检查是否缺少 X-Frame-Options 头', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{csp_is_not_configured}', title='🛡️ CSP未配置', description='检查 Content-Security-Policy 头是否存在', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{hsts_missing}', title='🔒 HSTS未启用', description='检查 Strict-Transport-Security 头', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{caesar_cipher_is_ancient}', title='🏛️ 凯撒密码', description='WKHQJ_BRFHVDU_BLSKHU_CL_DQFLHQW', points=20, difficulty="medium"),
        DBCTFFlag(flag_key='FLAG{aes_ecb_penguin}', title='🐧 AES ECB模式的企鹅', description='ECB模式加密同一明文产生同一密文—你能发现吗？', points=30, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{padding_oracle_is_classic}', title='🔮 Padding Oracle攻击', description='试试修改加密数据的padding', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{length_extension_attack}', title='📏 长度扩展攻击', description='SHA256(key+message)的可扩展性', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{rsa_wiener_attack}', title='🔑 RSA Wiener攻击', description='当d很小的时候，RSA可能被破解', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{bleichenbacher_oracle}', title='📨 Bleichenbacher Oracle', description='PKCS#1 v1.5 padding的RSA可能被攻破', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{buffer_overflow_in_the_wild}', title='💥 缓冲区溢出概念', description='理解栈溢出如何覆盖返回地址', points=30, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{format_string_is_powerful}', title='📝 格式化字符串攻击', description='%x %x %x %x 可以泄露栈信息', points=30, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{ret2libc_is_a_technique}', title='🔗 Return-to-libc攻击', description='绕过NX bit的技术', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{rop_chains_are_art}', title='⛓️ ROP链——二进制利用的艺术', description='Return-Oriented Programming', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{heap_exploitation_basics}', title='🗑️ 堆利用基础', description='Use-After-Free, Double-Free 等', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{race_condition_toctou}', title='🏃 TOCTOU竞态条件', description='Time-of-Check vs Time-of-Use', points=30, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{dns_rebinding_attack}', title='🌐 DNS Rebinding攻击', description='让浏览器攻击内网设备', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{prototype_pollution_in_js}', title='🧬 JS原型污染', description='__proto__ 和 constructor.prototype', points=30, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{oauth2_misconfiguration}', title='🔐 OAuth2配置错误', description='redirect_uri验证不严导致token泄露', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{saml_bypass_via_comment}', title='📋 SAML注入', description='SAML断言中的XML注释可以绕过验证', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{graphql_introspection_enabled}', title='🔍 GraphQL Introspection', description='GraphQL自省功能可能泄露Schema', points=30, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{http_request_smuggling}', title='🚛 HTTP请求走私', description='利用Content-Length和Transfer-Encoding的不一致', points=35, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{websocket_hijacking}', title='🔌 WebSocket劫持', description='缺少origin检查的WebSocket连接', points=30, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{subdomain_takeover_potential}', title='🌍 子域名接管', description='查找DNS dangling记录', points=30, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{shodan_is_your_eye}', title='🔭 Shodan搜索引擎', description='用Shodan扫描你的服务器暴露了什么', points=30, difficulty="hard"),
        DBCTFFlag(flag_key='FLAG{zero_day_is_a_mindset}', title='💎 零日漏洞思维', description='理解漏洞发现的方法论', points=40, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{fuzzing_finds_bugs}', title='🎯 Fuzzing测试', description='用AFL/libFuzzer对程序进行模糊测试', points=40, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{symbolic_execution_is_magic}', title='🔮 符号执行', description='用angr解题的技巧', points=45, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{return_oriented_shellcode}', title='💣 ROP到Shellcode', description='完整的ROP链构建', points=45, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{kernel_exploitation_101}', title='🐧 内核漏洞利用入门', description='理解内核态vs用户态', points=45, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{side_channel_is_stealthy}', title='👻 侧信道攻击', description='通过功耗/电磁/时间泄露信息', points=45, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{cache_timing_is_real}', title='⚡ 缓存时序攻击', description='Spectre和Meltdown的原理', points=45, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{quantum_crypto_is_coming}', title='🔬 后量子密码学', description='Shor算法和格密码', points=45, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{blockchain_smart_contract_bugs}', title='⛓️ 智能合约漏洞', description='Reentrancy, Integer Overflow, Flash Loans', points=40, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{reverse_engineering_is_an_art}', title='🔧 逆向工程的艺术', description='用Ghidra/IDA分析二进制文件', points=40, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{code_audit_is_essential}', title='📖 代码审计方法论', description='学会系统地阅读代码找漏洞', points=40, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{threat_modeling_is_proactive}', title='🗺️ 威胁建模', description='STRIDE模型和攻击树', points=40, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{red_team_is_the_ultimate_test}', title='🔴 红队攻击模拟', description='完整的渗透测试方法论', points=45, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{pwn_college_is_a_thing}', title='🎓 Pwn College', description='pwn.college 是一个超棒的学习平台', points=40, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{hackthebox_is_your_playground}', title='📦 HackTheBox', description='HTB是最好的实战训练平台之一', points=40, difficulty="expert"),
        DBCTFFlag(flag_key='FLAG{you_are_a_real_hacker_now}', title='🏆 真·白客认证', description='集齐90个flag！你已经掌握了Web渗透的全套技能', points=50, difficulty="legendary"),
        DBCTFFlag(flag_key='FLAG{the_42nd_challenge}', title='🐬 终极答案', description='在页面上输入某个著名的数字...', points=50, difficulty="legendary"),
        DBCTFFlag(flag_key='FLAG{full_chain_exploitation}', title='⛓️ 全链条利用', description='从信息收集→漏洞发现→利用→提权→持久化', points=50, difficulty="legendary"),
        DBCTFFlag(flag_key='FLAG{responsible_disclosure_is_key}', title='🤝 负责任的漏洞披露', description='发现漏洞后该怎么做', points=50, difficulty="legendary"),
        DBCTFFlag(flag_key='FLAG{every_expert_was_once_a_beginner}', title='🌱 不忘初心', description='即使是最厉害的黑客，也曾是个小白', points=50, difficulty="legendary"),
        DBCTFFlag(flag_key='FLAG{sharing_knowledge_is_the_way}', title='📚 知识分享', description='把你的CTF解题过程写成writeup', points=50, difficulty="legendary"),
        DBCTFFlag(flag_key='FLAG{white_hat_is_a_lifestyle}', title='🎩 白客是一种生活方式', description='用你的技能让互联网变得更安全', points=50, difficulty="legendary"),
        DBCTFFlag(flag_key='FLAG{bug_bounty_is_waiting}', title='💰 Bug Bounty在等你', description='HackerOne, Bugcrowd等平台', points=50, difficulty="legendary"),
        DBCTFFlag(flag_key='FLAG{the_learning_never_stops}', title='📖 学无止境', description='安全领域每天都有新东西', points=50, difficulty="legendary"),
        DBCTFFlag(flag_key='FLAG{the_final_boss_defeated}', title='👑 最终BOSS — 击败！', description='100/100！你已经完成了全部CTF挑战', points=50, difficulty="legendary"),
    ]
    for f in flags: db.add(f)
    db.commit()
    hints = [
        DBCTFHint(flag_key='FLAG{welcome_to_ctf}', hint_text='The journey begins here.', hint_order=1),
        DBCTFHint(flag_key='FLAG{welcome_to_ctf}', hint_text='访问 /ctf 页面', hint_order=2),
        DBCTFHint(flag_key='FLAG{view_source_is_step_one}', hint_text='Right-click anywhere on the page.', hint_order=1),
        DBCTFHint(flag_key='FLAG{view_source_is_step_one}', hint_text='右键→查看网页源代码', hint_order=2),
        DBCTFHint(flag_key='FLAG{http_headers_tell_all}', hint_text='Every HTTP response carries metadata.', hint_order=1),
        DBCTFHint(flag_key='FLAG{http_headers_tell_all}', hint_text='F12→Network→刷新→点第一个请求', hint_order=2),
        DBCTFHint(flag_key='FLAG{robots_are_not_your_enemy}', hint_text='robots.txt tells crawlers what to avoid.', hint_order=1),
        DBCTFHint(flag_key='FLAG{robots_are_not_your_enemy}', hint_text='访问 /robots.txt', hint_order=2),
        DBCTFHint(flag_key='FLAG{source_code_is_your_friend}', hint_text='View source and look for <!-- comments -->.', hint_order=1),
        DBCTFHint(flag_key='FLAG{source_code_is_your_friend}', hint_text="右键查看源码→搜索'FLAG'", hint_order=2),
        DBCTFHint(flag_key='FLAG{console_is_your_best_friend}', hint_text='The console.log() function is your friend.', hint_order=1),
        DBCTFHint(flag_key='FLAG{console_is_your_best_friend}', hint_text='F12→Console标签', hint_order=2),
        DBCTFHint(flag_key='FLAG{cookies_are_delicious}', hint_text='Cookies store data sent by the server.', hint_order=1),
        DBCTFHint(flag_key='FLAG{cookies_are_delicious}', hint_text='F12→Application→Cookies', hint_order=2),
        DBCTFHint(flag_key='FLAG{meta_tags_hide_secrets}', hint_text='Check the <head> section of the HTML.', hint_order=1),
        DBCTFHint(flag_key='FLAG{meta_tags_hide_secrets}', hint_text="查看网页源码→搜索'meta'", hint_order=2),
        DBCTFHint(flag_key='FLAG{f12_is_your_gateway}', hint_text='Press F12 on your keyboard.', hint_order=1),
        DBCTFHint(flag_key='FLAG{f12_is_your_gateway}', hint_text='按F12键', hint_order=2),
        DBCTFHint(flag_key='FLAG{every_journey_begins_with_curiosity}', hint_text="You've completed the tutorial!", hint_order=1),
        DBCTFHint(flag_key='FLAG{every_journey_begins_with_curiosity}', hint_text='恭喜完成入门！下一关开始真正的挑战', hint_order=2),
        DBCTFHint(flag_key='FLAG{base64_is_not_encryption}', hint_text='What encoding ends with = or == ?', hint_order=1),
        DBCTFHint(flag_key='FLAG{base64_is_not_encryption}', hint_text="echo 'Q29uZ...' | base64 -d", hint_order=2),
        DBCTFHint(flag_key='FLAG{rot13_is_the_original_crypto}', hint_text='Rotate each letter by 13 positions.', hint_order=1),
        DBCTFHint(flag_key='FLAG{rot13_is_the_original_crypto}', hint_text="www.rot13.com 或 tr 'A-Za-z' 'N-ZA-Mn-za-m'", hint_order=2),
        DBCTFHint(flag_key='FLAG{hex_is_everywhere}', hint_text='Each 2 characters = 1 byte in hex.', hint_order=1),
        DBCTFHint(flag_key='FLAG{hex_is_everywhere}', hint_text="echo '464c...' | xxd -r -p", hint_order=2),
        DBCTFHint(flag_key='FLAG{morse_code_is_classic}', hint_text='.- is A, -... is B, etc.', hint_order=1),
        DBCTFHint(flag_key='FLAG{morse_code_is_classic}', hint_text="搜索'morse code decoder'", hint_order=2),
        DBCTFHint(flag_key='FLAG{url_encoding_hides_things}', hint_text='%XX is URL-encoded hex.', hint_order=1),
        DBCTFHint(flag_key='FLAG{url_encoding_hides_things}', hint_text='decodeURIComponent() 或在线URL解码', hint_order=2),
        DBCTFHint(flag_key='FLAG{binary_is_the_native_tongue}', hint_text='8 bits = 1 ASCII character.', hint_order=1),
        DBCTFHint(flag_key='FLAG{binary_is_the_native_tongue}', hint_text="搜索'binary to text converter'", hint_order=2),
        DBCTFHint(flag_key='FLAG{hidden_in_plain_sight}', hint_text='Look for CSS that hides text visually.', hint_order=1),
        DBCTFHint(flag_key='FLAG{hidden_in_plain_sight}', hint_text="F12→Elements→搜索'hidden'或'color:'", hint_order=2),
        DBCTFHint(flag_key='FLAG{http_methods_matter}', hint_text="GET isn't the only HTTP method.", hint_order=1),
        DBCTFHint(flag_key='FLAG{http_methods_matter}', hint_text='curl -X POST https://yhymoney.asia/api/v1/ctf/status', hint_order=2),
        DBCTFHint(flag_key='FLAG{comment_out_the_truth}', hint_text='Check the JavaScript source for comments.', hint_order=1),
        DBCTFHint(flag_key='FLAG{comment_out_the_truth}', hint_text='查看页面JS文件中的注释', hint_order=2),
        DBCTFHint(flag_key='FLAG{error_pages_tell_stories}', hint_text="Try accessing a page that doesn't exist.", hint_order=1),
        DBCTFHint(flag_key='FLAG{error_pages_tell_stories}', hint_text='yhymoney.asia/nonexistent', hint_order=2),
        DBCTFHint(flag_key='FLAG{backup_files_are_dangerous}', hint_text='Developers often leave backup files.', hint_order=1),
        DBCTFHint(flag_key='FLAG{backup_files_are_dangerous}', hint_text='试试 /backup.zip /backup.tar.gz /backup.old', hint_order=2),
        DBCTFHint(flag_key='FLAG{hidden_api_endpoints}', hint_text='FastAPI auto-generates API documentation.', hint_order=1),
        DBCTFHint(flag_key='FLAG{hidden_api_endpoints}', hint_text='访问 /docs 或 /openapi.json', hint_order=2),
        DBCTFHint(flag_key='FLAG{jwt_tokens_are_not_magic}', hint_text='JWT has 3 parts separated by dots.', hint_order=1),
        DBCTFHint(flag_key='FLAG{jwt_tokens_are_not_magic}', hint_text='F12→Network→看请求头→复制token→jwt.io', hint_order=2),
        DBCTFHint(flag_key='FLAG{referer_header_leaks}', hint_text='The Referer header tells where you came from.', hint_order=1),
        DBCTFHint(flag_key='FLAG{referer_header_leaks}', hint_text='F12→Network→Request Headers→Referer', hint_order=2),
        DBCTFHint(flag_key='FLAG{user_agent_can_lie}', hint_text='You can pretend to be any browser.', hint_order=1),
        DBCTFHint(flag_key='FLAG{user_agent_can_lie}', hint_text="curl -A 'Googlebot' https://yhymoney.asia/", hint_order=2),
        DBCTFHint(flag_key='FLAG{ssti_smells_fishy}', hint_text='Server-Side Template Injection leaves patterns.', hint_order=1),
        DBCTFHint(flag_key='FLAG{ssti_smells_fishy}', hint_text='/api/v1/fun/list?test={{7*7}}', hint_order=2),
        DBCTFHint(flag_key='FLAG{directory_listing_forbidden}', hint_text='Some directories might list their contents.', hint_order=1),
        DBCTFHint(flag_key='FLAG{directory_listing_forbidden}', hint_text='试试各种常见目录路径', hint_order=2),
        DBCTFHint(flag_key='FLAG{xss_is_everywhere}', hint_text='Cross-Site Scripting — injected JavaScript.', hint_order=1),
        DBCTFHint(flag_key='FLAG{xss_is_everywhere}', hint_text='留言板输入框测试特殊字符', hint_order=2),
        DBCTFHint(flag_key='FLAG{csrf_token_missing}', hint_text='Cross-Site Request Forgery needs tokens.', hint_order=1),
        DBCTFHint(flag_key='FLAG{csrf_token_missing}', hint_text='检查POST请求的form data', hint_order=2),
        DBCTFHint(flag_key='FLAG{localstorage_is_not_safe}', hint_text='localStorage stores data in your browser.', hint_order=1),
        DBCTFHint(flag_key='FLAG{localstorage_is_not_safe}', hint_text='F12→Application→Local Storage', hint_order=2),
        DBCTFHint(flag_key='FLAG{md5_is_broken_use_sha256}', hint_text='MD5 has known collisions.', hint_order=1),
        DBCTFHint(flag_key='FLAG{md5_is_broken_use_sha256}', hint_text="echo -n 'flag' | md5sum", hint_order=2),
        DBCTFHint(flag_key='FLAG{xor_with_single_byte}', hint_text='Try XOR with a single byte key.', hint_order=1),
        DBCTFHint(flag_key='FLAG{xor_with_single_byte}', hint_text="搜索'single-byte XOR decoder'", hint_order=2),
        DBCTFHint(flag_key='FLAG{vigenere_is_classic_crypto}', hint_text='Vigenère cipher uses a repeating keyword.', hint_order=1),
        DBCTFHint(flag_key='FLAG{vigenere_is_classic_crypto}', hint_text="搜索'Vigenère cipher decoder'", hint_order=2),
        DBCTFHint(flag_key='FLAG{sql_injection_is_still_a_thing}', hint_text='SQL injection tricks the database.', hint_order=1),
        DBCTFHint(flag_key='FLAG{sql_injection_is_still_a_thing}', hint_text="在LP PIN验证框输入 ' OR '1'='1", hint_order=2),
        DBCTFHint(flag_key='FLAG{nosql_injection_exists_too}', hint_text='NoSQL databases have their own injection.', hint_order=1),
        DBCTFHint(flag_key='FLAG{nosql_injection_exists_too}', hint_text="搜索'NoSQL injection $ne'", hint_order=2),
        DBCTFHint(flag_key='FLAG{command_injection_backticks}', hint_text='Shell command injection via unsanitized input.', hint_order=1),
        DBCTFHint(flag_key='FLAG{command_injection_backticks}', hint_text="搜索'command injection payloads'", hint_order=2),
        DBCTFHint(flag_key='FLAG{idor_is_simple_but_deadly}', hint_text='Insecure Direct Object Reference.', hint_order=1),
        DBCTFHint(flag_key='FLAG{idor_is_simple_but_deadly}', hint_text='修改URL中的数字ID', hint_order=2),
        DBCTFHint(flag_key='FLAG{rate_limiting_is_absent}', hint_text='Without rate limiting, brute force is easy.', hint_order=1),
        DBCTFHint(flag_key='FLAG{rate_limiting_is_absent}', hint_text='写个循环发请求', hint_order=2),
        DBCTFHint(flag_key='FLAG{path_traversal_dot_dot_slash}', hint_text='../ can escape the intended directory.', hint_order=1),
        DBCTFHint(flag_key='FLAG{path_traversal_dot_dot_slash}', hint_text='在URL或参数中尝试 ../../../', hint_order=2),
        DBCTFHint(flag_key='FLAG{xxe_is_still_relevant}', hint_text='XML parsers can be tricked.', hint_order=1),
        DBCTFHint(flag_key='FLAG{xxe_is_still_relevant}', hint_text="搜索'XXE payload'", hint_order=2),
        DBCTFHint(flag_key='FLAG{ssrf_is_the_sleeper_threat}', hint_text='Server-Side Request Forgery.', hint_order=1),
        DBCTFHint(flag_key='FLAG{ssrf_is_the_sleeper_threat}', hint_text='在URL参数中传入 http://127.0.0.1:8000', hint_order=2),
        DBCTFHint(flag_key='FLAG{deserialization_is_dangerous}', hint_text='Unsafe deserialization = RCE.', hint_order=1),
        DBCTFHint(flag_key='FLAG{deserialization_is_dangerous}', hint_text="搜索'Python pickle RCE'", hint_order=2),
        DBCTFHint(flag_key='FLAG{jwt_none_algorithm_attack}', hint_text='Some JWT libraries accept alg:none.', hint_order=1),
        DBCTFHint(flag_key='FLAG{jwt_none_algorithm_attack}', hint_text='jwt.io → 改header→ {\"alg\":\"none\"}', hint_order=2),
        DBCTFHint(flag_key='FLAG{timing_attack_is_subtle}', hint_text='Response time can leak information.', hint_order=1),
        DBCTFHint(flag_key='FLAG{timing_attack_is_subtle}', hint_text='测量不同输入的响应时间', hint_order=2),
        DBCTFHint(flag_key='FLAG{steganography_in_images}', hint_text='Images can hide data.', hint_order=1),
        DBCTFHint(flag_key='FLAG{steganography_in_images}', hint_text='下载图片→用 steghide 或 strings 检查', hint_order=2),
        DBCTFHint(flag_key='FLAG{strings_command_is_powerful}', hint_text='strings extracts readable text from binaries.', hint_order=1),
        DBCTFHint(flag_key='FLAG{strings_command_is_powerful}', hint_text='strings filename | grep FLAG', hint_order=2),
        DBCTFHint(flag_key='FLAG{metafile_data_leaks}', hint_text='Photos carry GPS, camera, and timestamp data.', hint_order=1),
        DBCTFHint(flag_key='FLAG{metafile_data_leaks}', hint_text='exiftool image.jpg', hint_order=2),
        DBCTFHint(flag_key='FLAG{git_exposed_dot_git}', hint_text='Exposed .git directories leak source code.', hint_order=1),
        DBCTFHint(flag_key='FLAG{git_exposed_dot_git}', hint_text='访问 /.git/config', hint_order=2),
        DBCTFHint(flag_key='FLAG{env_file_leaked}', hint_text='.env files contain secrets.', hint_order=1),
        DBCTFHint(flag_key='FLAG{env_file_leaked}', hint_text='访问 /.env', hint_order=2),
        DBCTFHint(flag_key='FLAG{dockerfile_tells_the_stack}', hint_text='Dockerfiles reveal the infrastructure.', hint_order=1),
        DBCTFHint(flag_key='FLAG{dockerfile_tells_the_stack}', hint_text='访问 /Dockerfile', hint_order=2),
        DBCTFHint(flag_key='FLAG{cors_misconfiguration}', hint_text='CORS: Access-Control-Allow-Origin: * is dangerous.', hint_order=1),
        DBCTFHint(flag_key='FLAG{cors_misconfiguration}', hint_text='F12→检查响应头 Access-Control-*', hint_order=2),
        DBCTFHint(flag_key='FLAG{clickjacking_missing_xframe}', hint_text='Without X-Frame-Options, site can be iframed.', hint_order=1),
        DBCTFHint(flag_key='FLAG{clickjacking_missing_xframe}', hint_text='检查响应头是否有 X-Frame-Options', hint_order=2),
        DBCTFHint(flag_key='FLAG{csp_is_not_configured}', hint_text='Content-Security-Policy prevents XSS.', hint_order=1),
        DBCTFHint(flag_key='FLAG{csp_is_not_configured}', hint_text='检查响应头 CSP', hint_order=2),
        DBCTFHint(flag_key='FLAG{hsts_missing}', hint_text='HSTS forces HTTPS.', hint_order=1),
        DBCTFHint(flag_key='FLAG{hsts_missing}', hint_text='检查响应头 Strict-Transport-Security', hint_order=2),
        DBCTFHint(flag_key='FLAG{caesar_cipher_is_ancient}', hint_text='Shift each letter by a fixed amount.', hint_order=1),
        DBCTFHint(flag_key='FLAG{caesar_cipher_is_ancient}', hint_text="搜索'Caesar cipher decoder'", hint_order=2),
        DBCTFHint(flag_key='FLAG{aes_ecb_penguin}', hint_text='ECB mode leaks patterns.', hint_order=1),
        DBCTFHint(flag_key='FLAG{aes_ecb_penguin}', hint_text='研究 AES ECB vs CBC 模式', hint_order=2),
        DBCTFHint(flag_key='FLAG{padding_oracle_is_classic}', hint_text='Padding Oracle lets you decrypt without the key.', hint_order=1),
        DBCTFHint(flag_key='FLAG{padding_oracle_is_classic}', hint_text="搜索'Padding Oracle attack explained'", hint_order=2),
        DBCTFHint(flag_key='FLAG{length_extension_attack}', hint_text='Merkle-Damgard hash construction has this flaw.', hint_order=1),
        DBCTFHint(flag_key='FLAG{length_extension_attack}', hint_text="搜索'hash length extension attack'", hint_order=2),
        DBCTFHint(flag_key='FLAG{rsa_wiener_attack}', hint_text='Small private exponent d = vulnerable.', hint_order=1),
        DBCTFHint(flag_key='FLAG{rsa_wiener_attack}', hint_text="搜索'RSA Wiener attack'", hint_order=2),
        DBCTFHint(flag_key='FLAG{bleichenbacher_oracle}', hint_text='The million message attack.', hint_order=1),
        DBCTFHint(flag_key='FLAG{bleichenbacher_oracle}', hint_text="搜索'Bleichenbacher attack'", hint_order=2),
        DBCTFHint(flag_key='FLAG{buffer_overflow_in_the_wild}', hint_text='Overflow the buffer → control execution flow.', hint_order=1),
        DBCTFHint(flag_key='FLAG{buffer_overflow_in_the_wild}', hint_text="搜索'buffer overflow for beginners'", hint_order=2),
        DBCTFHint(flag_key='FLAG{format_string_is_powerful}', hint_text='printf without format specifier is dangerous.', hint_order=1),
        DBCTFHint(flag_key='FLAG{format_string_is_powerful}', hint_text="搜索'format string vulnerability'", hint_order=2),
        DBCTFHint(flag_key='FLAG{ret2libc_is_a_technique}', hint_text="When you can't execute shellcode, use existing code.", hint_order=1),
        DBCTFHint(flag_key='FLAG{ret2libc_is_a_technique}', hint_text="搜索'ret2libc attack'", hint_order=2),
        DBCTFHint(flag_key='FLAG{rop_chains_are_art}', hint_text='Chain gadgets together to execute arbitrary code.', hint_order=1),
        DBCTFHint(flag_key='FLAG{rop_chains_are_art}', hint_text="搜索'ROP chain tutorial'", hint_order=2),
        DBCTFHint(flag_key='FLAG{heap_exploitation_basics}', hint_text='Heap bugs are harder but more rewarding.', hint_order=1),
        DBCTFHint(flag_key='FLAG{heap_exploitation_basics}', hint_text="搜索'heap exploitation basics'", hint_order=2),
        DBCTFHint(flag_key='FLAG{race_condition_toctou}', hint_text='Between check and use, things can change.', hint_order=1),
        DBCTFHint(flag_key='FLAG{race_condition_toctou}', hint_text="搜索'TOCTOU race condition'", hint_order=2),
        DBCTFHint(flag_key='FLAG{dns_rebinding_attack}', hint_text='DNS rebinding bypasses same-origin policy.', hint_order=1),
        DBCTFHint(flag_key='FLAG{dns_rebinding_attack}', hint_text="搜索'DNS rebinding attack'", hint_order=2),
        DBCTFHint(flag_key='FLAG{prototype_pollution_in_js}', hint_text='JavaScript objects inherit from prototypes.', hint_order=1),
        DBCTFHint(flag_key='FLAG{prototype_pollution_in_js}', hint_text="搜索'prototype pollution'", hint_order=2),
        DBCTFHint(flag_key='FLAG{oauth2_misconfiguration}', hint_text='OAuth flow has many edge cases.', hint_order=1),
        DBCTFHint(flag_key='FLAG{oauth2_misconfiguration}', hint_text="搜索'OAuth2 redirect_uri bypass'", hint_order=2),
        DBCTFHint(flag_key='FLAG{saml_bypass_via_comment}', hint_text='SAML relies on XML — which has comments.', hint_order=1),
        DBCTFHint(flag_key='FLAG{saml_bypass_via_comment}', hint_text="搜索'SAML XML comment injection'", hint_order=2),
        DBCTFHint(flag_key='FLAG{graphql_introspection_enabled}', hint_text='Introspection reveals the entire API schema.', hint_order=1),
        DBCTFHint(flag_key='FLAG{graphql_introspection_enabled}', hint_text="搜索'GraphQL introspection attack'", hint_order=2),
        DBCTFHint(flag_key='FLAG{http_request_smuggling}', hint_text='Frontend and backend parse requests differently.', hint_order=1),
        DBCTFHint(flag_key='FLAG{http_request_smuggling}', hint_text="搜索'HTTP request smuggling'", hint_order=2),
        DBCTFHint(flag_key='FLAG{websocket_hijacking}', hint_text='WebSocket without origin check = hijackable.', hint_order=1),
        DBCTFHint(flag_key='FLAG{websocket_hijacking}', hint_text='检查WebSocket连接的Origin头', hint_order=2),
        DBCTFHint(flag_key='FLAG{subdomain_takeover_potential}', hint_text='Dead DNS records point to services you can claim.', hint_order=1),
        DBCTFHint(flag_key='FLAG{subdomain_takeover_potential}', hint_text="搜索'subdomain takeover'", hint_order=2),
        DBCTFHint(flag_key='FLAG{shodan_is_your_eye}', hint_text='Shodan indexes internet-connected devices.', hint_order=1),
        DBCTFHint(flag_key='FLAG{shodan_is_your_eye}', hint_text='shodan.io 搜索你的IP', hint_order=2),
        DBCTFHint(flag_key='FLAG{zero_day_is_a_mindset}', hint_text='A zero-day is just a bug nobody found yet.', hint_order=1),
        DBCTFHint(flag_key='FLAG{zero_day_is_a_mindset}', hint_text='阅读CVE数据库和PoC代码', hint_order=2),
        DBCTFHint(flag_key='FLAG{fuzzing_finds_bugs}', hint_text='Random input → unexpected behavior → bugs.', hint_order=1),
        DBCTFHint(flag_key='FLAG{fuzzing_finds_bugs}', hint_text="搜索'fuzzing with AFL tutorial'", hint_order=2),
        DBCTFHint(flag_key='FLAG{symbolic_execution_is_magic}', hint_text='Symbolic execution solves constraints automatically.', hint_order=1),
        DBCTFHint(flag_key='FLAG{symbolic_execution_is_magic}', hint_text="搜索'angr CTF tutorial'", hint_order=2),
        DBCTFHint(flag_key='FLAG{return_oriented_shellcode}', hint_text='Build a chain: ROP → mprotect → shellcode.', hint_order=1),
        DBCTFHint(flag_key='FLAG{return_oriented_shellcode}', hint_text="搜索'ROP to shellcode chain'", hint_order=2),
        DBCTFHint(flag_key='FLAG{kernel_exploitation_101}', hint_text='Kernel bugs = full system control.', hint_order=1),
        DBCTFHint(flag_key='FLAG{kernel_exploitation_101}', hint_text="搜索'kernel exploitation basics'", hint_order=2),
        DBCTFHint(flag_key='FLAG{side_channel_is_stealthy}', hint_text='The computer itself leaks secrets.', hint_order=1),
        DBCTFHint(flag_key='FLAG{side_channel_is_stealthy}', hint_text="搜索'side-channel attack explained'", hint_order=2),
        DBCTFHint(flag_key='FLAG{cache_timing_is_real}', hint_text='CPU cache timing can leak memory content.', hint_order=1),
        DBCTFHint(flag_key='FLAG{cache_timing_is_real}', hint_text="搜索'Meltdown and Spectre explained'", hint_order=2),
        DBCTFHint(flag_key='FLAG{quantum_crypto_is_coming}', hint_text='Quantum computers will break RSA and ECC.', hint_order=1),
        DBCTFHint(flag_key='FLAG{quantum_crypto_is_coming}', hint_text="搜索'shor algorithm and post-quantum'", hint_order=2),
        DBCTFHint(flag_key='FLAG{blockchain_smart_contract_bugs}', hint_text='Smart contract bugs = free money for hackers.', hint_order=1),
        DBCTFHint(flag_key='FLAG{blockchain_smart_contract_bugs}', hint_text="搜索'reentrancy attack ethereum'", hint_order=2),
        DBCTFHint(flag_key='FLAG{reverse_engineering_is_an_art}', hint_text='Reverse engineering reveals how programs work.', hint_order=1),
        DBCTFHint(flag_key='FLAG{reverse_engineering_is_an_art}', hint_text='下载Ghidra，分析一个简单程序', hint_order=2),
        DBCTFHint(flag_key='FLAG{code_audit_is_essential}', hint_text='Manual code review finds what tools miss.', hint_order=1),
        DBCTFHint(flag_key='FLAG{code_audit_is_essential}', hint_text='学习OWASP Code Review Guide', hint_order=2),
        DBCTFHint(flag_key='FLAG{threat_modeling_is_proactive}', hint_text='Think like an attacker before you code.', hint_order=1),
        DBCTFHint(flag_key='FLAG{threat_modeling_is_proactive}', hint_text="搜索'STRIDE threat modeling'", hint_order=2),
        DBCTFHint(flag_key='FLAG{red_team_is_the_ultimate_test}', hint_text='Red team = full-scope adversarial simulation.', hint_order=1),
        DBCTFHint(flag_key='FLAG{red_team_is_the_ultimate_test}', hint_text="搜索'red team operations guide'", hint_order=2),
        DBCTFHint(flag_key='FLAG{pwn_college_is_a_thing}', hint_text='Free binary exploitation education.', hint_order=1),
        DBCTFHint(flag_key='FLAG{pwn_college_is_a_thing}', hint_text='访问 pwn.college', hint_order=2),
        DBCTFHint(flag_key='FLAG{hackthebox_is_your_playground}', hint_text='Real machines, real challenges.', hint_order=1),
        DBCTFHint(flag_key='FLAG{hackthebox_is_your_playground}', hint_text='访问 hackthebox.com', hint_order=2),
        DBCTFHint(flag_key='FLAG{you_are_a_real_hacker_now}', hint_text='This is the ultimate achievement.', hint_order=1),
        DBCTFHint(flag_key='FLAG{you_are_a_real_hacker_now}', hint_text='集齐前90个flag', hint_order=2),
        DBCTFHint(flag_key='FLAG{the_42nd_challenge}', hint_text='The answer to life, the universe, and everything.', hint_order=1),
        DBCTFHint(flag_key='FLAG{the_42nd_challenge}', hint_text='键盘输入 4 然后 2', hint_order=2),
        DBCTFHint(flag_key='FLAG{full_chain_exploitation}', hint_text='The complete attack lifecycle.', hint_order=1),
        DBCTFHint(flag_key='FLAG{full_chain_exploitation}', hint_text='研究Cyber Kill Chain模型', hint_order=2),
        DBCTFHint(flag_key='FLAG{responsible_disclosure_is_key}', hint_text='With great power comes great responsibility.', hint_order=1),
        DBCTFHint(flag_key='FLAG{responsible_disclosure_is_key}', hint_text="搜索'responsible disclosure policy'", hint_order=2),
        DBCTFHint(flag_key='FLAG{every_expert_was_once_a_beginner}', hint_text='Remember where you started.', hint_order=1),
        DBCTFHint(flag_key='FLAG{every_expert_was_once_a_beginner}', hint_text='CTF的旅途，从第一道题开始', hint_order=2),
        DBCTFHint(flag_key='FLAG{sharing_knowledge_is_the_way}', hint_text='Teaching others deepens your understanding.', hint_order=1),
        DBCTFHint(flag_key='FLAG{sharing_knowledge_is_the_way}', hint_text='写一篇CTF writeup并发布', hint_order=2),
        DBCTFHint(flag_key='FLAG{white_hat_is_a_lifestyle}', hint_text="Security is not a product, it's a process.", hint_order=1),
        DBCTFHint(flag_key='FLAG{white_hat_is_a_lifestyle}', hint_text='参与Bug Bounty或安全社区', hint_order=2),
        DBCTFHint(flag_key='FLAG{bug_bounty_is_waiting}', hint_text='Companies will pay you to find bugs.', hint_order=1),
        DBCTFHint(flag_key='FLAG{bug_bounty_is_waiting}', hint_text='访问 hackerone.com', hint_order=2),
        DBCTFHint(flag_key='FLAG{the_learning_never_stops}', hint_text='Technology evolves, so should you.', hint_order=1),
        DBCTFHint(flag_key='FLAG{the_learning_never_stops}', hint_text='订阅安全博客和CVE feeds', hint_order=2),
        DBCTFHint(flag_key='FLAG{the_final_boss_defeated}', hint_text='CONGRATULATIONS! You are a TRUE White Hat!', hint_order=1),
        DBCTFHint(flag_key='FLAG{the_final_boss_defeated}', hint_text='全部100题完成！你是真正的白客！', hint_order=2),
    ]
    for h in hints: db.add(h)
    db.commit()


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    return Response(content="""User-agent: *
Disallow: /admin
Disallow: /secret-panel
Disallow: /hidden-api
Disallow: /backup.zip
Allow: /

# FLAG{robots_are_not_your_enemy}
# 恭喜你找到了第一个flag！去渗透挑战面板提交吧！
# 提示：下一个flag藏在网页源代码里 👀
""", media_type="text/plain")

# 伪造的"遗忘后台"
from fastapi.responses import PlainTextResponse

@app.get("/secret-panel", include_in_schema=False)
def secret_panel():
    return HTMLResponse(content="""<!DOCTYPE html><html><head><title>内部管理系统</title><style>body{background:#000;color:#0f0;font-family:monospace;padding:40px;text-align:center}h1{color:#f00}.hidden{color:#000}.hidden:hover{color:#0f0}</style></head><body><h1>⚠️ 警告：越权访问！</h1><p>你的IP已被记录：""" + _random.choice(["192.168.1.1","10.0.0.1","172.16.0.1"]) + """</p><p>系统已触发警报 🚨</p><br><p class="hidden">开玩笑的 😂 这是给你弟弟的白客训练场~</p><p class="hidden">试试访问 /hidden-api?token=guest</p></body></html>""")

@app.get("/hidden-api", include_in_schema=False)
def hidden_api(token: str = None):
    if token == "guest":
        return {"status": "access granted", "message": "欢迎初级白客", "flag": "FLAG{robots_are_not_your_enemy}", "next_hint": "检查网页源码中的HTML注释"}
    return {"status": "denied", "message": "需要 token 参数", "hint": "试试 ?token=guest"}

# 🕵️ 隐藏的CTF挑战页面
@app.get("/ctf", include_in_schema=False)
def ctf_challenge_page():
    return HTMLResponse(content="""<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"UTF-8\"><title>CTF挑战入口</title>
<style>body{background:#0a0e27;color:#0f0;font-family:monospace;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{text-align:center;border:1px solid #0f0;padding:40px;border-radius:8px;max-width:600px}
h1{color:#ff0}h2{color:#f0f}.hint{color:#666;margin-top:20px;font-size:12px}
a{color:#0ff}</style></head><body><div class=\"box\">
<h1>🕵️ CTF 挑战入口</h1><p>恭喜你找到了隐藏的挑战页面！</p>
<p>Flag格式: <code>FLAG{...}</code></p>
<div class=\"hint\">
<p>📌 第1题: 检查 robots.txt → <a href=\"/robots.txt\">/robots.txt</a></p>
<p>📌 第2题: 查看此页面源代码 → 右键 → 查看源代码</p>
<p>📌 第3题: HTTP响应头 → F12 Network</p>
<p>📌 第4题: 检查Cookie → F12 Application</p>
<p>📌 第5题: 访问 <a href=\"/hidden-api?token=guest\">/hidden-api?token=guest</a></p>
<p>📌 第6题: 访问 <a href=\"/secret-panel\">/secret-panel</a> (假的警告)</p>
<p>📌 第7题: 访问 <a href=\"/backup.zip\">/backup.zip</a></p>
<!-- FLAG{source_code_is_your_friend} ← 你看，flag就在源码里！ -->
</div></div></body></html>""")

# 🏆 CTF 排行榜
@app.get("/api/v1/ctf/leaderboard", include_in_schema=False)
def ctf_leaderboard(db: Session = Depends(get_db)):
    flags = db.query(DBCTFFlag).filter(DBCTFFlag.found_by.isnot(None)).all()
    return {"players": [{"name": f.found_by, "title": f.title, "points": f.points, "found_at": f.found_at.strftime("%m/%d %H:%M") if f.found_at else ""} for f in flags]}
    flags = db.query(DBCTFFlag).filter(DBCTFFlag.found_by.isnot(None)).all()
    return {"players": [{"name": f.found_by, "title": f.title, "points": f.points, "found_at": f.found_at.strftime("%m/%d %H:%M") if f.found_at else ""} for f in flags]}

@app.get("/backup.zip", include_in_schema=False)
def fake_backup():
    return Response(content="PK\x03\x04\n这不是真的ZIP文件，但是你在正确的方向上！\nFLAG{robots_are_not_your_enemy}\n下一个flag在响应头里", media_type="application/zip")

# CTF验证端点
@app.post("/api/v1/ctf/submit")
def ctf_submit(flag: str = Form(...), db: Session = Depends(get_db)):
    _ensure_ctf_seeds(db)
    found = db.query(DBCTFFlag).filter(DBCTFFlag.flag_key == flag.strip()).first()
    if not found:
        return {"status": "wrong", "message": "Flag错误，继续尝试！"}
    if found.found_by:
        return {"status": "already_found", "message": f"这个Flag已经被 {found.found_by} 找到了！"}
    found.found_by = "弟弟"
    found.found_at = datetime.now()
    db.commit()
    total = db.query(DBCTFFlag).filter(DBCTFFlag.found_by.isnot(None)).count()
    all_count = db.query(DBCTFFlag).count()
    return {"status": "success", "title": found.title, "points": found.points, "message": f"🎉 恭喜！{found.title} (+{found.points}分)", "progress": f"{total}/{all_count}"}

@app.get("/api/v1/ctf/status")
def ctf_status(db: Session = Depends(get_db)):
    _ensure_ctf_seeds(db)
    flags = db.query(DBCTFFlag).all()
    found = [f for f in flags if f.found_by]
    return {
        "total": len(flags),
        "found": len(found),
        "total_points": sum(f.points for f in found),
        "max_points": sum(f.points for f in flags),
        "flags": [{"key": f.flag_key[:15]+"...", "title": f.title, "points": f.points, "difficulty": f.difficulty, "found": bool(f.found_by), "found_at": f.found_at.strftime("%m/%d %H:%M") if f.found_at else None} for f in flags]
    }

@app.get("/api/v1/ctf/hint/{flag_key:path}")
def ctf_hint(flag_key: str, db: Session = Depends(get_db)):
    hints = db.query(DBCTFHint).filter(DBCTFHint.flag_key == flag_key).order_by(DBCTFHint.hint_order).all()
    if not hints:
        return {"hints": ["这个flag没有额外的提示，靠你自己了！"]}
    return {"hints": [h.hint_text for h in hints]}


# ════════════════════════════════════════════════
# 🕵️ Extra CTF hidden endpoints for 100 challenges
# ════════════════════════════════════════════════

@app.get("/api/v1/ctf/challenge/{flag_id}", include_in_schema=False)
def ctf_challenge_detail(flag_id: str, db: Session = Depends(get_db)):
    fl = db.query(DBCTFFlag).filter(DBCTFFlag.flag_key == flag_id).first()
    if not fl: raise HTTPException(status_code=404)
    return {"title": fl.title, "description": fl.description, "points": fl.points, "difficulty": fl.difficulty, "found": bool(fl.found_by)}

# Base64 challenge response
@app.get("/api/v1/ctf/base64-challenge", include_in_schema=False)
def ctf_base64():
    return {"encoded": "Q29uZ3JhdHVsYXRpb25zISBZb3UgZm91bmQgaXQh", "hint": "base64 -d", "flag_format": "FLAG{...}"}

# XOR challenge endpoint
@app.get("/api/v1/ctf/xor-challenge", include_in_schema=False)
def ctf_xor():
    return {"encrypted": "2c0700170b1316591f131f561c0a1c0f561918131e031f570e", "hint": "Single-byte XOR. Key is 0x7a", "key": "0x7a"}

# ROT13 endpoint
@app.get("/api/v1/ctf/rot13-challenge", include_in_schema=False)
def ctf_rot13():
    return {"encoded": "SYNT{sbg13_vf_gur_bevtvany_pelcgb}", "hint": "ROT13 — rotate by 13"}

# Morse challenge
@app.get("/api/v1/ctf/morse-challenge", include_in_schema=False)
def ctf_morse():
    return {"morse": "..-. .-.. .- --. -.--. -- --- .-. ... . ..--.- -.-. --- -.. . ..--.- .. ... ..--.- -.-. .-.. .- ... ... .. -.-. -.--.-", "hint": "Morse code decoder online"}

# Vigenere challenge
@app.get("/api/v1/ctf/vigenere-challenge", include_in_schema=False)
def ctf_vigenere():
    return {"ciphertext": "WFNX{iphertb_fv_phnfprn_wnnqk}", "key": "RIN", "hint": "Vigenere cipher with key 'RIN'"}

# Caesar challenge
@app.get("/api/v1/ctf/caesar-challenge", include_in_schema=False)
def ctf_caesar():
    return {"ciphertext": "WKHENQ_BRFHVDU_BLSKHU_CL_DQFLHQW", "hint": "Shift by 3 (Caesar's favorite)", "shift": 3}

# JWT debug endpoint (shows token but in safe way)
@app.get("/api/v1/ctf/jwt-debug", include_in_schema=False)
def ctf_jwt():
    return {"hint": "JWT tokens are in the X-GP-Token header. Grab one and decode it at jwt.io", "structure": "header.payload.signature", "common_attacks": ["none algorithm", "weak HMAC secret", "expired token reuse"]}

# Hidden leaderboard endpoint
@app.get("/api/v1/ctf/leaderboard", include_in_schema=False)
def ctf_leaderboard(db: Session = Depends(get_db)):
    flags = db.query(DBCTFFlag).filter(DBCTFFlag.found_by.isnot(None)).all()
    if not flags: return {"players": [], "message": "No flags found yet! Be the first!"}
    players = {}
    for fl in flags:
        if fl.found_by not in players: players[fl.found_by] = {"name": fl.found_by, "total_points": 0, "flags_found": 0}
        players[fl.found_by]["total_points"] += fl.points
        players[fl.found_by]["flags_found"] += 1
    return {"players": sorted(players.values(), key=lambda x: x["total_points"], reverse=True)}

# Fake admin panel (further CTF bait)
@app.get("/admin-panel", include_in_schema=False)
def fake_admin_panel():
    return HTMLResponse(content="""<!DOCTYPE html><html><head><title>Admin Panel</title>
<style>body{background:#000;color:#0f0;font-family:monospace;padding:40px}h1{color:red}input{padding:8px;margin:5px;border:1px solid #0f0;background:#000;color:#0f0}</style></head><body>
<h1>⚠️ Restricted Access</h1><p>Username: <input disabled value='admin'></p><p>Password: <input type='password'></p>
<button onclick="alert('Nice try! This is a CTF training page.\\\\n\\\\nTry the real admin at /admin')">Login</button>
<!-- FLAG{hidden_in_plain_sight} — sometimes the flag is exactly where you would look -->
<!-- Next hint: check /api/v1/ctf/leaderboard --></body></html>""")

# Old backup endpoint
@app.get("/backup.tar.gz", include_in_schema=False)
def fake_tarball():
    return Response(content="FLAG{backup_files_are_dangerous}\n\nAlways check for common backup file extensions:\n  .bak .old .backup .zip .tar.gz .sql .swp ~\n\nNext: try /.env or /.git/config", media_type="text/plain")

@app.get("/.env", include_in_schema=False)
def fake_env():
    return PlainTextResponse("""# Application Environment Config
# FLAG{env_file_leaked} — NEVER commit .env files!

DB_HOST=localhost
DB_NAME=family_fund
DB_USER=admin
DB_PASS=SuperSecret123  # (this is fake, don't try it)
SECRET_KEY=FLAG_GOES_HERE
API_TOKEN=not_a_real_token_obviously

# Next challenge: try /.git/config
""")

@app.get("/.git/HEAD", include_in_schema=False)
def fake_git():
    return PlainTextResponse("ref: refs/heads/main\n\nFLAG{git_exposed_dot_git}\n\n.git directories should NEVER be web-accessible!\nUse a proper deployment pipeline instead.\n\nNext: try /Dockerfile")

@app.get("/Dockerfile", include_in_schema=False)
def fake_dockerfile():
    return PlainTextResponse("""FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
# FLAG{dockerfile_tells_the_stack}
# Always use .dockerignore to exclude sensitive files!
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
EXPOSE 8000
# Next: check robots.txt for more hidden paths
""")

# Status endpoint with timing (for timing attack challenge)
@app.get("/api/v1/ctf/timing-test/{user}", include_in_schema=False)
def ctf_timing(user: str):
    import time as _t
    if user == "admin":
        _t.sleep(0.5)  # Simulate DB lookup
        return {"valid": True}
    _t.sleep(0.01)
    return {"valid": False}

# CTF search API
@app.get("/api/v1/ctf/search", include_in_schema=False)
def ctf_search(q: str = "", difficulty: str = "", category: str = "", db: Session = Depends(get_db)):
    _ensure_ctf_seeds(db)
    query = db.query(DBCTFFlag)
    if q: query = query.filter(DBCTFFlag.title.contains(q) | DBCTFFlag.description.contains(q))
    if difficulty: query = query.filter(DBCTFFlag.difficulty == difficulty)
    flags = query.all()
    return {"results": [{"title": f.title, "points": f.points, "difficulty": f.difficulty, "found": bool(f.found_by), "desc": f.description} for f in flags]}


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


# ==========================================
# 🥚🥚🥚 趣味短链接跳转彩蛋
# ==========================================

# Dynamic shortcuts loaded from DB — see above
_ = 0  
# Shortcuts now handled dynamically via /go/{path} and DB