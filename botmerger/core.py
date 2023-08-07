# pylint: disable=no-name-in-module,too-many-arguments
"""Implementations of BotMerger class."""
import asyncio
import dataclasses
import json
import logging
from abc import abstractmethod
from typing import Any, Optional, Tuple, Type, Dict, Union, Iterable, List
from uuid import UUID

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
        self._default_user: Optional[MergedUser] = None
        self._default_msg_ctx: Optional[MergedMessage] = None

    async def get_default_user(self) -> MergedUser:
        if not self._default_user:
            self._default_user = await self.create_user(name=self.DEFAULT_USER_NAME, uuid=self.DEFAULT_USER_UUID)
        return self._default_user

    async def get_default_msg_ctx(self) -> MergedMessage:
        if not self._default_msg_ctx:
            default_user = await self.get_default_user()
            self._default_msg_ctx = await self._create_message(
                uuid=self.DEFAULT_MSG_CTX_UUID,
                content=self.DEFAULT_MSG_CTX_CONTENT,
                still_thinking=False,
                sender=default_user,
                receiver=default_user,
                parent_context=None,
                responds_to=None,
                goes_after=None,
            )
        return self._default_msg_ctx

    def trigger_bot(
        self,
        bot: MergedBot,
        request: Optional[Union[MessageType, "BotResponses"]] = None,
        requests: Optional[Iterable[Union[MessageType, "BotResponses"]]] = None,
        override_sender: Optional[MergedParticipant] = None,
        override_parent_ctx: Optional["MergedMessage"] = None,
        rewrite_cache: bool = False,
        **kwargs,  # TODO what to do with kwargs when there are multiple requests ?
    ) -> BotResponses:
        handler = self._single_turn_handlers[bot.uuid]

        if request is not None and requests is not None:
            raise ValueError("Cannot specify both `request` and `requests`. Please specify only one of them.")

        # pylint: disable=protected-access
        # noinspection PyProtectedMember
        current_context = SingleTurnContext._current_context.get()
        if current_context:
            if not override_sender:
                override_sender = current_context.this_bot
            if not override_parent_ctx:
                override_parent_ctx = current_context.concluding_request

        bot_responses = BotResponses()
        context = SingleTurnContext(
            merger=self,
            this_bot=bot,
            bot_responses=bot_responses,
        )

        asyncio.create_task(
            self._run_single_turn_handler(
                handler=handler,
                context=context,
                request=request,
                requests=requests,
                override_sender=override_sender,
                override_parent_ctx=override_parent_ctx,
                rewrite_cache=rewrite_cache,
                **kwargs,
            )
        )

        return bot_responses

    # noinspection PyProtectedMember,PyMethodMayBeStatic
    async def _run_single_turn_handler(
        self,
        handler: SingleTurnHandler,
        context: SingleTurnContext,
        request: Optional[Union[MessageType, "BotResponses"]],
        requests: Optional[Iterable[Union[MessageType, "BotResponses"]]],
        override_sender: Optional[MergedParticipant],
        override_parent_ctx: Optional["MergedMessage"],
        rewrite_cache: bool,
        **kwargs,
    ) -> None:
        caching_key: List[Any] = ["bot_response_cache", context.this_bot.alias]
        # pylint: disable=broad-except,protected-access
        try:
            prepared_requests = []

            async def _prepare_merged_message(_request: MessageType) -> None:
                request = await self.create_next_message(
                    content=_request,
                    still_thinking=False,
                    sender=override_sender,
                    receiver=context.this_bot,
                    parent_context=override_parent_ctx,
                    **kwargs,
                )
                prepared_requests.append(request)
                if not context.this_bot.no_cache:
                    caching_key.append(
                        # uuid is taken from the original message, but the extra fields are taken from the "forwarded"
                        # message
                        # TODO should any other fields be taken from the "forwarded" message ? (e.g. invisible_to_bots)
                        (request.original_message.uuid, json.dumps(request.extra_fields, sort_keys=True))
                    )

            async def _prepare_request(_request: Union[MessageType, "BotResponses"]) -> None:
                if isinstance(request, BotResponses):
                    async for another_bot_response in _request:
                        await _prepare_merged_message(another_bot_response)
                else:
                    await _prepare_merged_message(_request)

            if requests:
                for req in requests:
                    await _prepare_request(req)
            else:
                await _prepare_request(request)

            context.requests = tuple(prepared_requests)

            cached_responses: Optional[BotResponses] = None
            if not context.this_bot.no_cache:
                caching_key: Tuple[Any, ...] = tuple(caching_key)
                if not rewrite_cache:
                    # TODO is asyncio.Lock needed somewhere around here ?
                    cached_responses = await self.get_mutable_state(caching_key)

            if cached_responses is None:
                if not context.this_bot.no_cache:
                    # TODO come up with a way to put only json serializable stuff into the "mutable state"
                    # TODO introduce some sort of CachedBotResponses class, capable of creating new "forwarded"
                    #  messages that become part of the new chat history every time those response messages are
                    #  fetched from the cache (but it shouldn't forward the "forwarded" messages, it should
                    #  forward the original messages instead)
                    await self.set_mutable_state(caching_key, context._bot_responses)

                with context:
                    await handler(context)
            else:
                # we have a cache hit
                context._bot_responses._response_queue.put_nowait(cached_responses)

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
        no_cache: bool = False,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> MergedBot:
        # start a temporary event loop and call the async version of this method from there
        return asyncio.run(
            self.create_bot_async(
                alias=alias, name=name, description=description, single_turn=single_turn, no_cache=no_cache, **kwargs
            )
        )

    async def create_bot_async(
        self,
        alias: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        no_cache: bool = False,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> MergedBot:
        if await self._get_bot(alias):
            raise BotAliasTakenError(f"bot with alias {alias!r} is already registered")

        if not name:
            name = alias
        bot = MergedBot(merger=self, alias=alias, name=name, description=description, no_cache=no_cache, **kwargs)

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
            logger.debug("could not set `bot` attribute on %r", handler)

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
    ) -> MergedMessage:
        key = self._generate_channel_key(channel_type=channel_type, channel_id=channel_id)

        channel_msg_uuid = await self._get_correct_object(key, UUID)
        if channel_msg_uuid:
            channel_msg = await self.find_message(channel_msg_uuid)
        else:
            channel_msg = None

        if not channel_msg:
            user = await self.create_user(name=user_display_name)
            channel_msg = await self._create_message(
                content=f"{user_display_name}'s channel",
                still_thinking=False,
                sender=user,
                receiver=user,
                parent_context=None,
                responds_to=None,
                goes_after=None,
                extra_fields={
                    "channel_type": channel_type,
                    "channel_id": channel_id,
                },
            )
            await self._register_immutable_object(key, channel_msg.uuid)

        return channel_msg

    async def create_user(self, name: str, **kwargs) -> MergedUser:
        user = MergedUser(merger=self, name=name, **kwargs)
        await self._register_merged_object(user)
        return user

    async def _create_message(
        self,
        content: MessageType,
        still_thinking: Optional[bool],
        sender: MergedParticipant,
        receiver: MergedParticipant,
        parent_context: Optional[MergedMessage],
        responds_to: Optional[MergedMessage],
        goes_after: Optional[MergedMessage],
        **kwargs,
    ) -> OriginalMessage:
        if isinstance(content, MergedMessage):
            # we are forwarding a message from another thread (or from a different place in the same thread)
            if still_thinking is None:
                # pass on the value from the original message
                still_thinking = content.still_thinking

            message = ForwardedMessage(
                merger=self,
                sender=sender,
                receiver=receiver,
                original_message=content,
                still_thinking=still_thinking,
                parent_context=parent_context,
                responds_to=responds_to,
                goes_after=goes_after,
                **kwargs,
            )

        else:
            # we are creating a new message
            if still_thinking is None:
                raise ValueError("still_thinking must not be None when creating a new message")

            if dataclasses.is_dataclass(content):
                # noinspection PyDataclass
                content = dataclasses.asdict(content)
            elif isinstance(content, BaseModel):
                content = content.dict()

            # TODO check if resulting content is json-serializable

            message = OriginalMessage(
                merger=self,
                sender=sender,
                receiver=receiver,
                content=content,
                still_thinking=still_thinking,
                parent_context=parent_context,
                responds_to=responds_to,
                goes_after=goes_after,
                **kwargs,
            )

        await self._register_merged_object(message)
        if message.parent_context:
            await self.set_mutable_state(
                self._generate_latest_message_in_chat_key(
                    message.parent_context.uuid, message.sender.uuid, message.receiver.uuid
                ),
                message.uuid,
            )
        return message

    async def create_next_message(
        self,
        content: MessageType,
        still_thinking: Optional[bool],
        sender: Optional[MergedParticipant],
        receiver: MergedParticipant,
        parent_context: Optional[MergedMessage],
        responds_to: Optional[MergedMessage] = None,
        **kwargs,
    ) -> MergedMessage:
        if not sender:
            sender = await self.get_default_user()
        if not parent_context:
            parent_context = await self.get_default_msg_ctx()

        latest_message_uuid = await self.get_mutable_state(
            self._generate_latest_message_in_chat_key(parent_context.uuid, sender.uuid, receiver.uuid)
        )
        if latest_message_uuid:
            latest_message = await self.find_message(latest_message_uuid)
        else:
            latest_message = None

        return await self._create_message(
            content=content,
            still_thinking=still_thinking,
            sender=sender,
            receiver=receiver,
            parent_context=parent_context,
            responds_to=responds_to,
            goes_after=latest_message,
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
    def _generate_latest_message_in_chat_key(
        self, context_uuid: UUID4, *participant_uuids: UUID4
    ) -> Tuple[str, UUID4, ...]:
        """Generate a key for the latest message in a given context."""
        # TODO what to do when the same sender calls the same receiver within the same context message multiple times
        #  in parallel ? should the conversation history be grouped by responds_to to account for that ?
        #  some other solution ? Maybe some random identifier stored in a ContextVar ?
        return "latest_message_in_chat", context_uuid, *sorted(participant_uuids)

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
