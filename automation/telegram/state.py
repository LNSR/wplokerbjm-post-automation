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
