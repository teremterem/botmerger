# pylint: disable=no-name-in-module
"""BotManager implementations."""
import asyncio
from abc import abstractmethod
from typing import Any, AsyncGenerator

from pydantic import PrivateAttr, UUID4

from mergedbots.errors import BotHandleTakenError, BotNotFoundError
from mergedbots.models import BotManager, MergedParticipant, MergedUser, MergedBot, MergedMessage, MergedObject

ObjectKey = Any | tuple[Any, ...]


class BotManagerBase(BotManager):
    """
    An abstract factory of everything else in this library. This class implements the common functionality of all
    concrete BotManager implementations.
    """

    # TODO think about thread-safety ?

    async def fulfill(self, bot_handle: str, request: MergedMessage) -> AsyncGenerator[MergedMessage, None]:
        """Find a bot by its handle and fulfill a request using that bot."""
        bot = await self.find_bot(bot_handle)
        # noinspection PyProtectedMember
        async for response in bot._fulfillment_func(bot, request):  # pylint: disable=protected-access
            yield response

    def create_bot(self, handle: str, name: str = None, **kwargs) -> MergedBot:
        """
        Create a merged bot. This version of bot creation function is meant to be called before event loop is started
        (for ex. as a decorator to fulfillment functions as they are being defined).
        """
        # TODO is this a dirty hack ? find a better way to do this ?
        # start a temporary event loop and call the async version of this method from there
        return asyncio.run(self.create_bot_async(handle=handle, name=name, **kwargs))

    async def create_bot_async(self, handle: str, name: str = None, **kwargs) -> MergedBot:
        """Create a merged bot."""
        if await self._get_bot(handle):
            raise BotHandleTakenError(f"bot with handle {handle!r} is already registered")

        if not name:
            name = handle
        bot = MergedBot(manager=self, handle=handle, name=name, **kwargs)

        await self._register_bot(bot)
        return bot

    async def find_bot(self, handle: str) -> MergedBot:
        """Fetch a bot by its handle."""
        bot = await self._get_bot(handle)
        if not bot:
            raise BotNotFoundError(f"bot with handle {handle!r} does not exist")
        return bot

    async def find_or_create_user(
        self,
        channel_type: str,
        channel_specific_id: Any,
        user_display_name: str,
        **kwargs,
    ) -> MergedUser:
        """Find or create a user."""
        key = self._generate_merged_user_key(channel_type=channel_type, channel_specific_id=channel_specific_id)
        user = await self._get_object(key)
        self._assert_correct_obj_type_or_none(user, MergedUser, key)
        if user:
            return user

        user = MergedUser(manager=self, name=user_display_name, **kwargs)
        await self._register_merged_object(user)
        await self._register_object(key, user)
        return user

    async def create_originator_message(  # pylint: disable=too-many-arguments
        self,
        channel_type: str,
        channel_id: Any,
        originator: MergedParticipant,
        content: str,
        is_visible_to_bots: bool = True,
        new_conversation: bool = False,
        **kwargs,
    ) -> MergedMessage:
        """
        Create a new message from the conversation originator. The originator is typically a user, but it can also be
        a bot (which, for example, is trying to talk to another bot).
        """
        conv_tail_key = self._generate_conversation_tail_key(
            channel_type=channel_type,
            channel_id=channel_id,
        )
        previous_msg = None if new_conversation else await self._get_object(conv_tail_key)
        self._assert_correct_obj_type_or_none(previous_msg, MergedMessage, conv_tail_key)

        message = MergedMessage(
            manager=self,
            channel_type=channel_type,
            channel_id=channel_id,
            sender=originator,
            content=content,
            is_visible_to_bots=is_visible_to_bots,
            is_still_typing=False,  # TODO use a wrapper object for this
            originator=originator,
            previous_msg=previous_msg,
            in_fulfillment_of=None,
            **kwargs,
        )
        await self._register_merged_object(message)
        await self._register_object(conv_tail_key, message)  # save the tail of the conversation
        return message

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
        await self._register_object(self._generate_merged_bot_key(bot.handle), bot)

    async def _get_bot(self, handle: str) -> MergedBot | None:
        """Get a bot by its handle."""
        key = self._generate_merged_bot_key(handle)
        bot = await self._get_object(key)
        self._assert_correct_obj_type_or_none(bot, MergedBot, key)
        return bot

    # noinspection PyMethodMayBeStatic
    def _generate_merged_bot_key(self, handle: str) -> tuple[str, str]:
        """Generate a key for a bot."""
        return "bot_by_handle", handle

    # noinspection PyMethodMayBeStatic
    def _generate_merged_user_key(self, channel_type: str, channel_specific_id: Any) -> tuple[str, str, str]:
        """Generate a key for a user."""
        return "user_by_channel", channel_type, channel_specific_id

    # noinspection PyMethodMayBeStatic
    def _generate_conversation_tail_key(self, channel_type: str, channel_id: Any) -> tuple[str, str, str]:
        """Generate a key for a conversation tail."""
        return "conv_tail_by_channel", channel_type, channel_id

    # noinspection PyMethodMayBeStatic
    def _assert_correct_obj_type_or_none(self, obj: Any, expected_type: type, key: Any) -> None:
        """Assert that the object is of the expected type or None."""
        if obj and not isinstance(obj, expected_type):
            raise TypeError(
                f"wrong type of object by the key {key!r}: "
                f"expected {expected_type.__name__!r}, got {type(obj).__name__!r}",
            )


class InMemoryBotManager(BotManagerBase):
    """An in-memory object manager."""

    _objects: dict[ObjectKey, Any] = PrivateAttr(default_factory=dict)

    async def get_full_conversion(
        self, conversation_tail: "MergedMessage", include_invisible_to_bots: bool = False
    ) -> list["MergedMessage"]:
        """Fetch the full conversation history up to the given message inclusively (`conversation_tail`)."""
        # NOTE: This is a simplistic implementation. A different approach will be needed in case of `RedisBotManager`,
        # `RemoteBotManager`, and other future implementations, because in those cases history messages will not be
        # immediately available via `msg.previous_msg`.
        conversation = []
        msg = conversation_tail
        while msg:
            if include_invisible_to_bots or msg.is_visible_to_bots:
                conversation.append(msg)
            msg = msg.previous_msg

        conversation.reverse()
        return conversation

    async def _register_object(self, key: ObjectKey, value: Any) -> None:
        """Register an object."""
        self._objects[key] = value

    async def _get_object(self, key: ObjectKey) -> Any | None:
        """Get an object by its key."""
        return self._objects.get(key)


# TODO RemoteBotManager for distributed configurations ?
# TODO RedisBotManager ? SQLAlchemyBotManager ? A hybrid of the two ? Any other ideas ?
