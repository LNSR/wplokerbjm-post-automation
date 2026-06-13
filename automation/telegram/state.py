from __future__ import annotations

import threading
import time
from collections.abc import Callable

from automation.models import TelegramChatCommandState, TelegramPostDirective


class BulkCommandStore:
    def __init__(
        self,
        *,
        ttl_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._monotonic = monotonic
        self._commands: dict[str, TelegramChatCommandState] = {}
        self._lock = threading.Lock()

    @staticmethod
    def chat_key(chat_id: int | str) -> str:
        return str(chat_id)

    def remember(
        self,
        chat_id: int | str,
        directive: TelegramPostDirective,
    ) -> None:
        with self._lock:
            self._commands[self.chat_key(chat_id)] = TelegramChatCommandState(
                directive=directive,
                expires_at=self._monotonic() + self._ttl_seconds,
            )

    def recall(
        self,
        chat_id: int | str,
    ) -> TelegramPostDirective | None:
        key = self.chat_key(chat_id)
        with self._lock:
            state = self._commands.get(key)
            if state is None:
                return None
            if state.expires_at < self._monotonic():
                self._commands.pop(key, None)
                return None
            return state.directive

    def effective(
        self,
        chat_id: int | str,
        directive: TelegramPostDirective | None,
    ) -> TelegramPostDirective | None:
        if directive is not None:
            self.remember(chat_id, directive)
            return directive
        return self.recall(chat_id)


class FallbackChainStore:
    """Stores per-chat OpenCode fallback chain override.

    The chain is a comma-separated string of
    ``provider:model:endpoint_style`` items, e.g.
    ``"go:kimi-k2.6:chat,go:qwen3.7-plus:messages"``.

    Persists until the bot restarts or the user clears it with
    ``/set_fallback_model default``.
    """

    def __init__(self) -> None:
        self._chains: dict[str, str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def chat_key(chat_id: int | str) -> str:
        return str(chat_id)

    def set_chain(self, chat_id: int | str, chain: str) -> None:
        with self._lock:
            self._chains[self.chat_key(chat_id)] = chain

    def get_chain(self, chat_id: int | str) -> str | None:
        with self._lock:
            return self._chains.get(self.chat_key(chat_id))

    def clear_chain(self, chat_id: int | str) -> None:
        with self._lock:
            self._chains.pop(self.chat_key(chat_id), None)


class ModelPreferenceStore:
    """Stores per-chat model alias selection.

    Persists until the bot restarts or the user changes it with
    /set_model.  No TTL -- the selection is sticky across messages.
    """

    def __init__(self) -> None:
        self._prefs: dict[str, str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def chat_key(chat_id: int | str) -> str:
        return str(chat_id)

    def set_model(self, chat_id: int | str, alias: str) -> None:
        with self._lock:
            self._prefs[self.chat_key(chat_id)] = alias

    def get_model(self, chat_id: int | str) -> str | None:
        with self._lock:
            return self._prefs.get(self.chat_key(chat_id))

    def clear_model(self, chat_id: int | str) -> None:
        with self._lock:
            self._prefs.pop(self.chat_key(chat_id), None)


class ProcessedMessageStore:
    """Remembers recently processed Telegram message IDs to skip webhook retries.

    TTL starts when the message is *marked*, not created, so the second
    webhook delivery has a generous window to be recognized as duplicate.
    """

    def __init__(
        self,
        *,
        ttl_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._monotonic = monotonic
        self._messages: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def message_key(chat_id: int | str, message_id: int) -> str:
        return f"{chat_id}:{message_id}"

    def mark_processed(self, chat_id: int | str, message_id: int) -> None:
        """Mark a message as processed.

        Subsequent ``is_processed`` calls return ``True`` until the TTL
        expires.
        """
        key = self.message_key(chat_id, message_id)
        with self._lock:
            self._messages[key] = self._monotonic() + self._ttl_seconds

    def is_processed(self, chat_id: int | str, message_id: int) -> bool:
        """Return ``True`` if the message was marked within the TTL window."""
        key = self.message_key(chat_id, message_id)
        with self._lock:
            expires_at = self._messages.get(key)
            if expires_at is None:
                return False
            if expires_at < self._monotonic():
                self._messages.pop(key, None)
                return False
            return True
