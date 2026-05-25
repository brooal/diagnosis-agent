from __future__ import annotations

import os

from sqlalchemy import create_engine
from dotenv import load_dotenv
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("APP_DATABASE_URL") or os.getenv("DATABASE_URL", "sqlite:///./diagnosis_agent.db")
APP_DB_ECHO = os.getenv("APP_DB_ECHO", "false").lower() in {"1", "true", "yes", "y", "on"}


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    echo=APP_DB_ECHO,
    future=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
)


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
