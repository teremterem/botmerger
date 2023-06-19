# pylint: disable=no-name-in-module,too-many-arguments
"""Implementations of BotMerger class."""
import asyncio
import dataclasses
import logging
from abc import abstractmethod
from typing import Any, Optional, Tuple, Type, Dict

from pydantic import UUID4, BaseModel

from botmerger.base import (
    BotMerger,
    MergedObject,
    SingleTurnHandler,
    SingleTurnContext,
    BotResponses,
    ObjectKey,
    MessageType,
)
from botmerger.errors import BotAliasTakenError, BotNotFoundError
from botmerger.models import (
    MergedBot,
    MergedChannel,
    MergedUser,
    MergedMessage,
    MergedParticipant,
    OriginalMessage,
    ForwardedMessage,
)

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

    async def trigger_bot(self, bot: MergedBot, request: MergedMessage) -> BotResponses:
        handler = self._single_turn_handlers[bot.uuid]
        bot_responses = BotResponses(request)
        context = SingleTurnContext(
            merger=self,
            this_bot=bot,
            channel=request.channel,
            request=request,
            bot_responses=bot_responses,
        )
        asyncio.create_task(self._run_single_turn_handler(handler, context))
        return bot_responses

    # noinspection PyProtectedMember,PyMethodMayBeStatic
    async def _run_single_turn_handler(self, handler: SingleTurnHandler, context: SingleTurnContext) -> None:
        # pylint: disable=broad-except,protected-access
        try:
            await handler(context)
        except Exception as exc:
            logger.debug(exc, exc_info=exc)
            context._bot_responses._response_queue.put_nowait(exc)
        finally:
            context._bot_responses._response_queue.put_nowait(context._bot_responses._END_OF_RESPONSES)

    def create_bot(
        self,
        alias: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> MergedBot:
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
        self._single_turn_handlers[bot.uuid] = handler
        try:
            handler.bot = bot
        except AttributeError:
            # the trick with setting attributes on a function does not work with methods, but that's fine
            logger.debug("could not set attributes on %r", handler)

    async def find_bot(self, alias: str) -> MergedBot:
        bot = await self._get_bot(alias)
        if not bot:
            raise BotNotFoundError(f"bot with alias {alias!r} was not found")
        return bot

    async def find_or_create_user_channel(
        self,
        channel_type: str,
        channel_id: Any,
        user_display_name: str,
        **kwargs,
    ) -> MergedChannel:
        key = self._generate_channel_key(channel_type=channel_type, channel_id=channel_id)

        channel = await self._get_correct_object(key, MergedChannel)

        if not channel:
            user = MergedUser(merger=self, name=user_display_name, **kwargs)
            await self._register_merged_object(user)

            channel = MergedChannel(
                merger=self,
                channel_type=channel_type,
                channel_id=channel_id,
                owner=user,
            )
            await self._register_immutable_object(key, channel)
            await self._register_merged_object(user)

        return channel

    async def create_message(
        self,
        thread_uuid: UUID4,
        channel: MergedChannel,
        sender: MergedParticipant,
        content: MessageType,
        indicate_typing_afterwards: Optional[bool],
        responds_to: Optional[MergedMessage],
        goes_after: Optional[MergedMessage],
        **kwargs,
    ) -> OriginalMessage:
        if isinstance(content, MergedMessage):
            # we are forwarding a message from another thread (or from a different place in the same thread)
            if indicate_typing_afterwards is None:
                # pass on the value from the original message
                indicate_typing_afterwards = content.indicate_typing_afterwards
            if isinstance(content, ForwardedMessage):
                # make sure we are not forwarding a forwarded message
                # TODO do this recursively or just rely on the fact that all messages are created by this method
                #  and there is never a ForwardedMessage instance in original_message field ?
                content = content.original_message

            message = ForwardedMessage(
                merger=self,
                channel=channel,
                thread_uuid=thread_uuid,
                sender=sender,
                original_message=content,
                indicate_typing_afterwards=indicate_typing_afterwards,
                responds_to=responds_to,
                goes_after=goes_after,
                **kwargs,
            )

        else:
            # we are creating a new message
            if indicate_typing_afterwards is None:
                raise ValueError("indicate_typing_afterwards must not be None when creating a new message")

            if dataclasses.is_dataclass(content):
                # noinspection PyDataclass
                content = dataclasses.asdict(content)
            elif isinstance(content, BaseModel):
                content = content.dict()

            # TODO check if resulting content is json-serializable

            message = OriginalMessage(
                merger=self,
                channel=channel,
                thread_uuid=thread_uuid,
                sender=sender,
                content=content,
                indicate_typing_afterwards=indicate_typing_afterwards,
                responds_to=responds_to,
                goes_after=goes_after,
                **kwargs,
            )

        await self._register_merged_object(message)
        await self.set_mutable_state(self._generate_latest_message_key(thread_uuid), message.uuid)
        return message

    async def create_next_message(
        self,
        thread_uuid: UUID4,
        channel: MergedChannel,
        sender: MergedParticipant,
        content: MessageType,
        indicate_typing_afterwards: Optional[bool],
        responds_to: Optional[MergedMessage],
        **kwargs,
    ) -> MergedMessage:
        latest_message_uuid = await self.get_mutable_state(self._generate_latest_message_key(channel.uuid))
        if latest_message_uuid:
            latest_message = await self.find_message(latest_message_uuid)
        else:
            latest_message = None

        return await self.create_message(
            thread_uuid=thread_uuid,
            channel=channel,
            sender=sender,
            content=content,
            responds_to=responds_to,
            goes_after=latest_message,
            indicate_typing_afterwards=indicate_typing_afterwards,
            **kwargs,
        )

    async def find_message(self, uuid: UUID4) -> MergedMessage:
        return await self._get_correct_object(uuid, MergedMessage)

    @abstractmethod
    async def _register_immutable_object(self, key: ObjectKey, value: Any) -> None:
        """Register an immutable object."""

    @abstractmethod
    async def _get_immutable_object(self, key: ObjectKey) -> Optional[Any]:
        """Get an immutable object by its key."""

    async def _get_correct_object(self, key: ObjectKey, expected_type: Type) -> Optional[Any]:
        """
        Get an object by its key and assert that either there is no object (None) or the object is of the expected
        type.
        """
        obj = await self._get_immutable_object(key)
        self._assert_correct_obj_type_or_none(obj, expected_type, key)
        return obj

    async def _register_merged_object(self, obj: MergedObject) -> None:
        """Register a merged object."""
        await self._register_immutable_object(obj.uuid, obj)

    async def _register_bot(self, bot: MergedBot) -> None:
        """Register a bot."""
        await self._register_merged_object(bot)
        await self._register_immutable_object(self._generate_bot_key(bot.alias), bot)

    async def _get_bot(self, alias: str) -> Optional[MergedBot]:
        """Get a bot by its alias."""
        return await self._get_correct_object(self._generate_bot_key(alias), MergedBot)

    # noinspection PyMethodMayBeStatic
    def _generate_bot_key(self, alias: str) -> Tuple[str, str]:
        """Generate a key for a bot."""
        return "bot_by_alias", alias

    # noinspection PyMethodMayBeStatic
    def _generate_channel_key(self, channel_type: str, channel_id: Any) -> Tuple[str, str, str]:
        """Generate a key for a channel."""
        return "channel_by_type_and_id", channel_type, channel_id

    # noinspection PyMethodMayBeStatic
    def _generate_latest_message_key(self, thread_uuid: UUID4) -> Tuple[str, UUID4]:
        """Generate a key for the latest message in a thread."""
        return "latest_message_by_thread", thread_uuid

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
        self._immutable_objects: Dict[ObjectKey, Any] = {}
        self._mutable_objects: Dict[UUID4, Any] = {}

    async def set_mutable_state(self, key: ObjectKey, state: Any) -> None:
        self._mutable_objects[key] = state

    async def get_mutable_state(self, key: ObjectKey) -> Optional[Any]:
        return self._mutable_objects.get(key)

    async def _register_immutable_object(self, key: ObjectKey, value: Any) -> None:
        self._immutable_objects[key] = value

    async def _get_immutable_object(self, key: ObjectKey) -> Optional[Any]:
        return self._immutable_objects.get(key)
