from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytz
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

SP_TZ = pytz.timezone("America/Sao_Paulo")


class Base(DeclarativeBase):
    pass


def now_sp() -> datetime:
    return datetime.now(SP_TZ)


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    bling_client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    bling_client_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    access_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    plan_sales: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_inventory: Mapped[bool] = mapped_column(Boolean, default=False)
    plan_financial: Mapped[bool] = mapped_column(Boolean, default=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    login_count: Mapped[int] = mapped_column(Integer, default=0)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_sp)


def get_engine(db_path: str = "database.db"):
    return create_engine(f"sqlite:///{db_path}", echo=False, future=True)


def get_session_local(db_path: str = "database.db"):
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine(db_path))


def init_db(db_path: str = "database.db") -> None:
    engine = get_engine(db_path)
    Base.metadata.create_all(bind=engine)
