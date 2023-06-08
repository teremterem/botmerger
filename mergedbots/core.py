# pylint: disable=no-name-in-module
"""BotManager implementations."""
import logging
from abc import abstractmethod
from typing import Any, AsyncGenerator

from mergedbots.errors import BotNotFoundError
from pydantic import PrivateAttr, UUID4

from mergedbots.base import BotManager
from mergedbots.models import MergedParticipant, MergedBot, MergedMessage, MergedObject

ObjectKey = Any | tuple[Any, ...]

logger = logging.getLogger(__name__)


class BotManagerBase(BotManager):
    """
    An abstract factory of everything else in this library. This class implements the common functionality of all
    concrete BotManager implementations.
    """

    # TODO think about thread-safety ?

    async def fulfill(
        self, bot_handle: str, request: MergedMessage, fallback_bot_handle: str = None
    ) -> AsyncGenerator["MergedMessage", None]:
        """
        Find a bot by its handle and fulfill a request using that bot. If the bot is not found and
        `fallback_bot_handle` is provided, then the fallback bot is used instead. If the fallback bot is not found
        either, then `BotNotFoundError` is raised.
        """
        try:
            bot = await self.find_bot(bot_handle)
        except BotNotFoundError as exc1:
            if not fallback_bot_handle:
                raise exc1

            logger.info("bot %r not found, falling back to %r", bot_handle, fallback_bot_handle)
            try:
                bot = await self.find_bot(fallback_bot_handle)
            except BotNotFoundError as exc2:
                raise exc2 from exc1

        # TODO retrieve bot responses from cache if this particular bot already fulfilled this particular request
        # noinspection PyProtectedMember
        async for response in bot._fulfillment_func(bot, request):  # pylint: disable=protected-access
            yield response

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
        return await self._create_next_message(
            channel_type=channel_type,
            channel_id=channel_id,
            new_conversation=new_conversation,
            sender=originator,
            content=content,
            is_visible_to_bots=is_visible_to_bots,
            is_still_typing=False,  # TODO use a wrapper object for this
            originator=originator,
            in_fulfillment_of=None,
            **kwargs,
        )

    # noinspection PyProtectedMember
    async def create_bot_response(  # pylint: disable=too-many-arguments
        self,
        bot: MergedBot,
        in_fulfillment_of: MergedMessage,
        content: str,
        is_still_typing: bool,
        is_visible_to_bots: bool,
        **kwargs,
    ) -> "MergedMessage":
        """Create a bot response to `in_fulfillment_of` message."""
        response = await self._create_next_message(
            channel_type=in_fulfillment_of.channel_type,
            channel_id=in_fulfillment_of.channel_id,
            in_fulfillment_of=in_fulfillment_of,
            sender=bot,
            content=content,
            is_still_typing=is_still_typing,
            is_visible_to_bots=is_visible_to_bots,
            originator=in_fulfillment_of.originator,
            **kwargs,
        )

        # NOTE: This is a temporary implementation - MergedMessage will not support `_responses` and
        # `_responses_by_bots` attributes in the future (this kind of state data is meant to be retrieved from the
        # underlying storage dynamically).

        # pylint: disable=protected-access
        in_fulfillment_of._responses.append(response)
        # TODO what if message processing failed and bot response list is not complete ?
        #  we need a flag to indicate that the bot response list is complete
        in_fulfillment_of._responses_by_bots[bot.handle].append(response)

        return response

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

    async def _create_next_message(
        self,
        channel_type: str,
        channel_id: Any,
        new_conversation: bool = False,
        **kwargs,
    ) -> MergedMessage:
        """
        Create a new message in a conversation (and update the "conversation tail" reference for the correspondent
        for the correspondent channel).
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
            previous_msg=previous_msg,
            **kwargs,
        )
        await self._register_merged_object(message)
        await self._register_object(conv_tail_key, message)  # save the tail of the conversation
        return message

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

    # TODO should in-memory implementation care about eviction of old objects ?
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
