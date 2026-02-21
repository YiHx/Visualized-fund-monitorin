from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse # 新增：用来发送网页文件
from fastapi.security import HTTPBasic, HTTPBasicCredentials # 新增：HTTP基础密码锁
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, Float, Date, desc, extract
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from datetime import date
import os
import shutil
import secrets # 新增：用来安全对比密码

# ==========================================
# 0. 环境准备
# ==========================================
UPLOAD_DIR = "uploads"
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

SQLALCHEMY_DATABASE_URL = "sqlite:///./family_fund.db"
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
    tx_type = Column(String, nullable=False) # PRINCIPAL, ALPHA, WITHDRAWAL, QUARTERLY_PAYOUT
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

# 全局状态表 (用来控制季度派息是否开启)
class DBSystemState(Base):
    __tablename__ = "system_state"
    id = Column(Integer, primary_key=True, index=True)
    quarterly_claim_active = Column(Integer, default=0) # 0 关闭, 1 开启

Base.metadata.create_all(bind=engine)

app = FastAPI(title="家庭高净值资产控制台")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ==========================================
# 密码锁与网页分发路由 (实现 / 和 /admin 隔离)
# ==========================================
security = HTTPBasic()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    """这里设置你的专属 GP 账号和密码"""
    correct_username = secrets.compare_digest(credentials.username.encode("utf8"), b"your_username") # 
    correct_password = secrets.compare_digest(credentials.password.encode("utf8"), b"your_password")
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="权限不足：您不是该资产池的全权受托人。",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/")
def serve_lp_dashboard():
    """主域名：直接展示弟弟的监控台"""
    return FileResponse("dashboard.html")

@app.get("/admin")
def serve_gp_admin(username: str = Depends(get_current_username)):
    """/admin 路由：必须输入上面的账号密码才能访问控制台"""
    return FileResponse("admin.html")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ==========================================
# 2. 核心风控算法：动态额度计算
# ==========================================
def get_dynamic_monthly_limit():
    """计算第 5.2(a) 款规定的当月提款上限 (严格按每年4月3日生日上浮)"""
    BASE_LIMIT = 100.0
    today = date.today()
    current_year = today.year
    
    # 2027年以前，绝对是基础额度
    if current_year < 2027:
        return BASE_LIMIT
        
    # 计算他过了几次“涨薪日”(4月3日)
    # 按照合同，2027年是第1次涨薪，2028年是第2次，以此类推...
    years_passed = current_year - 2026
    
    # 核心制裁逻辑：只要今天的日期还没到当年的 4月3日，
    # 那么今年的 10% 上浮就坚决不生效，按去年的额度算！
    if today < date(current_year, 4, 3):
        years_passed -= 1
        
    # 如果倒退完了发现次数 <= 0 (比如在 2027年4月2日)，依然是基础额度
    if years_passed <= 0:
        return BASE_LIMIT
        
    # 严格按照复利公式计算上浮 (基础额度 * 1.1 的 N 次方)
    return round(BASE_LIMIT * ((1.1) ** years_passed), 2)

def get_current_month_used(db: Session):
    """统计当前自然月，乙方已经提取或正在申请的额度"""
    today = date.today()
    # 已经成功提款的
    used_tx = db.query(DBTransaction).filter(
        DBTransaction.tx_type == 'WITHDRAWAL',
        extract('year', DBTransaction.tx_date) == today.year,
        extract('month', DBTransaction.tx_date) == today.month
    ).all()
    
    # 还在 Pending 待审批的（防止疯狂提交申请卡BUG）
    pending_req = db.query(DBRequest).filter(
        DBRequest.req_type == 'WITHDRAWAL_REQ',
        DBRequest.status == 'PENDING',
        extract('year', DBRequest.req_date) == today.year,
        extract('month', DBRequest.req_date) == today.month
    ).all()
    
    total_used = sum([t.amount for t in used_tx]) + sum([r.amount for r in pending_req])
    return total_used

