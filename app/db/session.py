from __future__ import annotations

import os

from sqlalchemy import create_engine
from  sqlalchemy.orm import sessionmaker, DeclarativeBase

# DATABASE_URL = os.getenv("DATABASE_URL")
DATABASE_URL = "sqlite:///./diagnosis_agent.db"

class Base(DeclarativeBase):
    pass

engine = create_engine(
    DATABASE_URL,
    echo = True, #打印SQL语句到控制台
    future=True,
    connect_args={"check_same_thread": False}, #默认情况下sqlite只允许一个线程访问，设置false允许多线程环境下运行

)
SessionLocal = sessionmaker(#每次调用SessionLocal，会产生一个独立的事务环境
    bind = engine,
    autoflush=False, #不自动同步数据，明确同步的时候才同步
    autocommit=False,
    future= True,
)
def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
