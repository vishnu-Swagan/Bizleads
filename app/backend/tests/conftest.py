import os
import sys
from pathlib import Path

# MUST run before importing anything from the app. Settings.__getattr__ raises
# AttributeError for absent env vars, and services/business_search.py constructs
# AIHubService() at module scope. Empty strings are falsy, so no client is built.
os.environ.setdefault("APP_AI_BASE_URL", "")
os.environ.setdefault("APP_AI_KEY", "")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-used")
os.environ.setdefault("MGX_IGNORE_INIT_DATA", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from core.database import Base, get_db
from dependencies.auth import get_current_user
from main import app
from schemas.auth import UserResponse

USER_A_ID = "user-a"
USER_B_ID = "user-b"

USER_A = UserResponse(id=USER_A_ID, email="a@example.com", role="user")
USER_B = UserResponse(id=USER_B_ID, email="b@example.com", role="user")


@pytest_asyncio.fixture
async def db_session():
    # StaticPool + check_same_thread keep every connection pointed at the same
    # in-memory database. Without it, create_all runs on a connection that is
    # then discarded and the tables vanish.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


def _build_client(db_session, user):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def anon_client(db_session):
    async with _build_client(db_session, None) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user_a_client(db_session):
    async with _build_client(db_session, USER_A) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def user_b_client(db_session):
    async with _build_client(db_session, USER_B) as client:
        yield client
    app.dependency_overrides.clear()
