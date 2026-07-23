"""数据库连接层。

- 异步引擎：供 FastAPI 路由使用，基于 aiomysql 驱动。
- 同步引擎：供 Celery Worker 使用，基于 pymysql 驱动。

"""
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

# FastAPI 异步引擎（aiomysql）
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
)

async_session = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,  
)

# Celery Worker 同步引擎（pymysql）
sync_engine = create_engine(
    settings.DATABASE_URL.replace("mysql+aiomysql", "mysql+pymysql"),
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20,
)

SyncSession = sessionmaker(
    sync_engine,
    class_=Session,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """每个 HTTP 请求一个独立会话，请求结束自动归还连接池。"""
    async with async_session() as session:
        yield session
