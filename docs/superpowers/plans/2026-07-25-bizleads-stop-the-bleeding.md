# BizLeads Stop-the-Bleeding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the exploitable authentication, tenant-isolation, billing-integrity and AI-fabrication defects identified in `AUDIT-2026-07-25.md`, with automated tests that fail if any of them return.

**Architecture:** A single new `dependencies/tenancy.py` module supplies an `EntityPolicy` declaration per entity router, a `filter_writes` allowlist helper, and two workspace resolvers replacing five divergent copies of the same query. Each of the six currently-open routers declares one policy and applies it uniformly across its nine route shapes. Billing and discovery hardening are localised edits to `routers/payments.py` and `routers/discover.py`. Two frontend surfaces gain honest empty/setup states and a provenance badge.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, Postgres (production) / SQLite (tests), pytest + pytest-asyncio + httpx, React 18 + Vite + TypeScript + Tailwind + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-07-25-bizleads-security-remediation-design.md`

## Global Constraints

- Work happens in `/Users/vishnu/Downloads/Local Biz Weakness Finder`. Backend is `app/backend`, frontend is `app/frontend/src`. All `cd` commands below assume the repo root.
- Baseline commit is `481064a`. Every task ends with a commit.
- **Cross-tenant denial returns 404, never 403** — do not confirm another tenant's row exists.
- **Disallowed writes return 400 naming the rejected field.**
- Reuse the existing design system (shadcn/ui, Tailwind, slate neutrals, `indigo-600` primary). Do not introduce new colours, fonts, or component libraries.
- Colour is never the only signal on a badge — always pair with text.
- No new production dependencies. `pytest>=8.4.1`, `pytest-asyncio>=1.1.0`, `httpx>=0.27.0` and `aiosqlite>=0.20.0` are **already in `app/backend/requirements.txt`**.
- Python: run all backend commands from `app/backend`.

### Deviation from spec

Spec §7 calls for a separate `requirements-dev.txt`. **Skip it** — every test dependency is already present in `requirements.txt`. Adding a second file would create two sources of truth for no benefit.

### Known import-time hazard (affects Task 1 only)

`core/config.py:68` — `Settings.__getattr__` **raises `AttributeError`** when a dynamically-read env var is absent. `services/business_search.py:11` calls `AIHubService()` at module scope, whose `__init__` reads `settings.app_ai_base_url`. Importing the app therefore crashes unless those env vars exist. `conftest.py` sets them to empty strings *before* importing `main`; empty is falsy, so no OpenAI client is constructed.

Separately, `services/mapbox_places.py:13` reads `MAPBOX_ACCESS_TOKEN` at **module import**. Tests must patch the module attribute (`services.mapbox_places.MAPBOX_ACCESS_TOKEN`) or the `is_mapbox_configured` function — patching `os.environ` after import has no effect.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `app/backend/pytest.ini` | pytest config (asyncio auto mode, testpath) |
| `app/backend/tests/conftest.py` | Env priming, SQLite engine, `anon_client` / `user_a_client` / `user_b_client` fixtures |
| `app/backend/tests/test_smoke.py` | Proves the harness imports and serves |
| `app/backend/tests/test_route_auth.py` | Parametrized anonymous-access and deleted-route coverage |
| `app/backend/tests/test_tenant_isolation.py` | Cross-tenant read/write denial |
| `app/backend/tests/test_write_allowlist.py` | Privileged-field rejection, `never_return` masking |
| `app/backend/tests/test_billing.py` | verify-payment forgery and replay |
| `app/backend/tests/test_discovery.py` | Provider gate, credit ordering, fabrication guard |
| `app/backend/dependencies/tenancy.py` | `EntityPolicy`, scope/write helpers, workspace resolvers |
| `app/backend/alembic/versions/c7d1e2f3a4b5_add_leads_data_source.py` | `data_source` column + backfill |

**Modified:** `app/backend/main.py` (CORS, mock-seed gate), the six entity routers, `routers/leads.py`, `routers/lead_notes.py`, `routers/ai_interaction_logs.py`, `routers/aihub.py`, `routers/payments.py`, `routers/discover.py`, `routers/search.py`, `routers/automation.py`, `models/leads.py`, `app/frontend/src/pages/app/Discover.tsx`, `app/frontend/src/pages/app/Leads.tsx`, `app/frontend/src/pages/app/LeadDetail.tsx`.

---

## Task 1: Test harness

**Files:**
- Create: `app/backend/pytest.ini`
- Create: `app/backend/tests/__init__.py` (empty)
- Create: `app/backend/tests/conftest.py`
- Test: `app/backend/tests/test_smoke.py`

**Interfaces:**
- Consumes: nothing.
- Produces: fixtures `db_session` (`AsyncSession`), `anon_client` (`httpx.AsyncClient`, no auth override), `user_a_client` and `user_b_client` (`httpx.AsyncClient` with `get_current_user` overridden), and constants `USER_A_ID = "user-a"`, `USER_B_ID = "user-b"`. Every later task depends on these exact names.

- [ ] **Step 1: Write the failing smoke test**

Create `app/backend/tests/test_smoke.py`:

```python
async def test_health_endpoint_serves(anon_client):
    response = await anon_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
cd app/backend && python3 -m pytest tests/test_smoke.py -v
```

Expected: collection error — `fixture 'anon_client' not found`.

- [ ] **Step 3: Create pytest.ini**

Create `app/backend/pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: Create the empty test package marker**

```bash
cd app/backend && touch tests/__init__.py
```

- [ ] **Step 5: Write conftest.py**

Create `app/backend/tests/conftest.py`. The `os.environ` block must come before any project import — see the import-time hazard note above.

```python
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
```

- [ ] **Step 6: Run the smoke test to verify it passes**

```bash
cd app/backend && python3 -m pytest tests/test_smoke.py -v
```

Expected: PASS. If it errors on import with `AttributeError: 'Settings' object has no attribute '<name>'`, add that name's upper-case form to the `os.environ.setdefault` block and re-run.

- [ ] **Step 7: Commit**

```bash
git add app/backend/pytest.ini app/backend/tests/
git commit -m "test: add pytest harness with SQLite fixtures and auth overrides"
```

---

## Task 2: Delete the nine unauthenticated `/all` routes

**Files:**
- Modify: `app/backend/routers/leads.py:159-196` (delete the `query_leadss_all` route)
- Modify: `app/backend/routers/lead_notes.py`, `app/backend/routers/ai_interaction_logs.py`
- Modify: `app/backend/routers/workspaces.py`, `workspace_members.py`, `credit_ledger.py`, `provider_connections.py`, `offer_profiles.py`, `search_jobs.py`
- Test: `app/backend/tests/test_route_auth.py`

**Interfaces:**
- Consumes: `anon_client` from Task 1.
- Produces: nothing consumed later.

- [ ] **Step 1: Write the failing test**

Create `app/backend/tests/test_route_auth.py`:

```python
import pytest

ALL_ROUTES = [
    "/api/v1/entities/leads/all",
    "/api/v1/entities/lead_notes/all",
    "/api/v1/entities/ai_interaction_logs/all",
    "/api/v1/entities/workspaces/all",
    "/api/v1/entities/workspace_members/all",
    "/api/v1/entities/credit_ledger/all",
    "/api/v1/entities/provider_connections/all",
    "/api/v1/entities/offer_profiles/all",
    "/api/v1/entities/search_jobs/all",
]


@pytest.mark.parametrize("path", ALL_ROUTES)
async def test_all_routes_are_deleted(anon_client, path):
    response = await anon_client.get(path)
    assert response.status_code == 404, f"{path} still exists"
```

- [ ] **Step 2: Run it to confirm it fails**

```bash
cd app/backend && python3 -m pytest tests/test_route_auth.py -v
```

Expected: FAIL — the routes return 200 or 500, not 404.

- [ ] **Step 3: Delete each `/all` route**

In each of the nine router files, delete the entire decorated function beginning with `@router.get("/all", ...)` and ending at the line before the next `@router.` decorator. In `routers/leads.py` that is lines 159-196, the function `query_leadss_all`. The other files follow the identical generated shape with different names (`query_lead_notess_all`, `query_workspacess_all`, and so on).

Verify none remain:

```bash
cd app/backend && grep -rn '@router.get("/all"' routers/ && echo "STILL PRESENT" || echo "all removed"
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd app/backend && python3 -m pytest tests/test_route_auth.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add app/backend/routers/ app/backend/tests/test_route_auth.py
git commit -m "fix(security): delete nine unauthenticated /all routes

These returned every tenant's rows with no auth and no ownership filter.
leads/all exposed contact_email and contact_phone for every workspace."
```

---

## Task 3: Tenancy module

