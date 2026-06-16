<!-- Context: project-intelligence/concepts | Priority: critical | Version: 1.0 | Updated: 2026-06-17 -->

# Concept: Technical Domain & TDD Patterns

**Purpose**: Tech stack, strong-typed architecture, TDD methodology, and code conventions for the WPLokerBJM automation pipeline.

**Last Updated**: 2026-06-17

---

## Core Idea

Python 3.14+ automation pipeline — AI flyer extraction → WordPress draft via Telegram bot. **Strict typing is non-negotiable**: every model, function, and test carries explicit type annotations. Pydantic `strict=True` + `extra="forbid"` on all models. **TDD-first**: 195 assertions across 13 test files covering 31 source modules (~1:2 test-to-source ratio). No untyped code merges.

---

## Strict Typing — Foundation

**Every module** starts with `from __future__ import annotations` for deferred evaluation. All function signatures are fully annotated with modern Python 3.10+ union syntax (`| None`, `list[str]`, `dict[str, Any]`).

**Base models** (`automation/models.py`) enforce strictness at the framework level:

```python
class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", validate_assignment=True)

class FrozenStrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
```

**Type choices** (imported from pydantic):
- `StrictStr` / `StrictInt` / `StrictFloat` / `StrictBool` — no coercion, never `"0"` → `0`
- `SecretStr` — never leaked to logs, explicit `.get_secret_value()` to unwrap
- `Literal["a", "b"]` — constrained unions, no magic strings
- `list[dict[StrictStr, StrictStr]]` — fully parameterized generics

**Field validators** are typed with `@field_validator` + `@classmethod`:

```python
@field_validator("wordpress_jwt", mode="before")
@classmethod
def validate_wordpress_jwt(cls, value: str | SecretStr) -> str:
    value = reveal_secret(value)
    if len(value) < 20 or value.count(".") != 2:
        raise ValueError("must look like a three-segment JWT")
    return value
```

**Cross-field validation** via `@model_validator(mode="after")` returns `Self` type.

**No untyped code allowed.** Every new function, parameter, return type, and variable must be annotated. This applies to tests too: `def test_...() -> None:`.

---

## Primary Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Runtime | Python 3.14+ | `from __future__ import annotations`, `| None`, `list[...]` |
| Pkg mgr | UV | Standard per `AGENTS.md` — no pip/poetry |
| Validation | Pydantic 2 + pydantic-settings | `strict=True`, `extra="forbid"`, `model_validator` |
| Config | `BaseSettings` → `.env` | dotenv + aliased env var names |
| Types | `StrictStr`, `StrictInt`, `SecretStr` | Zero-coercion policy |
| Testing | pytest 9.1+ | 106 tests, `MonkeyPatch`, autouse fixtures |
| AI | Gemini 2.5 Flash + OpenCode | Multi-model fallback chain |
| HTTP | httpx | WordPress REST + Telegram Bot API |

---

## TDD Methodology

**Coverage**: 31 source modules → 13 test files → 195 assertions → 106 tests (all passing).

**Test conventions**:
- `tests/test_{module}.py` mirrors `automation/{module}/`
- `conftest.py` with `autouse` fixture `clean_runtime_state` clears env → no leaks between tests
- `valid_env` fixture: complete test `RuntimeEnvironment`
- All test functions: `def test_...() -> None:` — typed return
- `pytest.MonkeyPatch` for env isolation, `unittest.mock.patch` for date/time

**Test structure per module** (TDD order):
1. **Happy path** — does it work with valid input?
2. **Negative cases** — rejects invalid input with correct error
3. **Edge cases** — boundaries, defaults, empty values, `None`
4. **Integration** — multi-step pipeline, cross-module flows

**Adding features** (strict TDD flow):
1. Write test → `uv run pytest -k test_new_feature` → FAIL (red)
2. Implement → `uv run pytest -k test_new_feature` → PASS (green)
3. Run full suite → `uv run pytest -v` → ALL 106+ must pass
4. No regressions tolerated — fix or revert

---

## Code Patterns

**Config pattern** — typed, validated, immutable:
```python
def env_value(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise AgentError(f"Missing: {name}")
    return value

def validate_runtime_environment(*, environ=None, require_public_url=True) -> RuntimeEnvironment:
    settings = RuntimeEnvironment()  # pydantic-settings auto-validates
    validate_skill_configuration()
    return settings
```

**Normalizer pattern** — defensive, traceable:
```python
def normalize_payload(payload: dict[str, Any], options: dict[str, Any], *, source=None) -> tuple[NormalizedPayload, list[str]]:
    # 1. Filter unknown fields → warnings
    # 2. Apply defaults (gender, status_pekerjaan, title suffix)
    # 3. Validate number types (INT_FIELDS)
    # 4. Normalize WYSIWYG (HTML cleanup, linkification)
    # 5. Match taxonomy terms against backend options
    # 6. Return validated model + warnings list
```

**Error handling** — safe, no secrets:
```python
class AgentError(RuntimeError):
    """Safe user-facing error. Never include secret values."""
```

**Module structure**: every package has `__init__.py`. Imports are absolute (`from automation.models import ...`), not relative.

---

## Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Files | snake_case | `test_payload_normalize.py`, `wordpress_auth.py` |
| Classes | PascalCase | `NormalizedPayload`, `BuildResult`, `AgentError` |
| Functions | snake_case | `normalize_payload()`, `env_value()` |
| Constants | UPPER_CASE | `TITLE_SUFFIX`, `CONTROLLED_TAXONOMIES`, `INT_FIELDS` |
| Test files | `test_` + module name | `test_payload_normalize.py` |
| Test functions | `test_` + scenario | `test_normalize_payload_requires_title()` |
| Private helpers | `_` prefix | `_deadline` in local scope |

---

## Project Structure

```
automation/
├── ai/           # AI extraction (Gemini + OpenCode chain)
├── payload/      # Payload validation & normalization
├── telegram/     # Telegram bot (handlers, server, state, webhook)
├── wordpress/    # WordPress REST + JWT auth
├── web/          # External enrichment (Exa)
├── config.py     # Env loader + RuntimeEnvironment validator
├── models.py     # All Pydantic models + AgentError
├── main.py       # CLI entry point + orchestrator
└── skills.py

tests/
├── conftest.py              # autouse env cleanup + valid_env fixture
├── test_ai_extractor.py
├── test_ai_prompt.py
├── test_config.py           # 16 tests — config validation
├── test_integrations_isolated.py
├── test_main.py
├── test_payload_normalize.py     # 20 tests — normalization (largest)
├── test_render_env_sync.py
├── test_telegram_*.py        # 7 Telegram-specific test files

.agents/skills/
├── job-copywriter/SKILL.md       # Flyer → MetaBox fields
└── agent-postdraft/SKILL.md      # POST to WordPress ingest
```

---

## 📂 Codebase References

**Models**: `automation/models.py` — `StrictModel`, `FrozenStrictModel`, `NormalizedPayload` (340 lines, all typed)
**Config**: `automation/config.py` — `validate_runtime_environment()`, `env_value()`
**Normalizer**: `automation/payload/normalize.py` — `normalize_payload()`, `normalize_title_case()`
**Tests**: `tests/test_payload_normalize.py` — 20 tests (best example of TDD patterns)
**Fixtures**: `tests/conftest.py` — `clean_runtime_state`, `valid_env`

---

## Related

- `wordpress-schema.md` — Data model for `lowongan` CPT
- `../lookup/api-contracts.md` — REST/GraphQL endpoints
- `../guides/automation-workflows.md` — Pipeline integration
- `../errors/common-errors.md` — Validation error patterns
