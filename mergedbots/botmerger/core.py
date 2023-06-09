# pylint: disable=no-name-in-module
"""Implementations of BotMerger class."""
import asyncio
import logging
from abc import abstractmethod
from typing import Any, Optional, Tuple, Type, Dict, Union

from pydantic import UUID4

from mergedbots.botmerger.base import BotMerger, MergedObject, SingleTurnHandler, SingleTurnContext, BotResponses
from mergedbots.botmerger.errors import BotAliasTakenError, BotNotFoundError
from mergedbots.botmerger.models import MergedBot, MergedChannel, MergedUser, MergedMessage, MessageEnvelope

ObjectKey = Union[UUID4, Tuple[Any, ...]]

logger = logging.getLogger(__name__)


class BotMergerBase(BotMerger):
    """
    An abstract factory of everything else in this library. This class implements the common functionality of all
    concrete BotMerger implementations.
    """

    # TODO should we or should we not think about thread-safety ?

    def __init__(self) -> None:
        super().__init__()
        self._single_turn_handlers: Dict[UUID4, SingleTurnHandler] = {}

    def trigger_bot(self, bot: MergedBot, message: Union[MergedMessage, MessageEnvelope]) -> BotResponses:
        """Trigger a bot with a message."""
        handler = self._single_turn_handlers[bot.uuid]
        bot_responses = BotResponses()
        context = SingleTurnContext(bot, message, bot_responses)
        asyncio.create_task(self._run_single_turn_handler(handler, context, bot_responses))
        return bot_responses

    async def _run_single_turn_handler(
        self, handler: SingleTurnHandler, context: SingleTurnContext, bot_responses: BotResponses
    ) -> None:
        # TODO propagate exceptions to BotResponses
        await handler(context)
        bot_responses._response_queue.put_nowait(BotResponses._END_OF_RESPONSES)

    # TODO TODO TODO def trigger_bot_by_uuid()
    # TODO TODO TODO def trigger_bot_by_alias()

    def create_bot(
        self,
        alias: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> MergedBot:
        """
        Create a bot. This version of bot creation function is meant to be called outside an async context (for ex.
        as a decorator to single-turn and multi-turn handler functions).
        """
        # start a temporary event loop and call the async version of this method from there
        return asyncio.run(
            self.create_bot_async(alias=alias, name=name, description=description, single_turn=single_turn, **kwargs)
        )

    async def create_bot_async(
        self,
        alias: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> MergedBot:
        """Create a bot while inside an async context."""
        if await self._get_bot(alias):
            raise BotAliasTakenError(f"bot with alias {alias!r} is already registered")

        if not name:
            name = alias
        bot = MergedBot(merger=self, alias=alias, name=name, description=description, **kwargs)

        await self._register_bot(bot)

        if single_turn:
            bot.single_turn(single_turn)
        return bot

    def register_local_single_turn_handler(self, bot: "MergedBot", handler: SingleTurnHandler) -> None:
        """Register a local function as a single-turn handler for a bot."""
        self._single_turn_handlers[bot.uuid] = handler
        try:
            handler.bot = bot
        except AttributeError:
            # the trick with setting attributes on a function does not work with methods, but that's fine
            logger.debug("could not set attributes on %r", handler)

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
    async def _get_object(self, key: ObjectKey) -> Optional[Any]:
        """Get an object by its key."""

    async def _register_merged_object(self, obj: MergedObject) -> None:
        """Register a merged object."""
        await self._register_object(obj.uuid, obj)

    async def _get_merged_object(self, uuid: UUID4) -> Optional[MergedObject]:
        """Get a merged object by its uuid."""
        obj = await self._get_object(uuid)
        self._assert_correct_obj_type_or_none(obj, MergedObject, uuid)
        return obj

    async def _register_bot(self, bot: MergedBot) -> None:
        """Register a bot."""
        await self._register_merged_object(bot)
        await self._register_object(self._generate_bot_key(bot.alias), bot)

    async def _get_bot(self, alias: str) -> Optional[MergedBot]:
        """Get a bot by its alias."""
        key = self._generate_bot_key(alias)
        bot = await self._get_object(key)
        self._assert_correct_obj_type_or_none(bot, MergedBot, key)
        return bot

    # noinspection PyMethodMayBeStatic
    def _generate_bot_key(self, alias: str) -> Tuple[str, str]:
        """Generate a key for a bot."""
        return "bot_by_alias", alias

    # noinspection PyMethodMayBeStatic
    def _generate_channel_key(self, channel_type: str, channel_id: Any) -> Tuple[str, str, str]:
        """Generate a key for a channel."""
        return "channel_by_type_and_id", channel_type, channel_id

    # noinspection PyMethodMayBeStatic
    def _assert_correct_obj_type_or_none(self, obj: Any, expected_type: Type, key: Any) -> None:
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
        self._objects: Dict[ObjectKey, Any] = {}

    async def _register_object(self, key: ObjectKey, value: Any) -> None:
        """Register an object."""
        self._objects[key] = value

    async def _get_object(self, key: ObjectKey) -> Optional[Any]:
        """Get an object by its key."""
        return self._objects.get(key)
