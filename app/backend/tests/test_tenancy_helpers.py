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
