from pydantic import BaseModel
from datetime import date
from typing import Optional, List

# --- 職級 (Rank) ---
class RankBase(BaseModel):
    rank_name: str
    commission_rate: float

class RankCreate(RankBase):
    pass

class RankResponse(RankBase):
    rank_id: int
    class Config:
        from_attributes = True

# --- 利率方案 (RatePlan) ---
class RatePlanBase(BaseModel):
    plan_name: str
    annual_rate: float
    period_months: int

class PlanCreate(RatePlanBase):
    pass

class PlanResponse(RatePlanBase):
    plan_id: int
    class Config:
        from_attributes = True

# --- 業務 (Agent) ---
class AgentBase(BaseModel):
    name: str
    rank_id: int

class AgentCreate(AgentBase):
    pass

class AgentResponse(AgentBase):
    agent_id: int
    class Config:
        from_attributes = True

# --- 客戶 (Customer) ---
class CustomerBase(BaseModel):
    name: str
    bank_info: Optional[str] = None
    agent_id: int

class CustomerCreate(CustomerBase):
    pass

class CustomerResponse(CustomerBase):
    customer_id: int
    class Config:
        from_attributes = True

# --- 投資合約 (InvestContract) ---
class ContractBase(BaseModel):
    customer_id: int
    plan_id: int
    amount: float
    start_date: date

class ContractCreate(ContractBase):
    pass

class ContractResponse(ContractBase):
    contract_id: int
    end_date: Optional[date]
    status: str
    class Config:
        from_attributes = True