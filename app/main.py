from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date
from dateutil.relativedelta import relativedelta
from typing import List

from . import models, schemas, database
from .database import get_db, init_db

# 啟動時自動初始化資料庫表格
init_db()

app = FastAPI(title="投資團隊管理系統")

@app.get("/")
def read_root():
    return {"status": "系統運作中", "version": "1.0"}

# --- 1. 職級管理 (Ranks) ---
@app.post("/ranks/", response_model=schemas.RankResponse, tags=["基礎資料"])
def create_rank(rank: schemas.RankCreate, db: Session = Depends(get_db)):
    db_rank = models.Rank(**rank.model_dump())
    db.add(db_rank)
    db.commit()
    db.refresh(db_rank)
    return db_rank

@app.get("/ranks/", response_model=List[schemas.RankResponse], tags=["基礎資料"])
def list_ranks(db: Session = Depends(get_db)):
    return db.query(models.Rank).all()

# --- 2. 利率方案管理 (Rate Plans) ---
@app.post("/plans/", response_model=schemas.PlanResponse, tags=["基礎資料"])
def create_plan(plan: schemas.PlanCreate, db: Session = Depends(get_db)):
    db_plan = models.RatePlan(**plan.model_dump())
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)
    return db_plan

@app.get("/plans/", response_model=List[schemas.PlanResponse], tags=["基礎資料"])
def list_plans(db: Session = Depends(get_db)):
    return db.query(models.RatePlan).all()

# --- 3. 業務員管理 (Agents) ---
@app.post("/agents/", response_model=schemas.AgentResponse, tags=["團隊管理"])
def create_agent(agent: schemas.AgentCreate, db: Session = Depends(get_db)):
    db_agent = models.Agent(**agent.model_dump())
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    return db_agent

@app.get("/agents/", response_model=List[schemas.AgentResponse], tags=["團隊管理"])
def list_agents(db: Session = Depends(get_db)):
    return db.query(models.Agent).all()

# --- 4. 客戶管理 (Customers) ---
@app.post("/customers/", response_model=schemas.CustomerResponse, tags=["客戶管理"])
def create_customer(customer: schemas.CustomerCreate, db: Session = Depends(get_db)):
    db_customer = models.Customer(**customer.model_dump())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@app.get("/customers/", response_model=List[schemas.CustomerResponse], tags=["客戶管理"])
def list_customers(db: Session = Depends(get_db)):
    return db.query(models.Customer).all()

# --- 5. 投資合約 (Contracts) - 包含自動計算結束日 ---
@app.post("/contracts/", response_model=schemas.ContractResponse, tags=["業務核心"])
def create_contract(contract: schemas.ContractCreate, db: Session = Depends(get_db)):
    # A. 查詢方案以獲取期數(Months)
    plan = db.query(models.RatePlan).filter(models.RatePlan.plan_id == contract.plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="找不到指定的利率方案")
    
    # B. 計算 end_date
    calculated_end_date = contract.start_date + relativedelta(months=plan.period_months)
    
    # C. 寫入資料庫
    db_contract = models.InvestContract(
        customer_id=contract.customer_id,
        plan_id=contract.plan_id,
        amount=contract.amount,
        start_date=contract.start_date,
        end_date=calculated_end_date,
        status="Active"
    )
    db.add(db_contract)
    db.commit()
    db.refresh(db_contract)
    return db_contract

# --- 6. 收益試算 API (核心需求) ---
@app.get("/calculations/payouts", tags=["財務報表"])
def calculate_payouts(
    start_date: date = Query(..., description="查詢區間開始"),
    end_date: date = Query(..., description="查詢區間結束"),
    db: Session = Depends(get_db)
):
    """
    輸入時間區間，系統算出該區間內所有生效合約應發放的收益
    """
    # 搜尋在區間內處於 Active 狀態且時間重疊的合約
    contracts = db.query(models.InvestContract).filter(
        models.InvestContract.status == "Active",
        models.InvestContract.start_date <= end_date,
        models.InvestContract.end_date >= start_date
    ).all()
    
    results = []
    total_payout = 0
    
    for c in contracts:
        # 簡單計算邏輯：本金 * (年利率/100) / 12 (假設為月領)
        monthly_payout = round(c.amount * (c.plan.annual_rate / 100) / 12, 2)
        total_payout += monthly_payout
        
        results.append({
            "customer_name": c.customer.name,
            "amount": c.amount,
            "plan_name": c.plan.plan_name,
            "annual_rate": f"{c.plan.annual_rate}%",
            "estimated_monthly_payout": monthly_payout,
            "contract_end_date": c.end_date
        })
        
    return {
        "query_period": {"from": start_date, "to": end_date},
        "total_contracts_found": len(contracts),
        "total_estimated_payout": round(total_payout, 2),
        "details": results
    }

@app.post("/contracts/batch/", tags=["業務核心"])
def create_contracts_batch(contracts: List[schemas.ContractCreate], db: Session = Depends(get_db)):
    db_contracts = []
    for contract in contracts:
        plan = db.query(models.RatePlan).filter(models.RatePlan.plan_id == contract.plan_id).first()
        if not plan:
            continue # 或是報錯
        
        end_date = contract.start_date + relativedelta(months=plan.period_months)
        
        db_contract = models.InvestContract(
            customer_id=contract.customer_id,
            plan_id=contract.plan_id,
            amount=contract.amount,
            start_date=contract.start_date,
            end_date=end_date,
            status="Active"
        )
        db_contracts.append(db_contract)
    
    db.add_all(db_contracts)
    db.commit()
    return {"message": f"成功批量匯入 {len(db_contracts)} 筆合約"}