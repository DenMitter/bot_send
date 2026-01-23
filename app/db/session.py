from typing import Optional
<<<<<<< HEAD

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
=======
>>>>>>> 9dd19731839bc17800be4d7e8cd1e3ac8fafa344

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import get_settings


_engine = None
<<<<<<< HEAD
_session_factory: Optional[async_sessionmaker] = None
=======
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None
>>>>>>> 9dd19731839bc17800be4d7e8cd1e3ac8fafa344


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.mysql_dsn, pool_pre_ping=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory
