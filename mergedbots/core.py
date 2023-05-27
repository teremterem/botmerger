# pylint: disable=no-name-in-module
"""Core logic of MergedBots library."""
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, PrivateAttr

from .errors import BotHandleTakenError, BotNotFoundError
from .models import MergedBot, ObjectManager


class BotManager(BaseModel):
    """An abstract factory of everything else in this library."""

    object_manager: ObjectManager

    def create_bot(self, handle: str, name: str = None, **kwargs) -> MergedBot:
        """Create a merged bot."""
        if self.object_manager.get_bot(handle):
            raise BotHandleTakenError(f"bot with handle {handle!r} is already registered")

        if not name:
            name = handle
        bot = MergedBot(uuid=uuid4(), object_manager=self.object_manager, handle=handle, name=name, **kwargs)

        self.object_manager.register_bot(bot)
        return bot

    def find_bot(self, handle: str) -> MergedBot:
        """Fetch a bot by its handle."""
        bot = self.object_manager.get_bot(handle)
        if not bot:
            raise BotNotFoundError(f"bot with handle {handle!r} does not exist")
        return bot


class InMemoryObjectManager(ObjectManager):
    """An in-memory object manager."""

    _objects: dict[Any, Any] = PrivateAttr(default_factory=dict)

    def register_object(self, key: Any, value: Any) -> None:
        """Register an object."""
        self._objects[key] = value

    def get_object(self, key: Any) -> Any | None:
        """Get an object by its key."""
        return self._objects.get(key)