**Files:**
- Create: `app/backend/dependencies/tenancy.py`
- Test: `app/backend/tests/test_tenancy_helpers.py`

**Interfaces:**
- Consumes: `models.workspaces.Workspaces`, `dependencies.auth.get_current_user`, `core.database.get_db`.
- Produces, relied on by Tasks 4-6 and 9-10:
  - `EntityPolicy(model, scope, writable, never_return=frozenset(), allow_create=True, allow_delete=True)`
  - `filter_writes(payload: dict, policy, *, strict: bool) -> dict`
  - `async ensure_workspace_for_user(user: UserResponse, db: AsyncSession) -> Workspaces`
  - `async get_current_workspace(...) -> Workspaces` (FastAPI dependency; raises 404 when absent)

**Deviation from spec §3.3.** The spec also lists `apply_scope(stmt, policy, principal_id)` and `strip_never_return(data, policy)`. Neither is built, because neither ends up with a caller: the generated routers filter through the service layer's `query_dict` rather than composing raw SELECTs, and `config_json` is excluded by deleting it from the Pydantic response model (Task 6) — structurally stronger than filtering at runtime, since Pydantic then has nowhere to put it. Writing two helpers nothing calls would be dead code on day one. `EntityPolicy.never_return` is retained as a declaration of intent, and Task 6's test proves the field never leaks.

- [ ] **Step 1: Write the failing tests**

Create `app/backend/tests/test_tenancy_helpers.py`:

```python
import pytest
from fastapi import HTTPException

from dependencies.tenancy import EntityPolicy, filter_writes
from models.workspaces import Workspaces

WORKSPACE_POLICY = EntityPolicy(
    model=Workspaces,
    scope="user",
    writable=frozenset({"name", "settings_json"}),
    never_return=frozenset({"stripe_customer_id"}),
)


def test_filter_writes_keeps_allowed_fields():
    result = filter_writes({"name": "Acme"}, WORKSPACE_POLICY, strict=True)
    assert result == {"name": "Acme"}


def test_filter_writes_drops_silently_on_create():
    result = filter_writes({"name": "Acme", "plan": "agency"}, WORKSPACE_POLICY, strict=False)
    assert result == {"name": "Acme"}


def test_filter_writes_rejects_privileged_field_on_update():
    with pytest.raises(HTTPException) as exc:
        filter_writes({"plan": "agency"}, WORKSPACE_POLICY, strict=True)
    assert exc.value.status_code == 400
    assert "plan" in exc.value.detail


def test_filter_writes_ignores_none_values():
    result = filter_writes({"name": "Acme", "plan": None}, WORKSPACE_POLICY, strict=True)
    assert result == {"name": "Acme"}
```

Note the fourth test: partial-update payloads arrive with `None` for every unset field, so a `None` value for a privileged field must not trigger a 400 — only an explicit non-`None` value does.

- [ ] **Step 2: Run to confirm failure**

```bash
cd app/backend && python3 -m pytest tests/test_tenancy_helpers.py -v
```

Expected: `ModuleNotFoundError: No module named 'dependencies.tenancy'`.

- [ ] **Step 3: Write the module**

Create `app/backend/dependencies/tenancy.py`:

```python
"""Tenant scoping and write-policy enforcement for generated entity routers.

Every entity router declares one EntityPolicy and routes it through these
helpers. Adding a route without a policy is the bug class this module exists
to prevent, so keep the declaration at module scope where it is visible.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, FrozenSet, Literal, Type

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from models.workspaces import Workspaces
from schemas.auth import UserResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntityPolicy:
    """Declares how one entity table is scoped and what a client may write."""

    model: Type[Any]
    scope: Literal["user", "workspace"]
    writable: FrozenSet[str]
    never_return: FrozenSet[str] = field(default_factory=frozenset)
    allow_create: bool = True
    allow_delete: bool = True

    @property
    def scope_column(self) -> str:
        return "user_id" if self.scope == "user" else "workspace_id"


def filter_writes(payload: Dict[str, Any], policy: EntityPolicy, *, strict: bool) -> Dict[str, Any]:
    """Remove fields the client may not write.

    strict=False (create): silently drop disallowed keys.
    strict=True (update): reject with 400 naming the field, so a deliberate
    privilege-escalation attempt is reported rather than quietly ignored.

    None values are always dropped without error: partial-update payloads carry
    None for every unset field, which is not an attempt to write it.
    """
    cleaned: Dict[str, Any] = {}
    rejected = []

    for key, value in payload.items():
        if value is None:
            continue
        if key in policy.writable:
            cleaned[key] = value
        elif strict:
            rejected.append(key)

    if rejected:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Field(s) not writable by client: {', '.join(sorted(rejected))}",
        )

    return cleaned


async def ensure_workspace_for_user(user: UserResponse, db: AsyncSession) -> Workspaces:
    """Resolve the user's workspace, creating a trial one if absent.

    The only sanctioned creation point. Called from GET /billing/usage and
    POST /discover/run so the three previously-divergent copies of this logic
    behave identically.
    """
    result = await db.execute(select(Workspaces).where(Workspaces.owner_id == user.id))
    workspace = result.scalar_one_or_none()
    if workspace:
        return workspace

    now = datetime.utcnow()
    workspace = Workspaces(
        name=f"{user.email or 'User'}'s Workspace",
        slug=user.id[:8],
        owner_id=user.id,
        plan="trial",
        subscription_status="trialing",
        monthly_credits=25,
        credits_used=0,
        max_seats=1,
        trial_ends_at=(now + timedelta(days=7)).isoformat(),
        credits_reset_at=(now + timedelta(days=30)).isoformat(),
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return workspace


async def get_current_workspace(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workspaces:
    """Resolve the caller's workspace. Never creates; 404 when absent."""
    result = await db.execute(select(Workspaces).where(Workspaces.owner_id == current_user.id))
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No workspace found for this account")
    return workspace
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd app/backend && python3 -m pytest tests/test_tenancy_helpers.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/backend/dependencies/tenancy.py app/backend/tests/test_tenancy_helpers.py
git commit -m "feat(security): add EntityPolicy tenancy module

Declarative per-table scoping and write allowlists, plus a single
workspace resolver replacing five divergent copies."
```

---

## Task 4: Secure the `workspaces` router

This is the highest-risk router: its columns are the plan, credit and subscription state that made self-upgrade possible.

**Files:**
- Modify: `app/backend/routers/workspaces.py`
- Test: `app/backend/tests/test_write_allowlist.py`

**Interfaces:**
- Consumes: `EntityPolicy`, `filter_writes` (Task 3); `USER_A_ID` fixtures (Task 1).
- Produces: `WORKSPACES_POLICY` in `routers/workspaces.py`, the reference pattern Tasks 5-6 copy.

- [ ] **Step 1: Write the failing tests**

Create `app/backend/tests/test_write_allowlist.py`:

```python
import pytest
from sqlalchemy import select

from models.workspaces import Workspaces
from tests.conftest import USER_A_ID

PRIVILEGED_FIELDS = ["plan", "monthly_credits", "subscription_status", "max_seats"]


async def _seed_workspace(db_session, owner_id=USER_A_ID):
    workspace = Workspaces(
        name="Acme", slug="acme", owner_id=owner_id,
        plan="trial", subscription_status="trialing",
        monthly_credits=25, credits_used=0, max_seats=1,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


async def test_anonymous_cannot_list_workspaces(anon_client):
    response = await anon_client.get("/api/v1/entities/workspaces")
    assert response.status_code == 401


async def test_owner_can_rename_own_workspace(user_a_client, db_session):
    workspace = await _seed_workspace(db_session)
    response = await user_a_client.put(
        f"/api/v1/entities/workspaces/{workspace.id}", json={"name": "Renamed"}
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


@pytest.mark.parametrize("field,value", [
    ("plan", "agency"),
    ("monthly_credits", 999999),
    ("subscription_status", "active"),
    ("max_seats", 100),
])
async def test_privileged_fields_are_rejected(user_a_client, db_session, field, value):
    workspace = await _seed_workspace(db_session)
    response = await user_a_client.put(
        f"/api/v1/entities/workspaces/{workspace.id}", json={field: value}
    )
    assert response.status_code == 400
    assert field in response.json()["detail"]

    refreshed = (await db_session.execute(
        select(Workspaces).where(Workspaces.id == workspace.id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert getattr(refreshed, field) != value, f"{field} was mutated despite 400"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd app/backend && python3 -m pytest tests/test_write_allowlist.py -v
```

Expected: FAIL — anonymous listing returns 200, and privileged writes return 200 with the value applied.

- [ ] **Step 3: Declare the policy**

In `app/backend/routers/workspaces.py`, after the existing imports add:

