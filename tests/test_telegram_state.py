from __future__ import annotations

from automation.models import TelegramPostDirective
from automation.telegram.state import BulkCommandStore


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.value = start

    def now(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_remember_returns_directive_before_expiry() -> None:
    clock = FakeClock()
    store = BulkCommandStore(ttl_seconds=90, monotonic=clock.now)
    directive = TelegramPostDirective(
        instruction="Prioritize the QR application link.",
    )

    store.remember(123, directive)

    assert store.recall(123) == directive


def test_recall_clears_expired_command() -> None:
    clock = FakeClock()
    store = BulkCommandStore(ttl_seconds=90, monotonic=clock.now)
    store.remember(123, TelegramPostDirective())

    clock.advance(91)

    assert store.recall(123) is None


def test_effective_returns_explicit_directive_and_remembers_it() -> None:
    clock = FakeClock()
    store = BulkCommandStore(ttl_seconds=90, monotonic=clock.now)
    directive = TelegramPostDirective(instruction="Keep the title concise.")

    assert store.effective("chat-1", directive) == directive
    assert store.effective("chat-1", None) == directive
