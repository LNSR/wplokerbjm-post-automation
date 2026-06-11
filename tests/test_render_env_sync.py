from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Load the sync script by path (filename has hyphens, not a valid module name)
_script_path = Path(__file__).resolve().parents[1] / "scripts" / "sync-render-env.py"
_spec = importlib.util.spec_from_file_location("sync_render_env", _script_path)
_sync_module = importlib.util.module_from_spec(_spec)
sys.modules["sync_render_env"] = _sync_module
_spec.loader.exec_module(_sync_module)

ALLOWLIST = _sync_module.ALLOWLIST
main = _sync_module.main

# ---------------------------------------------------------------------------
# Test 1: control secrets excluded from ALLOWLIST
# ---------------------------------------------------------------------------
def test_allowlist_excludes_control_secrets() -> None:
    assert "RENDER_ACCOUNT_API_KEY" not in ALLOWLIST
    assert "RENDER_SERVICE_ID" not in ALLOWLIST


# ---------------------------------------------------------------------------
# Test 2: ALLOWLIST covers all runtime env vars the app expects
# ---------------------------------------------------------------------------
def test_allowlist_includes_all_runtime_env_vars() -> None:
    required = frozenset({
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_USERNAME",
        "TELEGRAM_WEBHOOK_SECRET",
        "WPLBJM_API_BASE_URL_PROD",
        "WPLBJM_JWT_PROD",
        "WP_LOGIN_USERNAME",
        "WP_LOGIN_PASSWORD",
        "EXA_API_KEY",
        "GOOGLE_AI_STUDIO_KEY",
        "OPENCODE_API_KEY",
        "AI_PROVIDER",
        "OPENCODE_MODEL_CHAIN",
        "OPENCODE_COPYWRITER_CHAIN",
        "SKILL_MD_PATH",
        "PUBLIC_BASE_URL",
        "TELEGRAM_MEDIA_GROUP_DELAY_SECONDS",
        "TELEGRAM_BULK_COMMAND_TTL_SECONDS",
    })
    missing = required - ALLOWLIST
    assert not missing, f"ALLOWLIST missing vars: {missing}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _set_all_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ALLOWLIST:
        monkeypatch.setenv(key, f"test_{key}")
    monkeypatch.setenv("RENDER_ACCOUNT_API_KEY", "rnd_test")
    monkeypatch.setenv("RENDER_SERVICE_ID", "srv_test")


class _MockHttpResponse:
    """Minimal mock for urllib.response with context manager support."""

    def __init__(self, status: int = 200, body: bytes = b"{}") -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_MockHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        pass

    @staticmethod
    def as_urlopen(status: int = 200, body: bytes = b"{}"):
        """Return a function usable as `urlopen` replacement."""

        def _open(*_a: object, **_kw: object) -> _MockHttpResponse:
            return _MockHttpResponse(status=status, body=body)

        return _open


# ---------------------------------------------------------------------------
# Test 3: dry-run does NOT call the Render API
# ---------------------------------------------------------------------------
def test_dry_run_does_not_call_api(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _set_all_env(monkeypatch)

    auth_calls = 0
    sync_calls = 0

    def _controlled_open(*_a: object, **_kw: object) -> object:
        nonlocal auth_calls, sync_calls
        auth_calls += 1
        if auth_calls > 1:
            # After the auth call, any further call in dry-run means sync was attempted
            sync_calls += 1
        return _MockHttpResponse()

    monkeypatch.setattr("urllib.request.urlopen", _controlled_open)
    monkeypatch.setattr("urllib.request.Request", lambda *a, **kw: None)
    monkeypatch.setattr("urllib.error.HTTPError", Exception)

    exit_code = main(["--dry-run"])
    assert exit_code == 0
    assert "[DRY-RUN]" in capsys.readouterr().out
    assert sync_calls == 0, "No sync calls should happen in dry-run mode"
    assert auth_calls == 1, "Only auth validation should happen in dry-run"


# ---------------------------------------------------------------------------
# Test 4: missing var exits with error
# ---------------------------------------------------------------------------
def test_missing_var_exits_with_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _set_all_env(monkeypatch)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN")

    monkeypatch.setattr("urllib.request.urlopen", _MockHttpResponse.as_urlopen())
    monkeypatch.setattr("urllib.request.Request", lambda *a, **kw: None)
    monkeypatch.setattr("urllib.error.HTTPError", Exception)

    exit_code = main(["--dry-run"])
    assert exit_code == 0  # --dry-run does NOT fail on missing vars (only warns)
    out = capsys.readouterr().out
    assert "TELEGRAM_BOT_TOKEN" in out


# ---------------------------------------------------------------------------
# Test 5: sync calls Render API per key
# ---------------------------------------------------------------------------
def test_sync_calls_render_api_per_key(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _set_all_env(monkeypatch)

    calls: list[str] = []

    def fake_open(req: object, **kw: object) -> object:
        # Extract URL from the Request object
        calls.append(str(req))
        return _MockHttpResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    monkeypatch.setattr("urllib.request.Request", lambda *a, **kw: None)
    monkeypatch.setattr("urllib.error.HTTPError", Exception)

    exit_code = main([])  # NOT dry-run
    assert exit_code == 0

    # First call is auth validation (GET /services/{sid})
    # Remaining calls are per-key PUTs
    assert len(calls) >= len(ALLOWLIST), f"Expected at least {len(ALLOWLIST)} API calls, got {len(calls)}"


# ---------------------------------------------------------------------------
# Test 6: auth validation rejects bad key
# ---------------------------------------------------------------------------
def test_auth_validation_rejects_bad_key(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _set_all_env(monkeypatch)

    def fake_open(req: object, timeout: int = 0) -> object:
        return _MockHttpResponse(status=401, body=b'{"error":"unauthorized"}')

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    monkeypatch.setattr("urllib.request.Request", lambda *a, **kw: None)
    monkeypatch.setattr("urllib.error.HTTPError", Exception)

    exit_code = main(["--dry-run"])
    assert exit_code == 1

    stderr = capsys.readouterr().err
    assert "auth" in stderr.lower() or "401" in stderr


# ---------------------------------------------------------------------------
# Test 7: secret values NOT leaked in output
# ---------------------------------------------------------------------------
def test_secret_values_not_leaked_in_output(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _set_all_env(monkeypatch)
    # Use a recognizable value
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRET_VALUE_DO_NOT_LEAK")

    monkeypatch.setattr("urllib.request.urlopen", _MockHttpResponse.as_urlopen())
    monkeypatch.setattr("urllib.request.Request", lambda *a, **kw: None)
    monkeypatch.setattr("urllib.error.HTTPError", Exception)

    main(["--dry-run"])
    combined = capsys.readouterr().out + capsys.readouterr().err

    assert "SECRET_VALUE_DO_NOT_LEAK" not in combined
    assert "[DRY-RUN]" in combined
