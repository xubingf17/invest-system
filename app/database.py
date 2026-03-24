from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import importlib

# 直接用字串導入 Base，避免啟動時的循環導入問題
models_module = importlib.import_module("app.models")
Base = models_module.Base

SQLALCHEMY_DATABASE_URL = "sqlite:////src/data/investment.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()