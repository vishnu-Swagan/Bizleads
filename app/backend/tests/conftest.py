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
from fastapi import HTTPException, Request, status
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

# Identity travels per-request via this header, not via global app state. FastAPI
# reads app.dependency_overrides once per request from the shared `app` object, so
# a lambda closing over a single user (the old approach) gets clobbered the moment
# a second authenticated client fixture is built in the same test - both clients
# would then authenticate as whichever user's override was installed last. Reading
# the identity from a per-request header instead means the *same* override function
# can be shared by every authenticated client: installing it twice is idempotent,
# and each request still resolves to the identity its own client sent.
_TEST_USER_HEADER = "X-Test-User"
_USERS_BY_ID = {USER_A_ID: USER_A, USER_B_ID: USER_B}


async def _override_get_current_user_from_header(request: Request) -> UserResponse:
    user = _USERS_BY_ID.get(request.headers.get(_TEST_USER_HEADER))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication credentials were not provided"
        )
    return user


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


@pytest_asyncio.fixture
async def _overrides_cleanup():
    # Shared (cached per-test) by every client fixture below, so no matter how many
    # of anon_client/user_a_client/user_b_client a test requests, this runs exactly
    # once, after all of them have torn down (pytest fixture teardown is LIFO, and
    # this is set up before any client fixture that depends on it). Clearing
    # app.dependency_overrides from each client fixture's own teardown - the
    # previous approach - meant the first client to tear down wiped the overrides
    # out from under any client fixture still torn down after it.
    yield
    app.dependency_overrides.clear()


def _build_client(db_session, user_id):
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    if user_id is not None:
        app.dependency_overrides[get_current_user] = _override_get_current_user_from_header

    headers = {_TEST_USER_HEADER: user_id} if user_id is not None else {}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)


@pytest_asyncio.fixture
async def anon_client(db_session, _overrides_cleanup):
    # No get_current_user override is installed here, so requests exercise the
    # real auth dependency and get a genuine 401 when no token is supplied.
    async with _build_client(db_session, None) as client:
        yield client


@pytest_asyncio.fixture
async def user_a_client(db_session, _overrides_cleanup):
    async with _build_client(db_session, USER_A_ID) as client:
        yield client


@pytest_asyncio.fixture
async def user_b_client(db_session, _overrides_cleanup):
    async with _build_client(db_session, USER_B_ID) as client:
        yield client