```python
from dependencies.auth import get_current_user
from dependencies.tenancy import EntityPolicy, filter_writes
from models.workspaces import Workspaces
from schemas.auth import UserResponse

WORKSPACES_POLICY = EntityPolicy(
    model=Workspaces,
    scope="user",
    writable=frozenset({"name", "settings_json"}),
)
```

Ownership on this table lives in `owner_id`, not `user_id`, so the route handlers below compare against `owner_id` explicitly.

- [ ] **Step 4: Apply the pattern to all eight surviving routes**

Each generated router has these eight remaining route shapes. Apply each transformation exactly.

**GET "" (list)** — add the dependency and scope the query:

```python
@router.get("", response_model=WorkspacesListResponse)
async def query_workspacess(
    query: str = Query(None),
    sort: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=2000),
    fields: str = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkspacesService(db)
    query_dict = {}
    if query:
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
    query_dict["owner_id"] = current_user.id
    result = await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)
    return result
```

Forcing `owner_id` into `query_dict` after parsing means a client-supplied `owner_id` filter cannot widen the scope — it is always overwritten.

**GET "/{id}"** — 404 rather than 403 on someone else's row:

```python
@router.get("/{id}", response_model=WorkspacesResponse)
async def get_workspaces(
    id: int,
    fields: str = Query(None),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkspacesService(db)
    result = await service.get_by_id(id)
    if not result or result.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Workspaces not found")
    return result
```

**POST ""** — creation is server-only for workspaces:

```python
@router.post("", response_model=WorkspacesResponse, status_code=201)
async def create_workspaces(
    data: WorkspacesData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(
        status_code=403,
        detail="Workspaces are created automatically on first use and cannot be created via this API",
    )
```

**PUT "/{id}"** — ownership check then allowlist:

```python
@router.put("/{id}", response_model=WorkspacesResponse)
async def update_workspaces(
    id: int,
    data: WorkspacesUpdateData,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkspacesService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Workspaces not found")

    update_dict = filter_writes(data.model_dump(), WORKSPACES_POLICY, strict=True)
    if not update_dict:
        return existing

    result = await service.update(id, update_dict)
    if not result:
        raise HTTPException(status_code=404, detail="Workspaces not found")
    return result
```

**DELETE "/{id}"** — blocked:

```python
@router.delete("/{id}")
async def delete_workspaces(
    id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Workspaces cannot be deleted via this API")
```

**POST "/batch", PUT "/batch", DELETE "/batch"** — all three blocked for workspaces:

```python
@router.post("/batch", response_model=List[WorkspacesResponse], status_code=201)
async def create_workspacess_batch(
    request: WorkspacesBatchCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on workspaces")


@router.put("/batch", response_model=List[WorkspacesResponse])
async def update_workspacess_batch(
    request: WorkspacesBatchUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on workspaces")


@router.delete("/batch")
async def delete_workspacess_batch(
    request: WorkspacesBatchDeleteRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on workspaces")
```

**Route ordering matters:** FastAPI matches in declaration order, so `/batch` routes must stay declared before `/{id}` routes, exactly as the generated file already has them. Do not reorder.

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd app/backend && python3 -m pytest tests/test_write_allowlist.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add app/backend/routers/workspaces.py app/backend/tests/test_write_allowlist.py
git commit -m "fix(security): authenticate and scope the workspaces router

Anyone could PUT plan=agency, monthly_credits=999999 on any workspace.
Plan, credit and subscription columns are now server-only."
```

---

## Task 5: Secure the three read-only routers

`credit_ledger`, `search_jobs` and `workspace_members` accept no client writes at all.

**Files:**
- Modify: `app/backend/routers/credit_ledger.py`, `search_jobs.py`, `workspace_members.py`
- Test: `app/backend/tests/test_readonly_routers.py`

**Interfaces:**
- Consumes: `get_current_workspace` (Task 3).
- Produces: nothing consumed later.

- [ ] **Step 1: Write the failing tests**

Create `app/backend/tests/test_readonly_routers.py`:

```python
import pytest

from models.workspaces import Workspaces
from tests.conftest import USER_A_ID

READONLY_PREFIXES = [
    "/api/v1/entities/credit_ledger",
    "/api/v1/entities/search_jobs",
    "/api/v1/entities/workspace_members",
]


async def _seed_workspace(db_session):
    workspace = Workspaces(
        name="Acme", slug="acme", owner_id=USER_A_ID,
        plan="trial", subscription_status="trialing",
        monthly_credits=25, credits_used=0, max_seats=1,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


@pytest.mark.parametrize("prefix", READONLY_PREFIXES)
async def test_anonymous_is_rejected(anon_client, prefix):
    assert (await anon_client.get(prefix)).status_code == 401


@pytest.mark.parametrize("prefix", READONLY_PREFIXES)
async def test_create_is_forbidden(user_a_client, db_session, prefix):
    await _seed_workspace(db_session)
    response = await user_a_client.post(prefix, json={})
    assert response.status_code in (403, 422)


@pytest.mark.parametrize("prefix", READONLY_PREFIXES)
async def test_delete_is_forbidden(user_a_client, db_session, prefix):
    await _seed_workspace(db_session)
    assert (await user_a_client.delete(f"{prefix}/1")).status_code == 403
```

`422` is accepted on create because FastAPI validates the empty body before the handler runs; either rejection is correct.

- [ ] **Step 2: Run to confirm failure**

```bash
cd app/backend && python3 -m pytest tests/test_readonly_routers.py -v
```

Expected: FAIL — all currently return 200/201.

- [ ] **Step 3: Apply to each of the three routers**

In each file, add these imports:

```python
from dependencies.auth import get_current_user
from dependencies.tenancy import get_current_workspace
from models.workspaces import Workspaces
from schemas.auth import UserResponse
```

Replace the **GET ""** route body's service call so it is workspace-scoped (shown for `credit_ledger`; use the matching service class name in the other two):

```python
@router.get("", response_model=Credit_ledgerListResponse)
async def query_credit_ledgers(
    query: str = Query(None),
    sort: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=2000),
    fields: str = Query(None),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Credit_ledgerService(db)
    query_dict = {}
    if query:
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
    query_dict["workspace_id"] = workspace.id
    return await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)