# ==========================================
# 3. 清算引擎 (包含 FIFO 和复利)
# ==========================================
def calculate_system_nav(db: Session, current_date: date):
    HURDLE_RATE = 0.015 
    txs = db.query(DBTransaction).order_by(DBTransaction.tx_date.asc()).all()
    
    total_principal, total_alpha, total_interest = 0.0, 0.0, 0.0
    # 季度法定派发 (QUARTERLY_PAYOUT) 不占用单月 100 元限额，但取走钱依然要走 FIFO 扣除本金
    withdrawals = [t.amount for t in txs if t.tx_type in ['WITHDRAWAL', 'QUARTERLY_PAYOUT']]
    inflows = [t for t in txs if t.tx_type in ['PRINCIPAL', 'ALPHA']]
    
    for inflow in inflows:
        days_held = (current_date - inflow.tx_date).days
        if days_held < 0: continue
            
        effective_amount = inflow.amount
        while withdrawals and effective_amount > 0:
            w = withdrawals[0]
            if effective_amount >= w:
                effective_amount -= w
                withdrawals.pop(0) 
            else:
                withdrawals[0] -= effective_amount
                effective_amount = 0 
                
        interest = effective_amount * ((1 + HURDLE_RATE) ** (days_held / 365.0) - 1)
        total_interest += interest
        
        if inflow.tx_type == 'PRINCIPAL': total_principal += effective_amount
        else: total_alpha += effective_amount

    r_total = total_principal + total_alpha + total_interest
    return {
        "R_total": round(r_total, 4),           
        "R_guaranteed": round(r_total * 0.50, 2), 
        "effective_principal": round(total_principal, 2),
        "total_alpha": round(total_alpha, 2),
        "total_compound_interest": round(total_interest, 4) 
    }

# ==========================================
# 4. LP 前端接口 (弟弟视角)
# ==========================================
@app.get("/api/v1/lp/limit_status")
def get_limit_status(db: Session = Depends(get_db)):
    """返回当月额度使用情况供前端展示"""
    limit = get_dynamic_monthly_limit()
    used = get_current_month_used(db)
    state = db.query(DBSystemState).first()
    can_claim = state.quarterly_claim_active == 1 if state else False
    
    return {
        "monthly_limit": limit,
        "used_amount": used,
        "remaining": round(limit - used, 2),
        "can_claim_quarterly": can_claim
    }

@app.post("/api/v1/lp/request_withdrawal")
def lp_request_withdrawal(amount: float = Form(...), reason: str = Form(...), db: Session = Depends(get_db)):
    limit = get_dynamic_monthly_limit()
    used = get_current_month_used(db)
    
    # 【风控拦截】超额直接拒绝！
    if used + amount > limit:
        raise HTTPException(status_code=403, detail=f"触发熔断：申请金额(¥{amount}) + 本月已用(¥{used}) 已超本月动态上限(¥{limit})！")
        
    new_req = DBRequest(req_type="WITHDRAWAL_REQ", amount=amount, reason=reason)
    db.add(new_req)
    db.commit()
    return {"status": "success", "message": "资金用途已提交，正在排队等待 GP 审查。"}

@app.post("/api/v1/lp/claim_quarterly")
def claim_quarterly(db: Session = Depends(get_db)):
    """领取季度派发"""
    state = db.query(DBSystemState).first()
    if not state or state.quarterly_claim_active == 0:
        raise HTTPException(status_code=403, detail="当前非季度派息期或已失效。")
        
    # 生成一条免审提款流水
    new_tx = DBTransaction(tx_type="QUARTERLY_PAYOUT", amount=30.0, description="第5.5款：季度法定流动性派发提取")
    db.add(new_tx)
    # 领完后，自动关闭开关
    state.quarterly_claim_active = 0
    db.commit()
    return {"status": "success", "message": "30元已派发至个人账户，享受自由支配权！"}

@app.post("/api/v1/lp/request_alpha")
def lp_request_alpha(reason: str = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    """乙方只管交凭证，不填金额，金额默认为0，等待GP核定"""
    file_location = f"{UPLOAD_DIR}/{file.filename}"
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)
        
    # amount 直接强制设为 0.0
    new_req = DBRequest(req_type="ALPHA_REQ", amount=0.0, reason=reason, proof_image=file_location)
    db.add(new_req)
    db.commit()
    return {"status": "success", "message": "凭证已上传，进入审计队列，请等待 GP 裁定奖励金额。"}

@app.get("/api/v1/lp/my_requests")
def lp_get_my_requests(db: Session = Depends(get_db)):
    """获取乙方提交的最新 10 条工单 (防止历史包袱过重)"""
    return db.query(DBRequest).order_by(desc(DBRequest.req_date), desc(DBRequest.id)).limit(10).all()

# ==========================================
# 5. GP 控制台接口 (哥哥视角)
# ==========================================
@app.post("/api/v1/gp/inject_funds")
def gp_inject_funds(amount: float = Form(...), tx_type: str = Form(...), description: str = Form(...), db: Session = Depends(get_db)):
    """供 GP 手动注入年度本金或对赌红利"""
    new_tx = DBTransaction(tx_type=tx_type, amount=amount, description=description)
    db.add(new_tx)
    db.commit()
    return {"status": "success", "message": "资金注入底层资产池，开始指数计息。"}

