from sqlalchemy import Column, Integer, String, Float, Date, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from datetime import date

# 這是最重要的基礎類別，所有的 Table 都必須繼承它
Base = declarative_base()

# 1. 職級表 (例如：專員、經理、副總，對應不同的抽成比例)
class Rank(Base):
    __tablename__ = "ranks"
    
    rank_id = Column(Integer, primary_key=True, index=True)
    rank_name = Column(String, unique=True, nullable=False)
    commission_rate = Column(Float, nullable=False)  # 業務抽成率，例如 0.005 代表 0.5%
    
    # 關聯：一個職級下可以有多個業務
    agents = relationship("Agent", back_populates="rank")

# 2. 業務表
class Agent(Base):
    __tablename__ = "agents"
    
    agent_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    rank_id = Column(Integer, ForeignKey("ranks.rank_id"))
    
    # 在這裡直接定義好，別人啟動時就會自動產生這個欄位
    boss_id = Column(Integer, ForeignKey("agents.agent_id"), nullable=True)
    
    # 關聯設定
    rank = relationship("Rank", back_populates="agents")
    customers = relationship("Customer", back_populates="agent")

# 3. 客戶表
class Customer(Base):
    __tablename__ = "customers"
    
    customer_id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    bank_info = Column(String)  # 存儲銀行名稱、代碼、帳號等資訊
    agent_id = Column(Integer, ForeignKey("agents.agent_id"))
    note = Column(String, nullable=True)

    note = Column(String, nullable=True)
    
    # 關聯設定
    agent = relationship("Agent", back_populates="customers")
    contracts = relationship("InvestContract", back_populates="customer")

# 4. 利率方案表 (例如：方案A - 1.7% - 持續6個月)
class RatePlan(Base):
    __tablename__ = "rate_plans"
    
    plan_id = Column(Integer, primary_key=True, index=True)
    plan_name = Column(String, nullable=False)
    annual_rate = Column(Float, nullable=False)    # 年化利率，例如 1.7
    period_months = Column(Integer, nullable=False) # 方案期數(月份)，例如 6

# 5. 投資合約表 (核心：每一筆錢進來都在這裡)
class InvestContract(Base):
    __tablename__ = "invest_contracts"
    
    contract_id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.customer_id"))
    plan_id = Column(Integer, ForeignKey("rate_plans.plan_id"))
    amount = Column(Float, nullable=False)       # 投入本金
    start_date = Column(Date, nullable=False)    # 生效日期
    end_date = Column(Date)                      # 結束日期 (由程式自動算出)
    status = Column(String, default="Active")    # 狀態：Active (進行中), Completed (已結案)
    

    # 關聯設定
    customer = relationship("Customer", back_populates="contracts")
    plan = relationship("RatePlan")

    @property
    def is_expired(self):
        """自動判斷是否過期"""
        if self.end_date:
            return date.today() > self.end_date
        return False
