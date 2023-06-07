# pylint: disable=no-name-in-module
"""Implementations of BotMerger class."""
import asyncio
import logging
from abc import abstractmethod
from typing import Any

from pydantic import UUID4

from mergedbots.botmerger.base import BotMerger, MergedObject
from mergedbots.botmerger.errors import BotAliasTakenError, BotNotFoundError
from mergedbots.botmerger.models import MergedBot, MergedChannel, MergedUser

ObjectKey = UUID4 | tuple[Any, ...]

logger = logging.getLogger(__name__)


class BotMergerBase(BotMerger):
    """
    An abstract factory of everything else in this library. This class implements the common functionality of all
    concrete BotMerger implementations.
    """

    # TODO think about thread-safety ?

    def create_bot(self, alias: str, name: str = None, description: str = None, **kwargs) -> MergedBot:
        """
        Create a bot. This version of bot creation function is meant to be called outside an async context (for ex.
        as a decorator to `react` functions as they are being defined).
        """
        # TODO is this a dirty hack ? find a better way to do this ?
        # start a temporary event loop and call the async version of this method from there
        return asyncio.run(self.create_bot_async(alias=alias, name=name, description=description, **kwargs))

    async def create_bot_async(self, alias: str, name: str = None, description: str = None, **kwargs) -> MergedBot:
        """Create a bot while inside an async context."""
        if await self._get_bot(alias):
            raise BotAliasTakenError(f"bot with alias {alias!r} is already registered")

        if not name:
            name = alias
        bot = MergedBot(merger=self, alias=alias, name=name, description=description, **kwargs)

        await self._register_bot(bot)
        return bot

    async def find_bot(self, alias: str) -> MergedBot:
        """Fetch a bot by its alias."""
        bot = await self._get_bot(alias)
        if not bot:
            raise BotNotFoundError(f"bot with alias {alias!r} does not exist")
        return bot

    async def find_or_create_user_channel(
        self,
        channel_type: str,
        channel_id: Any,
        user_display_name: str,
        **kwargs,
    ) -> MergedChannel:
        """
        Find or create a channel with a user as its owner. Parameters `channel_type` and `channel_specific_id` are
        used to look up the channel. Parameter `user_display_name` is used to create a user if the channel does not
        exist and is ignored if the channel already exists.
        """
        key = self._generate_channel_key(channel_type=channel_type, channel_id=channel_id)

        channel = await self._get_object(key)
        self._assert_correct_obj_type_or_none(channel, MergedChannel, key)

        if not channel:
            user = MergedUser(merger=self, name=user_display_name, **kwargs)
            await self._register_merged_object(user)

            channel = MergedChannel(
                merger=self,
                channel_type=channel_type,
                channel_id=channel_id,
                owner=user,
            )
            await self._register_object(key, channel)
            await self._register_merged_object(user)

        return channel

    @abstractmethod
    async def _register_object(self, key: ObjectKey, value: Any) -> None:
        """Register an object."""

    @abstractmethod
    async def _get_object(self, key: ObjectKey) -> Any | None:
        """Get an object by its key."""

    async def _register_merged_object(self, obj: MergedObject) -> None:
        """Register a merged object."""
        await self._register_object(obj.uuid, obj)

    async def _get_merged_object(self, uuid: UUID4) -> MergedObject | None:
        """Get a merged object by its uuid."""
        obj = await self._get_object(uuid)
        self._assert_correct_obj_type_or_none(obj, MergedObject, uuid)
        return obj

    async def _register_bot(self, bot: MergedBot) -> None:
        """Register a bot."""
        await self._register_merged_object(bot)
        await self._register_object(self._generate_bot_key(bot.alias), bot)

    async def _get_bot(self, alias: str) -> MergedBot | None:
        """Get a bot by its alias."""
        key = self._generate_bot_key(alias)
        bot = await self._get_object(key)
        self._assert_correct_obj_type_or_none(bot, MergedBot, key)
        return bot

    # noinspection PyMethodMayBeStatic
    def _generate_bot_key(self, alias: str) -> tuple[str, str]:
        """Generate a key for a bot."""
        return "bot_by_alias", alias

    # noinspection PyMethodMayBeStatic
    def _generate_channel_key(self, channel_type: str, channel_id: Any) -> tuple[str, str, str]:
        """Generate a key for a channel."""
        return "channel_by_type_and_id", channel_type, channel_id

    # noinspection PyMethodMayBeStatic
    def _assert_correct_obj_type_or_none(self, obj: Any, expected_type: type, key: Any) -> None:
        """Assert that the object is of the expected type or None."""
        if obj and not isinstance(obj, expected_type):
            raise TypeError(
                f"wrong type of object by the key {key!r}: "
                f"expected {expected_type.__name__!r}, got {type(obj).__name__!r}",
            )


class InMemoryBotMerger(BotMergerBase):
    """An in-memory object manager."""

    # TODO should in-memory implementation care about eviction of old objects ?

    def __init__(self) -> None:
        super().__init__()
        self._objects: dict[ObjectKey, Any] = {}

    async def _register_object(self, key: ObjectKey, value: Any) -> None:
        """Register an object."""
        self._objects[key] = value

    async def _get_object(self, key: ObjectKey) -> Any | None:
        """Get an object by its key."""
        return self._objects.get(key)


# TODO RemoteBotMerger for distributed configurations ?
# TODO RedisBotMerger ? SQLAlchemyBotMerger ? A hybrid of the two ? Any other ideas ?
