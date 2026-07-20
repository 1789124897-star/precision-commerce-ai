"""SQLAlchemy 引擎 + 异步/同步 Session"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

async_engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
async_session = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# Celery worker 用同步引擎
sync_engine = create_engine(settings.DATABASE_URL.replace("mysql+aiomysql", "mysql+pymysql"), echo=settings.DEBUG)
SyncSession = sessionmaker(sync_engine, class_=Session, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