```

Replace **GET "/{id}"**:

```python
@router.get("/{id}", response_model=Credit_ledgerResponse)
async def get_credit_ledger(
    id: int,
    fields: str = Query(None),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Credit_ledgerService(db)
    result = await service.get_by_id(id)
    if not result or result.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    return result
```

Replace **all six mutating routes** (`POST ""`, `POST /batch`, `PUT /{id}`, `PUT /batch`, `DELETE /{id}`, `DELETE /batch`) with a 403. Keep each function's original name, decorator and request-body parameter so the OpenAPI schema stays valid; replace only the body:

```python
    raise HTTPException(
        status_code=403,
        detail="This resource is read-only; records are created by the server",
    )
```

Also add `current_user: UserResponse = Depends(get_current_user)` to each of those six so anonymous callers get 401 before reaching the 403.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd app/backend && python3 -m pytest tests/test_readonly_routers.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add app/backend/routers/credit_ledger.py app/backend/routers/search_jobs.py app/backend/routers/workspace_members.py app/backend/tests/test_readonly_routers.py
git commit -m "fix(security): make credit_ledger, search_jobs, workspace_members read-only

Unauthenticated POST to credit_ledger allowed minting credit rows."
```

---

## Task 6: Secure `provider_connections` and `offer_profiles`

**Files:**
- Modify: `app/backend/routers/provider_connections.py`, `app/backend/routers/offer_profiles.py`
- Test: `app/backend/tests/test_write_allowlist.py` (extend)

**Interfaces:**
- Consumes: `EntityPolicy`, `filter_writes`, `get_current_workspace` (Task 3).
- Produces: nothing consumed later.

- [ ] **Step 1: Write the failing test**

Append to `app/backend/tests/test_write_allowlist.py`:

```python
from models.provider_connections import Provider_connections


async def test_config_json_is_never_returned(user_a_client, db_session):
    workspace = await _seed_workspace(db_session)
    connection = Provider_connections(
        workspace_id=workspace.id,
        provider_type="discovery",
        provider_name="mapbox",
        status="connected",
        config_json='{"token": "secret-value"}',
    )
    db_session.add(connection)
    await db_session.commit()
    await db_session.refresh(connection)

    listed = await user_a_client.get("/api/v1/entities/provider_connections")
    assert listed.status_code == 200
    assert "secret-value" not in listed.text

    fetched = await user_a_client.get(f"/api/v1/entities/provider_connections/{connection.id}")
    assert fetched.status_code == 200
    assert "secret-value" not in fetched.text
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd app/backend && python3 -m pytest tests/test_write_allowlist.py -k config_json -v
```

Expected: FAIL — `secret-value` appears in the response body.

- [ ] **Step 3: Secure `provider_connections`**

Add to `app/backend/routers/provider_connections.py`:

```python
from dependencies.auth import get_current_user
from dependencies.tenancy import EntityPolicy, filter_writes, get_current_workspace
from models.provider_connections import Provider_connections
from models.workspaces import Workspaces
from schemas.auth import UserResponse

PROVIDER_CONNECTIONS_POLICY = EntityPolicy(
    model=Provider_connections,
    scope="workspace",
    writable=frozenset({"provider_type", "provider_name", "config_json"}),
    never_return=frozenset({"config_json"}),
)
```

Remove `config_json` from the **response** model so it can never be serialised. In the `Provider_connectionsResponse` class, delete the `config_json` field entirely. This is stronger than filtering at runtime — Pydantic simply has nowhere to put it.

Rewrite the five surviving non-batch routes:

```python
@router.get("", response_model=Provider_connectionsListResponse)
async def query_provider_connectionss(
    query: str = Query(None),
    sort: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=2000),
    fields: str = Query(None),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    query_dict = {}
    if query:
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
    query_dict["workspace_id"] = workspace.id
    return await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)


@router.get("/{id}", response_model=Provider_connectionsResponse)
async def get_provider_connections(
    id: int,
    fields: str = Query(None),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    result = await service.get_by_id(id)
    if not result or result.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.post("", response_model=Provider_connectionsResponse, status_code=201)
async def create_provider_connections(
    data: Provider_connectionsData,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    payload = filter_writes(data.model_dump(), PROVIDER_CONNECTIONS_POLICY, strict=False)
    payload["workspace_id"] = workspace.id
    result = await service.create(payload)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create provider connection")
    return result


@router.put("/{id}", response_model=Provider_connectionsResponse)
async def update_provider_connections(
    id: int,
    data: Provider_connectionsUpdateData,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")

    update_dict = filter_writes(data.model_dump(), PROVIDER_CONNECTIONS_POLICY, strict=True)
    if not update_dict:
        return existing
    return await service.update(id, update_dict)


@router.delete("/{id}")
async def delete_provider_connections(
    id: int,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Provider_connectionsService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    await service.delete(id)
    return {"message": "Provider connection deleted", "id": id}
```

Block `POST /batch`, `PUT /batch` and `DELETE /batch` by replacing each body with:

```python
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on provider connections")
```

Add `current_user: UserResponse = Depends(get_current_user)` to those three so anonymous callers get 401 first.

- [ ] **Step 4: Secure `offer_profiles`**

`offer_profiles` is genuinely user-owned, so every field stays writable. Add:

```python
from dependencies.auth import get_current_user
from dependencies.tenancy import get_current_workspace
from models.workspaces import Workspaces
from schemas.auth import UserResponse
```

Every field stays writable, so no `filter_writes` call is needed — only scoping. Rewrite the five non-batch routes:

```python
@router.get("", response_model=Offer_profilesListResponse)
async def query_offer_profiless(
    query: str = Query(None),
    sort: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=2000),
    fields: str = Query(None),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    query_dict = {}
    if query:
        try:
            query_dict = json.loads(query)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid query JSON format")
    query_dict["workspace_id"] = workspace.id
    return await service.get_list(skip=skip, limit=limit, query_dict=query_dict, sort=sort)


@router.get("/{id}", response_model=Offer_profilesResponse)
async def get_offer_profiles(
    id: int,
    fields: str = Query(None),
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    result = await service.get_by_id(id)
    if not result or result.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    return result


@router.post("", response_model=Offer_profilesResponse, status_code=201)
async def create_offer_profiles(
    data: Offer_profilesData,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    payload = data.model_dump()
    payload["workspace_id"] = workspace.id
    result = await service.create(payload)
    if not result:
        raise HTTPException(status_code=400, detail="Failed to create offer profile")
    return result


@router.put("/{id}", response_model=Offer_profilesResponse)
async def update_offer_profiles(
    id: int,
    data: Offer_profilesUpdateData,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")

    update_dict = {k: v for k, v in data.model_dump().items() if v is not None and k != "workspace_id"}
    if not update_dict:
        return existing
    return await service.update(id, update_dict)


@router.delete("/{id}")
async def delete_offer_profiles(
    id: int,
    workspace: Workspaces = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    service = Offer_profilesService(db)
    existing = await service.get_by_id(id)
    if not existing or existing.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Not found")
    await service.delete(id)
    return {"message": "Offer profile deleted", "id": id}
```

`workspace_id` is stripped from the update payload so a client cannot move its offer profile into another workspace.

Block the three `/batch` routes by replacing each body with:

```python
    raise HTTPException(status_code=403, detail="Batch operations are not permitted on offer profiles")
```

Add `current_user: UserResponse = Depends(get_current_user)` to those three.

- [ ] **Step 5: Run the full suite**

```bash
cd app/backend && python3 -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/backend/routers/provider_connections.py app/backend/routers/offer_profiles.py app/backend/tests/test_write_allowlist.py
git commit -m "fix(security): scope provider_connections and offer_profiles

config_json removed from the response model — provider credentials are
write-only and can no longer be read back by any client."
```

---

## Task 7: Cross-tenant isolation tests

No production code changes — this proves Tasks 4-6 actually hold.

**Files:**
- Test: `app/backend/tests/test_tenant_isolation.py`

**Interfaces:**
- Consumes: `user_a_client`, `user_b_client`, `USER_A_ID`, `USER_B_ID` (Task 1).

- [ ] **Step 1: Write the test**

Create `app/backend/tests/test_tenant_isolation.py`:

```python
from models.leads import Leads
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID, USER_B_ID


async def _seed_lead(db_session, owner_id):
    lead = Leads(
        user_id=owner_id, business_name="Acme Cafe", category="Cafe",
        location="Leeds", country="United Kingdom",
        contact_email="owner@acme.test", contact_phone="+44 113 000 0000",
    )
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


async def test_user_b_cannot_read_user_a_lead(user_a_client, user_b_client, db_session):
    lead = await _seed_lead(db_session, USER_A_ID)

    mine = await user_a_client.get(f"/api/v1/entities/leads/{lead.id}")
    assert mine.status_code == 200

    theirs = await user_b_client.get(f"/api/v1/entities/leads/{lead.id}")
    assert theirs.status_code == 404
    assert "owner@acme.test" not in theirs.text


async def test_user_b_cannot_update_user_a_lead(user_b_client, db_session):
    lead = await _seed_lead(db_session, USER_A_ID)
    response = await user_b_client.put(
        f"/api/v1/entities/leads/{lead.id}", json={"business_name": "Hijacked"}
    )
    assert response.status_code == 404


async def test_user_b_cannot_delete_user_a_lead(user_b_client, db_session):
    lead = await _seed_lead(db_session, USER_A_ID)
    assert (await user_b_client.delete(f"/api/v1/entities/leads/{lead.id}")).status_code == 404


async def test_lead_list_excludes_other_tenants(user_a_client, user_b_client, db_session):
    await _seed_lead(db_session, USER_A_ID)
    await _seed_lead(db_session, USER_B_ID)

    listed = await user_a_client.get("/api/v1/entities/leads")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert all(item["user_id"] == USER_A_ID for item in items)


async def test_user_b_cannot_read_user_a_workspace(user_a_client, user_b_client, db_session):
    workspace = Workspaces(
        name="A Corp", slug="acorp", owner_id=USER_A_ID,
        plan="agency", subscription_status="active",
        monthly_credits=5000, credits_used=0, max_seats=10,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)

    assert (await user_b_client.get(f"/api/v1/entities/workspaces/{workspace.id}")).status_code == 404
```

- [ ] **Step 2: Run it**

```bash
cd app/backend && python3 -m pytest tests/test_tenant_isolation.py -v
```

Expected: 5 passed. If any fail, the corresponding router from Tasks 4-6 is incorrectly scoped — fix that router rather than the test.

- [ ] **Step 3: Commit**

```bash
git add app/backend/tests/test_tenant_isolation.py
git commit -m "test: prove cross-tenant reads and writes return 404"
```

---

## Task 8: Lock CORS and authenticate aihub

**Files:**
- Modify: `app/backend/main.py:92-99`
- Modify: `app/backend/routers/aihub.py`
- Test: `app/backend/tests/test_route_auth.py` (extend)

**Interfaces:**
- Consumes: `anon_client` (Task 1).
- Produces: `ALLOWED_ORIGINS` env var contract, referenced in the handoff.

- [ ] **Step 1: Write the failing test**

Append to `app/backend/tests/test_route_auth.py`:

```python
AIHUB_ROUTES = [
    "/api/v1/aihub/gentxt",
    "/api/v1/aihub/genimg",
    "/api/v1/aihub/genvideo",
    "/api/v1/aihub/genaudio",
    "/api/v1/aihub/transcribe",
    "/api/v1/aihub/analyzepdf",
]


@pytest.mark.parametrize("path", AIHUB_ROUTES)
async def test_aihub_requires_authentication(anon_client, path):
    response = await anon_client.post(path, json={})
    assert response.status_code == 401, f"{path} is callable anonymously"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd app/backend && python3 -m pytest tests/test_route_auth.py -k aihub -v
```

Expected: FAIL — returns 422 or 500, not 401.

- [ ] **Step 3: Add auth to aihub**

In `app/backend/routers/aihub.py`, add the imports:

```python
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
```

Add this parameter to each of the six route functions:

```python
    current_user: UserResponse = Depends(get_current_user),
```

Internal callers construct `AIHubService()` directly as a Python object rather than calling over HTTP, so nothing internal breaks.

- [ ] **Step 4: Replace the CORS configuration**

In `app/backend/main.py`, replace lines 92-99:

```python
# MODULE_MIDDLEWARE_START
_default_origins = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
_allowed_origins = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)
# MODULE_MIDDLEWARE_END
```

`os` is already imported at `main.py:3`.

**Deployment note for the handoff:** `ALLOWED_ORIGINS` must contain the deployed frontend origin or the app breaks in production. This is the single riskiest line in the plan.

- [ ] **Step 5: Run the full suite**

```bash
cd app/backend && python3 -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/backend/main.py app/backend/routers/aihub.py app/backend/tests/test_route_auth.py
git commit -m "fix(security): restrict CORS to an allowlist and authenticate aihub

allow_origin_regex='.*' with allow_credentials=True let any origin make
credentialed calls. aihub generation endpoints were open cost exposure."
```

---

## Task 9: Harden verify-payment

**Files:**
- Modify: `app/backend/routers/payments.py:268-335`
- Test: `app/backend/tests/test_billing.py`

**Interfaces:**
- Consumes: `ensure_workspace_for_user` (Task 3).
- Produces: a `Credit_ledger` row per applied checkout, keyed `reference_id == session.id`.

- [ ] **Step 1: Write the failing tests**

Create `app/backend/tests/test_billing.py`:

```python
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import routers.payments as payments
from models.credit_ledger import Credit_ledger
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID


def _fake_session(user_id, session_id="cs_test_1", status="complete", payment_status="paid"):
    return SimpleNamespace(
        id=session_id, status=status, payment_status=payment_status,
        customer="cus_1", subscription="sub_1",
        metadata={"user_id": user_id, "plan": "solo"},
    )


@pytest.fixture(autouse=True)
def _stripe_configured(monkeypatch):
    monkeypatch.setattr(payments.stripe, "api_key", "sk_test_dummy", raising=False)


async def _seed_workspace(db_session):
    workspace = Workspaces(
        name="Acme", slug="acme", owner_id=USER_A_ID,
        plan="trial", subscription_status="trialing",
        monthly_credits=25, credits_used=20, max_seats=1,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


async def test_foreign_session_is_rejected(user_a_client, db_session, monkeypatch):
    await _seed_workspace(db_session)
    monkeypatch.setattr(
        payments.stripe.checkout.Session, "retrieve",
        lambda session_id: _fake_session("someone-else"),
    )
    response = await user_a_client.post("/api/v1/billing/verify-payment", json={"session_id": "cs_test_1"})
    assert response.status_code == 403


async def test_unpaid_session_is_rejected(user_a_client, db_session, monkeypatch):
    await _seed_workspace(db_session)
    monkeypatch.setattr(
        payments.stripe.checkout.Session, "retrieve",
        lambda session_id: _fake_session(USER_A_ID, payment_status="unpaid"),
    )
    response = await user_a_client.post("/api/v1/billing/verify-payment", json={"session_id": "cs_test_1"})
    assert response.status_code != 200 or response.json()["status"] != "active"


async def test_replay_does_not_reset_credits(user_a_client, db_session, monkeypatch):
    workspace = await _seed_workspace(db_session)
    monkeypatch.setattr(
        payments.stripe.checkout.Session, "retrieve",
        lambda session_id: _fake_session(USER_A_ID),
    )

    first = await user_a_client.post("/api/v1/billing/verify-payment", json={"session_id": "cs_test_1"})
    assert first.status_code == 200

    # Burn credits, then replay the same session.
    refreshed = (await db_session.execute(
        select(Workspaces).where(Workspaces.id == workspace.id)
    )).scalar_one()
    refreshed.credits_used = 250
    await db_session.commit()

    second = await user_a_client.post("/api/v1/billing/verify-payment", json={"session_id": "cs_test_1"})
    assert second.status_code == 200

    final = (await db_session.execute(
        select(Workspaces).where(Workspaces.id == workspace.id)
    )).scalar_one()
    await db_session.refresh(final)
    assert final.credits_used == 250, "replay reset credit usage"

    ledger_rows = (await db_session.execute(
        select(Credit_ledger).where(Credit_ledger.reference_id == "cs_test_1")
    )).scalars().all()
    assert len(ledger_rows) == 1, "replay created a duplicate ledger row"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd app/backend && python3 -m pytest tests/test_billing.py -v
```

Expected: FAIL — the foreign session is accepted and the replay resets `credits_used` to 0.

- [ ] **Step 3: Rewrite the handler**

Replace the body of `verify_payment` in `app/backend/routers/payments.py` (currently lines 268-335) with:

```python
@router.post("/verify-payment")
async def verify_payment(
    data: VerifyPaymentRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify a completed checkout and activate the subscription.

    Guards, in order: the session must belong to the caller, must be paid, and
    must not have been applied before. Without the last guard a single purchase
    could be replayed to reset credit usage indefinitely.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payment service is not configured. Please contact support.")

    if not data.session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    try:
        session = stripe.checkout.Session.retrieve(data.session_id)
    except StripeInvalidRequestError as e:
        logger.error(f"Invalid session_id: {e}")
        raise HTTPException(status_code=400, detail="Invalid checkout session")
    except Exception as e:
        logger.error(f"Stripe retrieval error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve payment session")

    metadata = session.metadata or {}
    if metadata.get("user_id") != current_user.id:
        logger.warning("Checkout session %s does not belong to the calling user", data.session_id)
        raise HTTPException(status_code=403, detail="This checkout session does not belong to your account")

    plan = metadata.get("plan", "solo")
    plan_info = PLANS.get(plan, PLANS["solo"])

    if session.status != "complete" or getattr(session, "payment_status", None) != "paid":
        return {"status": session.status or "pending", "plan": plan}

    workspace = await ensure_workspace_for_user(current_user, db)

    existing = await db.execute(
        select(Credit_ledger).where(Credit_ledger.reference_id == session.id)
    )
    if existing.scalar_one_or_none():
        # Already applied. Report current state; mutate nothing.
        return {
            "status": "active",
            "plan": workspace.plan,
            "plan_name": PLANS.get(workspace.plan, plan_info)["name"],
            "credits": workspace.monthly_credits,
            "already_applied": True,
        }

    workspace.plan = plan
    workspace.subscription_status = "active"
    workspace.monthly_credits = plan_info["credits"]
    workspace.max_seats = plan_info["seats"]
    workspace.stripe_customer_id = session.customer or ""
    workspace.stripe_subscription_id = session.subscription or ""
    workspace.credits_used = 0
    workspace.credits_reset_at = (datetime.utcnow() + timedelta(days=30)).isoformat()

    db.add(Credit_ledger(
        workspace_id=workspace.id,
        amount=plan_info["credits"],
        balance_after=plan_info["credits"],
        action="subscription_activated",
        description=f"{plan_info['name']} plan activated",
        reference_id=session.id,
        idempotency_key=session.id,
    ))

    await db.commit()

    return {
        "status": "active",
        "plan": plan,
        "plan_name": plan_info["name"],
        "credits": plan_info["credits"],
    }
```

Add to the imports at the top of `payments.py`:

```python
from dependencies.tenancy import ensure_workspace_for_user
```

`select`, `Credit_ledger`, `datetime` and `timedelta` are already imported at lines 6, 15 and 3.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd app/backend && python3 -m pytest tests/test_billing.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/backend/routers/payments.py app/backend/tests/test_billing.py
git commit -m "fix(billing): bind checkout sessions to the caller and make them single-use

Previously any session_id activated the caller's workspace, and replaying
a valid one reset credits_used to 0 for unlimited credits."
```

---

## Task 10: Harden discovery — provider gate, credit ordering, deep-pass cost

**Files:**
- Modify: `app/backend/routers/discover.py:50-250` and `:321-324`
- Test: `app/backend/tests/test_discovery.py`

**Interfaces:**
- Consumes: `ensure_workspace_for_user` (Task 3).
- Produces: response field `status` with values `complete`, `provider_unconfigured`, `no_matches`; error code `provider_unconfigured`. Task 14 consumes these.

- [ ] **Step 1: Write the failing tests**

Create `app/backend/tests/test_discovery.py`:

```python
import pytest
from sqlalchemy import select

import routers.discover as discover
import services.business_search as business_search
from models.workspaces import Workspaces
from tests.conftest import USER_A_ID


async def _seed_workspace(db_session, credits_used=0):
    workspace = Workspaces(
        name="Acme", slug="acme", owner_id=USER_A_ID,
        plan="solo", subscription_status="active",
        monthly_credits=300, credits_used=credits_used, max_seats=1,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


@pytest.fixture(autouse=True)
def _forbid_ai_discovery(monkeypatch):
    """Any call to the AI generator during discovery is a test failure."""
    async def _explode(*args, **kwargs):
        raise AssertionError("AI fabrication path was invoked")

    monkeypatch.setattr(business_search, "generate_search_results", _explode)
    monkeypatch.setattr(discover, "discover_businesses", _explode, raising=False)


async def test_unconfigured_provider_returns_setup_state(user_a_client, db_session, monkeypatch):
    workspace = await _seed_workspace(db_session)
    monkeypatch.setattr(discover, "is_mapbox_configured", lambda: False)

    response = await user_a_client.post("/api/v1/discover/run", json={"country": "United Kingdom"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "provider_unconfigured"
    assert body["results"] == []


async def test_unconfigured_provider_charges_no_credits(user_a_client, db_session, monkeypatch):
    workspace = await _seed_workspace(db_session)
    monkeypatch.setattr(discover, "is_mapbox_configured", lambda: False)

    await user_a_client.post("/api/v1/discover/run", json={"country": "United Kingdom"})

    refreshed = (await db_session.execute(
        select(Workspaces).where(Workspaces.id == workspace.id)
    )).scalar_one()
    await db_session.refresh(refreshed)
    assert refreshed.credits_used == 0


async def test_zero_matches_returns_no_matches_not_fabrication(user_a_client, db_session, monkeypatch):
    await _seed_workspace(db_session)
    monkeypatch.setattr(discover, "is_mapbox_configured", lambda: True)

    async def _empty(**kwargs):
        return []

    monkeypatch.setattr(discover, "search_places", _empty)

    response = await user_a_client.post("/api/v1/discover/run", json={"country": "United Kingdom"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_matches"
    assert body["results"] == []


async def test_deep_pass_costs_one_credit(user_a_client, db_session, monkeypatch):
    await _seed_workspace(db_session)
    monkeypatch.setattr(discover, "is_mapbox_configured", lambda: True)

    response = await user_a_client.post("/api/v1/discover/estimate", json={"pass_type": "deep"})
    assert response.status_code == 200
    assert response.json()["credit_cost"] == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd app/backend && python3 -m pytest tests/test_discovery.py -v
```

Expected: FAIL — an unconfigured provider falls through to the AI path (raising the assertion), credits are deducted before the provider check, and deep costs 3.

- [ ] **Step 3: Replace the credit-cost helper and estimate route**

In `app/backend/routers/discover.py`, add near the top after the imports:

```python
# Both passes currently perform identical work: audit_website is imported but
# never invoked. Charging 3 for the deep pass was billing users for an audit
# that does not run. Restore the differential when the deep pass does more.
CREDIT_COST_PER_PASS = {"quick": 1, "deep": 1}


def credit_cost_for(pass_type: str) -> int:
    return CREDIT_COST_PER_PASS.get(pass_type, 1)
```

In `estimate_search`, replace line 68:

```python
    credit_cost = credit_cost_for(data.pass_type)
```

and replace the `providers_used` block (lines 72-74) with:

```python
    providers_used = ["MapBox Places"] if is_mapbox_configured() else []
```

Add `"provider_configured": is_mapbox_configured(),` to the returned dict.

- [ ] **Step 4: Rewrite `run_discovery`**

Replace the body of `run_discovery` (lines 88-250) with:

```python
@router.post("/run")
async def run_discovery(
    data: DiscoverRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run a discovery search.

    The provider check happens before any job row or credit deduction, so an
    unconfigured provider costs the user nothing. There is deliberately no AI
    fallback: fabricated businesses must never be returned as live results.
    """
    workspace = await ensure_workspace_for_user(current_user, db)

    if not is_mapbox_configured():
        return {
            "status": "provider_unconfigured",
            "error": "provider_unconfigured",
            "message": "No discovery provider is connected. Add a MapBox access token in Settings to run searches.",
            "provider": "mapbox",
            "results": [],
            "total_results": 0,
            "credits_charged": 0,
            "credits_remaining": workspace.monthly_credits - workspace.credits_used,
        }

    credit_cost = credit_cost_for(data.pass_type)
    credits_remaining = workspace.monthly_credits - workspace.credits_used

    if credits_remaining < credit_cost:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "insufficient_credits",
                "message": f"This search requires {credit_cost} credit(s). You have {credits_remaining} remaining.",
                "credits_remaining": credits_remaining,
                "credits_required": credit_cost,
                "upgrade_url": "/app/settings/billing",
            },
        )

    job = Search_jobs(
        user_id=current_user.id,
        workspace_id=workspace.id,
        status="running",
        filters_json=json.dumps(data.dict()),
        credits_estimated=credit_cost,
        credits_charged=0,
        results_count=0,
        progress_pct=10,
        started_at=datetime.utcnow().isoformat(),
    )
    db.add(job)
    workspace.credits_used += credit_cost
    await db.commit()
    await db.refresh(job)
    await db.refresh(workspace)
    job_id = job.id
    credits_left = workspace.monthly_credits - workspace.credits_used

    try:
        raw_results = await search_places(
            query=data.query or "",
            location=data.city or data.region or "",
            category=data.category,
            country=data.country,
            limit=data.limit,
        )

        scored_results = []
        for biz in raw_results:
            score_data = build_score_breakdown(biz)
            biz["scores"] = score_data["scores"]
            biz["priority_score"] = score_data["priority_score"]
            biz["score_breakdown"] = score_data["breakdowns"]
            biz["website_state"] = score_data["website_state"]
            biz["score_version"] = score_data["score_version"]
            biz["risk_reasons"] = score_data.get("risk_reasons", [])
            biz["data_source"] = "provider"
            scored_results.append(biz)

        scored_results.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

        result = await db.execute(select(Search_jobs).where(Search_jobs.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            job.status = "complete"
            job.results_count = len(scored_results)
            job.progress_pct = 100
            job.credits_charged = credit_cost
            job.completed_at = datetime.utcnow().isoformat()
            await db.commit()

        return {
            "job_id": job_id,
            "status": "complete" if scored_results else "no_matches",
            "results": scored_results,
            "total_results": len(scored_results),
            "credits_charged": credit_cost,
            "credits_remaining": credits_left,
            "pass_type": data.pass_type,
            "score_version": "1.0.0",
            "data_source": "mapbox",
        }

    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        result = await db.execute(select(Search_jobs).where(Search_jobs.id == job_id))
        job = result.scalar_one_or_none()
        if job:
            job.status = "failed"
            job.error_message = str(e)[:500]
            job.progress_pct = 0

        ws_result = await db.execute(select(Workspaces).where(Workspaces.id == workspace.id))
        ws = ws_result.scalar_one_or_none()
        if ws:
            ws.credits_used = max(0, ws.credits_used - credit_cost)

        await db.commit()

        raise HTTPException(
            status_code=500,
            detail={
                "error": "discovery_failed",
                "message": "Discovery search failed. Credits have been refunded.",
                "job_id": job_id,
            },
        )
```

Two bugs fixed incidentally: the original `await db.rollback()` after commit left `workspace` expired, so reading `workspace.credits_used` afterwards risked a `MissingGreenlet` error. Credits are now captured into `credits_left` while the object is live.

Update the imports at the top — remove `discover_businesses` and the unused `audit_website`:

```python
from dependencies.tenancy import ensure_workspace_for_user
from services.mapbox_places import is_mapbox_configured, search_places
from services.pagespeed import is_pagespeed_configured
from services.scoring import build_score_breakdown
```

- [ ] **Step 5: Fix the pass-type labels**

Replace the `pass_types` block at lines 321-324:

```python
        "pass_types": [
            {"value": "quick", "label": "Quick Discovery (1 credit)", "description": "Entity resolution and basic scoring"},
            {"value": "deep", "label": "Deep Analysis (1 credit)", "description": "Currently identical to Quick; website audits are not yet wired up"},
        ],
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd app/backend && python3 -m pytest tests/test_discovery.py -v
```

Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add app/backend/routers/discover.py app/backend/tests/test_discovery.py
git commit -m "fix(data): remove AI fabrication fallback from discovery

An unconfigured or empty provider silently returned LLM-invented business
names, addresses, phones and emails as live results. Also stops charging
3 credits for a deep pass that runs identical code to the 1-credit quick
pass, and fixes an expired-object read after rollback."
```

---

## Task 11: Delete the two remaining fabrication routes

**Files:**
- Modify: `app/backend/routers/search.py` (delete `POST /businesses`)
- Modify: `app/backend/routers/automation.py` (delete `POST /generate-leads`)
- Test: `app/backend/tests/test_route_auth.py` (extend)

**Interfaces:**
- Consumes: `user_a_client` (Task 1).

- [ ] **Step 1: Write the failing test**

Append to `app/backend/tests/test_route_auth.py`:

```python
FABRICATION_ROUTES = [
    "/api/v1/search/businesses",
    "/api/v1/automation/generate-leads",
]


@pytest.mark.parametrize("path", FABRICATION_ROUTES)
async def test_fabrication_routes_are_deleted(user_a_client, path):
    response = await user_a_client.post(path, json={})
    assert response.status_code == 404, f"{path} still generates fabricated businesses"
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd app/backend && python3 -m pytest tests/test_route_auth.py -k fabrication -v
```

Expected: FAIL.

- [ ] **Step 3: Delete the routes**

In `app/backend/routers/search.py`, delete the entire `@router.post("/businesses", ...)` function (starting line 53) and remove `generate_search_results` from the import on line 11. Keep `GET /filters` — it serves dropdown options and fabricates nothing.

In `app/backend/routers/automation.py`, delete the entire `@router.post("/generate-leads", ...)` function (starting line 107) along with its `GenerateLeadsRequest` and `GenerateLeadsResponse` schema classes.

- [ ] **Step 4: Verify nothing still imports the generator**

```bash
cd app/backend && grep -rn "generate_search_results\|discover_businesses" routers/ services/
```

Expected: matches only inside `services/business_search.py` itself (now unreferenced by any router). Leave the service file in place — deleting it is unnecessary churn, and it is now unreachable.

- [ ] **Step 5: Run the full suite**

```bash
cd app/backend && python3 -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/backend/routers/search.py app/backend/routers/automation.py app/backend/tests/test_route_auth.py
git commit -m "fix(data): delete the two remaining AI fabrication endpoints

/search/businesses returned invented businesses with no provider attempt.
/automation/generate-leads wrote them straight into the leads table."
```

---

## Task 12: Gate mock-data seeding

**Files:**
- Modify: `app/backend/main.py:70-74`

**Interfaces:** none.

- [ ] **Step 1: Change the lifespan**

In `app/backend/main.py`, replace the startup block:

```python
    # MODULE_STARTUP_START
    await initialize_database()
    if os.environ.get("SEED_MOCK_DATA", "").lower() in ("true", "1", "yes"):
        logger.info("SEED_MOCK_DATA is set; loading sample records")
        await initialize_mock_data()
    else:
        logger.info("Mock data seeding disabled (set SEED_MOCK_DATA=true to enable)")
    await initialize_admin_user()
    # MODULE_STARTUP_END
```

The import of `initialize_mock_data` at line 18 stays — the function is retained for local development, just no longer default-on.

- [ ] **Step 2: Verify the seed no longer runs by default**

```bash
cd app/backend && python3 -c "
import os, ast
src = open('main.py').read()
assert 'SEED_MOCK_DATA' in src, 'gate not added'
assert src.index('SEED_MOCK_DATA') < src.index('await initialize_mock_data()'), 'gate must precede the call'
print('mock seeding is gated')
"
```

- [ ] **Step 3: Run the full suite**

```bash
cd app/backend && python3 -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add app/backend/main.py
git commit -m "fix(data): stop seeding eight fake leads into every empty database

Seeding is now opt-in via SEED_MOCK_DATA=true."
```

---

## Task 13: Add `data_source` provenance to leads

**Files:**
- Modify: `app/backend/models/leads.py`
- Modify: `app/backend/routers/leads.py` (schemas)
- Create: `app/backend/alembic/versions/c7d1e2f3a4b5_add_leads_data_source.py`
- Modify: `app/frontend/src/pages/app/Discover.tsx:172-189`
- Test: `app/backend/tests/test_data_source.py`

**Interfaces:**
- Consumes: `user_a_client` (Task 1).
- Produces: `Leads.data_source` column and the `data_source` field on `LeadsData` / `LeadsUpdateData` / `LeadsResponse`. Task 15 renders it.

- [ ] **Step 1: Write the failing test**

Create `app/backend/tests/test_data_source.py`:

```python
from tests.conftest import USER_A_ID


async def test_lead_can_be_created_with_data_source(user_a_client):
    response = await user_a_client.post("/api/v1/entities/leads", json={
        "business_name": "Real Cafe", "category": "Cafe",
        "location": "Leeds", "country": "United Kingdom",
        "data_source": "provider",
    })
    assert response.status_code == 201
    assert response.json()["data_source"] == "provider"


async def test_data_source_defaults_to_null_when_absent(user_a_client):
    response = await user_a_client.post("/api/v1/entities/leads", json={
        "business_name": "Unknown Origin", "category": "Cafe",
        "location": "Leeds", "country": "United Kingdom",
    })
    assert response.status_code == 201
    assert response.json()["data_source"] is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd app/backend && python3 -m pytest tests/test_data_source.py -v
```

Expected: FAIL — `data_source` is not a field.

- [ ] **Step 3: Add the column to the model**

In `app/backend/models/leads.py`, add after the `last_contacted` column:

```python
    # Provenance. NULL means unknown — deliberately not defaulted, because an
    # unknown origin must stay distinguishable from a verified one.
    data_source = Column(String, nullable=True)
```

- [ ] **Step 4: Add the field to the router schemas**

In `app/backend/routers/leads.py`, add to `LeadsData`, `LeadsUpdateData` and `LeadsResponse`:

```python
    data_source: Optional[str] = None
```

In `LeadsData` it replaces nothing; add it as the final field of each class.

- [ ] **Step 5: Write the migration**

Create `app/backend/alembic/versions/c7d1e2f3a4b5_add_leads_data_source.py`:

```python
"""add data_source to leads

Revision ID: c7d1e2f3a4b5
Revises: b1f0ca7c0c08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d1e2f3a4b5"
down_revision: Union[str, Sequence[str], None] = "b1f0ca7c0c08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The eight records seeded from backend/mock_data/leads.json. They share a
# numeric user_id, whereas real users carry a UUID platform sub, so the match
# is unambiguous. Matching on both columns guards against a real business
# happening to share a name.
MOCK_USER_ID = "1466317"
MOCK_BUSINESS_NAMES = (
    "Mario's Pizzeria",
    "Chen's Auto Repair",
    "Bloom & Petal Florist",
    "Café del Sol",
    "Tanaka Dental Clinic",
    "Silva Construction",
    "Nordic Bakery",
    "Patel Electronics",
)


def upgrade() -> None:
    op.add_column("leads", sa.Column("data_source", sa.String(), nullable=True))

    leads = sa.table("leads", sa.column("data_source", sa.String), sa.column("user_id", sa.String), sa.column("business_name", sa.String))
    op.execute(
        leads.update()
        .where(sa.and_(
            leads.c.user_id == MOCK_USER_ID,
            leads.c.business_name.in_(MOCK_BUSINESS_NAMES),
        ))
        .values(data_source="mock")
    )
    # Every other pre-existing row stays NULL. Their provenance genuinely
    # cannot be reconstructed, and guessing would defeat the point.


def downgrade() -> None:
    op.drop_column("leads", "data_source")
```

- [ ] **Step 6: Pass the source through from Discover**

In `app/frontend/src/pages/app/Discover.tsx`, inside `saveAsLead`'s `data` object (line 173-189), add after `last_contacted: ''`:

```typescript
          data_source: biz.data_source || 'provider',
```

Add `data_source?: string;` to the `BusinessResult` type declaration.

- [ ] **Step 7: Run tests to verify they pass**

```bash
cd app/backend && python3 -m pytest tests/test_data_source.py -v
```

Expected: 2 passed.

- [ ] **Step 8: Verify the migration against real Postgres**

The test suite builds tables from `Base.metadata.create_all`, so it does **not** exercise this migration. Verify by hand before deploying:

```bash
cd app/backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
```

Expected: all three succeed with no error. Requires `DATABASE_URL` pointing at a real Postgres instance.

- [ ] **Step 9: Commit**

```bash
git add app/backend/models/leads.py app/backend/routers/leads.py app/backend/alembic/versions/ app/backend/tests/test_data_source.py app/frontend/src/pages/app/Discover.tsx
git commit -m "feat(data): add data_source provenance column to leads

Backfills the eight seeded sample rows as 'mock'. Pre-existing rows stay
NULL because their origin cannot be reconstructed."
```

---

## Task 14: Discover setup and empty states

**Files:**
- Modify: `app/frontend/src/pages/app/Discover.tsx`

**Interfaces:**
- Consumes: `status` values `provider_unconfigured` / `no_matches` from Task 10.

- [ ] **Step 1: Handle the new statuses in the search handler**

In `handleSearch` (line 126), replace the success block at lines 148-151:

```typescript
      const status = res.data?.status;
      setResults(res.data?.results || []);
      setDataSource(res.data?.data_source || '');

      if (status === 'provider_unconfigured') {
        setJobStatus('provider_unconfigured');
        toast.error(res.data?.message || 'No discovery provider is connected.');
      } else if (status === 'no_matches') {
        setJobStatus('no_matches');
        toast.info('No businesses matched those filters.');
      } else {
        setJobStatus('complete');
        toast.success(
          `Found ${res.data?.total_results || 0} businesses · ${res.data?.credits_charged || 0} credit(s) used`
        );
      }
```

- [ ] **Step 2: Render the two distinct states**

Immediately before the `{results.length > 0 && (` block (line 358), insert:

```tsx
        {jobStatus === 'provider_unconfigured' && (
          <Card className="border-amber-200 bg-amber-50/50">
            <CardHeader>
              <CardTitle className="text-base text-slate-900">No discovery provider connected</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-slate-600">
                Business discovery needs a connected data provider. Without one, BizLeads will not
                return results — it will never invent businesses to fill the gap.
              </p>
              <p className="text-sm text-slate-600">
                Add a MapBox access token to enable searching. No credits were charged.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="border-slate-200 cursor-pointer"
                onClick={() => navigate('/app/settings/workspace')}
              >
                Go to Settings
              </Button>
            </CardContent>
          </Card>
        )}

        {jobStatus === 'no_matches' && (
          <Card className="border-slate-200">
            <CardHeader>
              <CardTitle className="text-base text-slate-900">No businesses matched</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <p className="text-sm text-slate-600">
                The provider ran your search and returned nothing. Try widening it:
              </p>
              <ul className="text-sm text-slate-600 list-disc pl-5 space-y-1">
                <li>Remove the category filter, or pick a broader one</li>
                <li>Search a larger city or drop the city entirely</li>
                <li>Set Website State back to “All States”</li>
              </ul>
            </CardContent>
          </Card>
        )}
```

The visual distinction is deliberate: amber signals a configuration problem you must fix, slate signals a normal search outcome. Conflating them is what made the fabrication fallback seem reasonable.

- [ ] **Step 3: Fix the misleading source badge**

Replace the badge at line 372:

```tsx
                <Badge variant="outline" className="text-xs border-green-200 text-green-700 bg-green-50">
                  Source: MapBox Places
                </Badge>
```

Delete the dead `{filters?.google_places_connected && (...)}` block above it — the backend returns `mapbox_connected`, never `google_places_connected`, so it has never rendered.

- [ ] **Step 4: Ensure `navigate`, `CardHeader` and `CardTitle` are imported**

Confirm the top of the file imports them; add any that are missing:

```typescript
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
```

and inside the component: `const navigate = useNavigate();`

- [ ] **Step 5: Ensure error toasts are announced (spec §5)**

Errors must be announced to assistive technology, not merely rendered in red. The app uses `sonner` via `src/components/ui/sonner.tsx`, mounted in `App.tsx:56`. Check what it already provides:

```bash
cd app/frontend && grep -n "aria-live\|role=" src/components/ui/sonner.tsx
```

Sonner renders its own `aria-live` region by default. **If that grep returns a match, this step is already satisfied — change nothing and move on.** Only if it returns nothing, add the announcement to the `Toaster` in `src/components/ui/sonner.tsx`:

```tsx
      toastOptions={{
        classNames: {
          error: 'group-[.toaster]:border-red-200',
        },
      }}
      containerAriaLabel="Notifications"
```

Do not hand-roll a second live region if sonner already has one — two live regions announce every message twice, which is worse than none.

- [ ] **Step 6: Verify the build compiles**

```bash
cd app/frontend && pnpm install && pnpm run build
```

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add app/frontend/src/pages/app/Discover.tsx
git commit -m "feat(ui): distinguish provider-unconfigured from zero-match states

Also removes a source badge that reported 'AI Discovery' for real provider
results and a dead google_places_connected branch."
```

---

## Task 15: Provenance badge on leads

**Files:**
- Modify: `app/frontend/src/pages/app/Leads.tsx`
- Modify: `app/frontend/src/pages/app/LeadDetail.tsx`

**Interfaces:**
- Consumes: `Leads.data_source` from Task 13.

- [ ] **Step 1: Add the shared badge helper**

In `app/frontend/src/pages/app/Leads.tsx`, add near `stageBadgeClass` (line 40):

```typescript
const dataSourceBadge: Record<string, { label: string; className: string; title: string }> = {
  provider: {
    label: 'Verified source',
    className: 'bg-green-50 text-green-700 border-green-200',
    title: 'Sourced from a connected data provider.',
  },
  manual: {
    label: 'Added manually',
    className: 'bg-slate-50 text-slate-700 border-slate-200',
    title: 'Entered by a team member.',
  },
  ai_generated: {
    label: 'AI-generated — unverified',
    className: 'bg-red-50 text-red-700 border-red-200',
    title: 'Produced by an AI model. This business may not exist. Verify before contacting.',
  },
  mock: {
    label: 'Sample data',
    className: 'bg-slate-50 text-slate-400 border-slate-200',
    title: 'Seeded demo record, not a real business.',
  },
};

const unverifiedBadge = {
  label: 'Unverified',
  className: 'bg-amber-50 text-amber-700 border-amber-200',
  title: 'Origin unknown — this lead predates provenance tracking. Verify before contacting.',
};

export function getDataSourceBadge(source?: string | null) {
  return (source && dataSourceBadge[source]) || unverifiedBadge;
}
```

Every entry carries a label as well as a colour, so colour is never the only signal.

- [ ] **Step 2: Render it in the leads table**

Add a header cell to the `TableRow` at line 160:

```tsx
                  <TableHead className="text-xs font-medium text-slate-600">Source</TableHead>
```

and a matching cell inside the row body, after the priority cell (around line 196):

```tsx
                    <TableCell>
                      {(() => {
                        const badge = getDataSourceBadge(lead.data_source);
                        return (
                          <Badge variant="outline" className={cn('text-xs', badge.className)} title={badge.title}>
                            {badge.label}
                          </Badge>
                        );
                      })()}
                    </TableCell>
```

Add `data_source?: string | null;` to the `Lead` type in this file.

- [ ] **Step 3: Render it on the lead detail page**

In `app/frontend/src/pages/app/LeadDetail.tsx`, import the helper and render the badge beside the business name in the header:

```tsx
import { getDataSourceBadge } from './Leads';
```

```tsx
{(() => {
  const badge = getDataSourceBadge(lead?.data_source);
  return (
    <Badge variant="outline" className={cn('text-xs', badge.className)} title={badge.title}>
      {badge.label}
    </Badge>
  );
})()}
```

Add `data_source?: string | null;` to the lead type in this file.

- [ ] **Step 4: Verify the build compiles**

```bash
cd app/frontend && pnpm run build
```

Expected: build succeeds.

- [ ] **Step 5: Run the whole backend suite one final time**

```bash
cd app/backend && python3 -m pytest tests/ -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/frontend/src/pages/app/Leads.tsx app/frontend/src/pages/app/LeadDetail.tsx
git commit -m "feat(ui): show data provenance badge on leads

Every lead now states where it came from, so a user knows whether a phone
number is provider-sourced or of unknown origin."
```

---

## Post-implementation handoff

Record these before deploying:

1. **`ALLOWED_ORIGINS`** must list the deployed frontend origin, comma-separated. The app breaks without it.
2. **`MAPBOX_ACCESS_TOKEN`** must be set or Discover legitimately returns the setup state for every search.
3. **`SEED_MOCK_DATA`** must remain unset in production.
4. **`ENVIRONMENT`** must not be `dev` — `main.py:158` returns full stack traces when it is.
5. Run `alembic upgrade head` against production Postgres (Task 13, Step 8).
6. **Still broken after this work**, per spec §2: no Stripe webhook, so cancelling in Stripe never revokes access. Tenancy is per-user, not per-workspace. Trials never expire. Seats are unenforced. Discovery is synchronous. No evidence persistence or deduplication. The webhook is the highest-priority next item.