@app.post("/api/v1/gp/toggle_quarterly")
def toggle_quarterly(db: Session = Depends(get_db)):
    """GP一键开启/关闭 季度派息通告"""
    state = db.query(DBSystemState).first()
    if not state:
        state = DBSystemState(quarterly_claim_active=1)
        db.add(state)
    else:
        state.quarterly_claim_active = 1 if state.quarterly_claim_active == 0 else 0
    db.commit()
    return {"status": "success", "is_active": state.quarterly_claim_active == 1}

@app.get("/api/v1/gp/pending_requests")
def gp_get_pending_requests(db: Session = Depends(get_db)):
    return db.query(DBRequest).filter(DBRequest.status == "PENDING").all()

@app.post("/api/v1/gp/process_request/{req_id}")
def gp_process_request(req_id: int, action: str, final_amount: float = 0.0, db: Session = Depends(get_db)):
    """GP 审批时，如果是发红利，由 GP 传入 final_amount"""
    req = db.query(DBRequest).filter(DBRequest.id == req_id).first()
    if action == "REJECT":
        req.status = "REJECTED"
        db.commit()
        return {"message": "已行使一票否决权。"}
        
    if action == "APPROVE":
        req.status = "APPROVED"
        tx_type = "WITHDRAWAL" if req.req_type == "WITHDRAWAL_REQ" else "ALPHA"
        
        # 核心逻辑：如果是提款，按他申请的额度扣；如果是发奖金，按你敲定的 final_amount 发！
        actual_amount = final_amount if req.req_type == "ALPHA_REQ" else req.amount
        
        new_tx = DBTransaction(tx_type=tx_type, amount=actual_amount, description=f"审计批准: {req.reason}")
        db.add(new_tx)
        db.commit()
        return {"message": f"指令已执行，已核准金额 ¥{actual_amount} 并入账。"}

@app.post("/api/v1/gp/asset_allocation")
def gp_update_allocation(asset_name: str = Form(...), amount: float = Form(...), db: Session = Depends(get_db)):
    """GP 手动调仓，并增加【超额风控拦截】"""
    # 1. 先算出当前资金池到底有多少钱 (R_total)
    nav_data = calculate_system_nav(db, date.today())
    r_total = nav_data["R_total"]
    
    existing = db.query(DBAssetAllocation).filter(DBAssetAllocation.asset_name == asset_name).first()
    
    if amount <= 0:
        if existing:
            db.delete(existing)
            db.commit()
        return {"status": "success", "message": f"已清仓标的：{asset_name}"}
        
    # 2. 算一下除了现在正在改的这个标的，其他标的已经占用了多少钱？
    other_allocs = db.query(DBAssetAllocation).filter(DBAssetAllocation.asset_name != asset_name).all()
    other_sum = sum([a.allocated_amount for a in other_allocs])
    
    # 3. 核心拦截逻辑：别人占用的钱 + 你现在想分配的钱，绝不能超过总资金池！
    if other_sum + amount > r_total:
        raise HTTPException(status_code=400, detail=f"风控拦截：可分配金额不足！当前总资金池: ¥{r_total:.2f}，其他已分配: ¥{other_sum:.2f}。你无权借钱加杠杆！")
        
    if existing:
        existing.allocated_amount = amount # 调仓
    else:
        new_alloc = DBAssetAllocation(asset_name=asset_name, allocated_amount=amount) # 建仓
        db.add(new_alloc)
        
    db.commit()
    return {"status": "success", "message": f"宏观配置已更新：{asset_name} -> ¥{amount}"}

@app.get("/api/v1/dashboard")
def get_dashboard(db: Session = Depends(get_db)):
    """全局数据查询接口（修复了丢包问题）"""
    nav_data = calculate_system_nav(db, date.today())
    ledger = db.query(DBTransaction).order_by(desc(DBTransaction.tx_date)).limit(20).all()
    
    # 👉 罪魁祸首就是原来漏了这行代码！现在把数据库里的分配数据提出来打包！
    allocations = db.query(DBAssetAllocation).all()
    alloc_list = [{"asset": a.asset_name, "amount": a.allocated_amount} for a in allocations]
    
    return {
        "nav": nav_data, 
        "ledger": ledger,
        "allocations": alloc_list  # 打包发给前端！
    }