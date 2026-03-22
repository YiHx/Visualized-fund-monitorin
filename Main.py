from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, desc, extract
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import date, datetime, timedelta
import os
import shutil
import secrets
import requests
from sqlalchemy.exc import SQLAlchemyError

# ==========================================
# 0. 环境准备
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

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

Base.metadata.create_all(bind=engine)

app = FastAPI(title="家庭高净值资产控制台")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

security = HTTPBasic()
def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username.encode("utf8"), b"gp") 
    correct_password = secrets.compare_digest(credentials.password.encode("utf8"), b"gp123")
    if not (correct_username and correct_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="权限不足", headers={"WWW-Authenticate": "Basic"})
    return credentials.username

@app.get("/")
def serve_lp_dashboard(): return FileResponse("dashboard.html")
@app.get("/admin")
def serve_gp_admin(username: str = Depends(get_current_username)): return FileResponse("admin.html")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# ==========================================
# 2. 核心算法与引擎
# ==========================================
def notify_gp_wechat(title, content):
    url = "http://www.pushplus.plus/send"
    data = {
        "token": "e92ace8deade436093a43798c81ecddc",
        "title": title,
        "content": content
    }
    try:
        # 给微信发信号，超时时间设为 2 秒，防止卡顿
        requests.post(url, json=data, timeout=2)
    except Exception as e:
        print(f"微信通知发送失败: {e}")

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
    """Return allocation amounts adjusted to current NAV for consistent dashboard display."""
    raw_allocations = db.query(DBAssetAllocation).all()
    if not raw_allocations:
        return []

    raw_total = sum(a.allocated_amount for a in raw_allocations if a.allocated_amount and a.allocated_amount > 0)
    if raw_total <= 0 or nav_total <= 0:
        return [{"asset": a.asset_name, "amount": 0.0} for a in raw_allocations]

    # If configured allocation exceeds current NAV, scale all legs proportionally.
    scale = min(1.0, nav_total / raw_total)
    return [{
        "asset": a.asset_name,
        "amount": round(max(0.0, a.allocated_amount * scale), 2)
    } for a in raw_allocations]

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
class VerifyReq(BaseModel): pin: str
@app.post("/api/v1/lp/verify")
def verify_lp(req: VerifyReq):
    if req.pin == "0103": return {"status": "success"}
    raise HTTPException(status_code=403, detail="授权码错误。")

@app.get("/api/v1/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    nav = calculate_system_nav(db, date.today())
    return {
        "nav": nav,
        "ledger": db.query(DBTransaction).order_by(desc(DBTransaction.tx_date), desc(DBTransaction.id)).limit(20).all(),
        "allocations": get_display_allocations(db, nav["R_total"]),
        "quarterly_info": get_quarterly_info(db)
    }

@app.get("/api/v1/lp/notices")
def lp_get_notices(db: Session = Depends(get_db)):
    notices = db.query(DBNotice).order_by(desc(DBNotice.id)).limit(5).all()
    return [{"id": n.id, "content": n.content, "publish_time": n.publish_time.strftime("%Y-%m-%d %H:%M")} for n in notices]

@app.post("/api/v1/gp/notices")
def gp_post_notice(content: str = Form(...), db: Session = Depends(get_db)):
    db.add(DBNotice(content=content))
    db.commit()
    return {"status": "success", "message": "全网通知已强势发布！"}

# 👉 新增：GP 撤回通知的绝杀接口
@app.delete("/api/v1/gp/notices/{notice_id}")
def gp_delete_notice(notice_id: int, db: Session = Depends(get_db)):
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
            "created_date": m.created_date.strftime("%Y-%m-%d %H:%M") if m.created_date else None,
            "reply": m.reply,
            "reply_time": m.reply_time.strftime("%Y-%m-%d %H:%M") if m.reply_time else None
        })
    return out

@app.post("/api/v1/lp/messages")
def post_message(content: str = Form(...), db: Session = Depends(get_db)):
    try:
        db.add(DBMessage(content=content))
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="留言写入失败，请检查服务器数据库写权限。")
    notify_gp_wechat("💬 家庭办公室新留言", f"乙方有话对你说：\n{content}") # 👉 新加的这行
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

@app.post("/api/v1/gp/messages/{msg_id}/reply")
def reply_message(msg_id: int, reply: str = Form(...), db: Session = Depends(get_db)):
    msg = db.query(DBMessage).filter(DBMessage.id == msg_id).first()
    if msg:
        msg.reply = reply
        msg.reply_time = datetime.now()
        db.commit()
    return {"status": "success"}

@app.post("/api/v1/gp/inject_funds")
def gp_inject_funds(amount: float = Form(...), tx_type: str = Form(...), description: str = Form(...), db: Session = Depends(get_db)):
    db.add(DBTransaction(tx_type=tx_type, amount=amount, description=description)); db.commit()
    return {"status": "success", "message": f"资金注入成功！已将 ¥{amount} 并入 {tx_type} 引擎。"}

@app.post("/api/v1/gp/adjust_funds")
def gp_adjust_funds(action: str = Form(...), amount: float = Form(...), description: str = Form(...), db: Session = Depends(get_db)):
    if amount <= 0: raise HTTPException(status_code=400, detail="调整金额必须大于0")
    tx_type = "ADJUST_UP" if action == "UP" else "ADJUST_DOWN"
    db.add(DBTransaction(tx_type=tx_type, amount=amount, description=f"【上帝模式强控】{description}"))
    db.commit()
    verb = "强行注入" if action == "UP" else "强行扣除"
    return {"status": "success", "message": f"强控执行完毕：已从资金池{verb} ¥{amount}。"}

@app.post("/api/v1/gp/toggle_quarterly")
def toggle_quarterly(db: Session = Depends(get_db)):
    active = db.query(DBQuarterlyEvent).filter(DBQuarterlyEvent.status == "ACTIVE").all()
    for a in active: a.status = "EXPIRED"
    db.add(DBQuarterlyEvent(issued_at=datetime.now(), status="ACTIVE")); db.commit()
    return {"status": "success", "message": "72小时倒计时派息令已强势发布！"}

@app.get("/api/v1/gp/pending_requests")
def gp_get_pending_requests(db: Session = Depends(get_db)):
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

@app.post("/api/v1/gp/process_request/{req_id}")
def gp_process_request(req_id: int, action: str, final_amount: float = 0.0, reject_reason: str = "", db: Session = Depends(get_db)):
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
def gp_update_allocation(asset_name: str = Form(...), amount: float = Form(...), db: Session = Depends(get_db)):
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