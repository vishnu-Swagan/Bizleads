"""Interactive API docs must not be published in production.

They served a browsable map of all 70 endpoints — every path, request schema
and field name — to anonymous visitors. The endpoints themselves are
authenticated, so this was never a breach, but publishing the blueprint of an
API is a gift to anyone probing it, and it is not how a production service
presents itself.

Asserts the configured URLs rather than issuing requests: constructing the app
runs its lifespan (database connections, provider clients), which a test of
routing configuration has no business doing.
"""
import importlib

import pytest


def _app_for(monkeypatch, environment: str):
    """Rebuild the app under a given ENVIRONMENT — the flag is read at import."""
    monkeypatch.setenv("ENVIRONMENT", environment)
    import main
    return importlib.reload(main).app


@pytest.fixture(autouse=True)
def _restore_module(monkeypatch):
    """Leave `main` as the rest of the suite expects to find it."""
    yield
    monkeypatch.undo()
    import main
    importlib.reload(main)


def test_production_serves_no_docs(monkeypatch):
    app = _app_for(monkeypatch, "production")
    assert app.docs_url is None, "/docs is served in production"
    assert app.redoc_url is None, "/redoc is served in production"
    assert app.openapi_url is None, "/openapi.json is served in production"


def test_development_keeps_the_docs(monkeypatch):
    """Closing them in production must not cost developers the tooling."""
    app = _app_for(monkeypatch, "development")
    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"


def test_an_unset_environment_is_treated_as_development(monkeypatch):
    """Absent config must not silently publish docs in a real deployment...

    ...but it must also not break local work. Unset means development; the
    production deployment sets ENVIRONMENT explicitly (render.yaml).
    """
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    import main
    app = importlib.reload(main).app
    assert app.docs_url == "/docs"
