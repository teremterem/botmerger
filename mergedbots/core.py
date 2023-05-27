# pylint: disable=no-name-in-module
"""Core logic of MergedBots library."""
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, UUID4, PrivateAttr

from .errors import BotHandleTakenError, BotNotFoundError, WrongMergedObjectError
from .models import MergedBot, MergedObject, ObjectManager


class BotManager(BaseModel):
    """An abstract factory of everything else in this library."""

    object_manager: ObjectManager

    def create_bot(self, handle: str, name: str = None, **kwargs) -> MergedBot:
        """Create a merged bot."""
        if self.object_manager.get_bot_uuid(handle):
            raise BotHandleTakenError(f"a bot with the handle {handle!r} is already registered")

        if not name:
            name = handle
        bot = MergedBot(uuid=uuid4(), handle=handle, name=name, **kwargs)

        self.object_manager.register_object(bot)
        self.object_manager.register_bot_handle(handle, bot.uuid)

        return bot

    def fetch_bot(self, handle: str) -> MergedBot:
        """Fetch a bot by its handle."""
        bot_uuid = self.object_manager.get_bot_uuid(handle)
        if not bot_uuid:
            raise BotNotFoundError(f"bot with handle {handle!r} does not exist")

        bot = self.object_manager.get_object(bot_uuid)
        if not isinstance(bot, MergedBot):
            raise WrongMergedObjectError(
                f"wrong type of object with uuid {bot_uuid!r} (expected MergedBot, got {type(bot).__name__})"
            )
        return bot


class InMemoryObjectManager(ObjectManager):
    """An in-memory object manager."""

    _objects: dict[UUID4, MergedObject] = PrivateAttr(default_factory=dict)
    _bot_handles_to_uuids: dict[str, UUID4] = PrivateAttr(default_factory=dict)

    def register_object(self, obj: MergedObject) -> None:
        """Register an object."""
        self._objects[obj.uuid] = obj

    def register_bot_handle(self, bot_handle: str, bot_uuid: UUID4) -> None:
        """Register a bot handle."""
        self._bot_handles_to_uuids[bot_handle] = bot_uuid

    def get_object(self, uuid: UUID4) -> Optional[MergedObject]:
        """Get an object by its uuid."""
        return self._objects.get(uuid)

    def get_bot_uuid(self, handle: str) -> Optional[UUID4]:
        """Get a bot's uuid by its handle."""
        return self._bot_handles_to_uuids.get(handle)
