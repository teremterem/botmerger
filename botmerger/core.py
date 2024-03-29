# pylint: disable=no-name-in-module,too-many-arguments
"""Base abstract implementation of the BotMerger interface."""
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
from botmerger.errors import BotNotFoundError
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
                parent_ctx_msg_uuid=None,
                requesting_msg_uuid=None,
                prev_msg_uuid=None,
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
                # TODO what to do with `hidden_from_history` flag ? currently it is just False for every message.
                #  should it be inherited in case messages are being forwarded ?
                request = await self.create_next_message(
                    content=_request,
                    still_thinking=False,
                    sender=override_sender,
                    receiver=context.this_bot,
                    parent_ctx_msg_uuid=override_parent_ctx.uuid if override_parent_ctx else None,
                    **kwargs,
                )
                prepared_requests.append(request)
                if not context.this_bot.no_cache:
                    caching_key.append(
                        # uuid is taken from the original message, but the extra fields are taken from the "forwarded"
                        # message
                        # TODO should any other fields be taken from the "forwarded" message ?
                        #  (e.g. hidden_from_history)
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

    async def replay(self, request_msg_uuid: UUID4) -> BotResponses:
        request = await self.find_message(request_msg_uuid)
        if request is None:
            raise ValueError(f"Request message with uuid {request_msg_uuid} not found.")
        if not isinstance(request.receiver, MergedBot):
            raise ValueError(f"Message with uuid {request_msg_uuid} wasn't originally sent to a bot.")
        bot = request.receiver

        handler = self._single_turn_handlers[bot.uuid]

        bot_responses = BotResponses()
        context = SingleTurnContext(
            merger=self,
            this_bot=bot,
            bot_responses=bot_responses,
        )
        asyncio.create_task(
            self._replay_single_turn_handler(
                handler=handler,
                context=context,
                request=request,
            )
        )
        return bot_responses

    # noinspection PyProtectedMember,PyMethodMayBeStatic
    async def _replay_single_turn_handler(
        self,
        handler: SingleTurnHandler,
        context: SingleTurnContext,
        request: "MergedMessage",
    ) -> None:
        # TODO avoid duplication of the caching_key building code
        caching_key: Tuple[Any, ...] = (
            "bot_response_cache",
            context.this_bot.alias,
            request.original_message.uuid,
            json.dumps(request.extra_fields, sort_keys=True),
        )
        # pylint: disable=broad-except,protected-access
        try:
            context.requests = (request,)

            if not context.this_bot.no_cache:
                # TODO come up with a way to put only json serializable stuff into the "mutable state"
                # TODO introduce some sort of CachedBotResponses class, capable of creating new "forwarded"
                #  messages that become part of the new chat history every time those response messages are
                #  fetched from the cache (but it shouldn't forward the "forwarded" messages, it should
                #  forward the original messages instead)
                await self.set_mutable_state(caching_key, context._bot_responses)

            with context:
                await handler(context)

        except Exception as exc:
            logger.debug(exc, exc_info=exc)
            context._bot_responses._response_queue.put_nowait(exc)
        finally:
            context._bot_responses._response_queue.put_nowait(context._bot_responses._END_OF_RESPONSES)

    def create_bot(
        self,
        alias: Union[str, SingleTurnHandler],
        name: Optional[str] = None,
        description: Optional[str] = None,
        no_cache: bool = False,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> Union[MergedBot, SingleTurnHandler]:
        # start a temporary event loop and call the async version of this method from there
        return asyncio.run(
            self.create_bot_async(
                alias=alias, name=name, description=description, single_turn=single_turn, no_cache=no_cache, **kwargs
            )
        )

    async def create_bot_async(
        self,
        alias: Union[str, SingleTurnHandler],
        name: Optional[str] = None,
        description: Optional[str] = None,
        no_cache: bool = False,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> Union[MergedBot, SingleTurnHandler]:
        if callable(alias):
            # TODO "bare decorator" is a temporary solution for the "optional alias" problem - replace with a better
            #  implementation which allows passing other parameters (`name`, `description`, etc.) when alias is
            #  omitted (because "bare decorator" does not allow that)
            bot = await self.create_bot_async(alias.__name__)
            return bot.single_turn(alias)

        # # TODO restore this check when the hack below is removed
        # if await self._get_bot(alias):
        #     raise BotAliasTakenError(f"bot with alias {alias!r} is already registered")

        if not name:
            name = alias
        # TODO this is a hack that violates immutability of MergedBot for the sake of merging the bot being set up
        #  with the bot that was loaded from the yaml log - come up with a design that does not require this
        bot = await self._get_bot(alias)
        if bot:
            bot.name = name
            bot.description = description
            bot.no_cache = no_cache
            for key, value in kwargs.items():
                setattr(bot, key, value)
        else:
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
                parent_ctx_msg_uuid=None,
                requesting_msg_uuid=None,
                prev_msg_uuid=None,
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
        parent_ctx_msg_uuid: Optional[UUID4],
        requesting_msg_uuid: Optional[UUID4],
        prev_msg_uuid: Optional[UUID4],
        hidden_from_history: bool = False,
        **kwargs,
    ) -> MergedMessage:
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
                parent_ctx_msg_uuid=parent_ctx_msg_uuid,
                requesting_msg_uuid=requesting_msg_uuid,
                prev_msg_uuid=prev_msg_uuid,
                hidden_from_history=hidden_from_history,
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
                parent_ctx_msg_uuid=parent_ctx_msg_uuid,
                requesting_msg_uuid=requesting_msg_uuid,
                prev_msg_uuid=prev_msg_uuid,
                hidden_from_history=hidden_from_history,
                **kwargs,
            )

        await self._register_message(message)
        return message

    async def _register_message(self, message: MergedMessage) -> None:
        await self._register_merged_object(message)
        if message.parent_ctx_msg_uuid:
            await self.set_mutable_state(
                self._generate_latest_message_in_chat_key(
                    message.parent_ctx_msg_uuid, message.sender.uuid, message.receiver.uuid
                ),
                message.uuid,
            )

    async def create_next_message(
        self,
        content: MessageType,
        still_thinking: Optional[bool],
        sender: Optional[MergedParticipant],
        receiver: MergedParticipant,
        parent_ctx_msg_uuid: Optional[UUID4],
        requesting_msg_uuid: Optional[UUID4] = None,
        hidden_from_history: bool = False,
        **kwargs,
    ) -> MergedMessage:
        if not sender:
            sender = await self.get_default_user()
        if not parent_ctx_msg_uuid:
            parent_ctx_msg_uuid = (await self.get_default_msg_ctx()).uuid

        latest_message_uuid = await self.get_mutable_state(
            self._generate_latest_message_in_chat_key(parent_ctx_msg_uuid, sender.uuid, receiver.uuid)
        )
        return await self._create_message(
            content=content,
            still_thinking=still_thinking,
            sender=sender,
            receiver=receiver,
            parent_ctx_msg_uuid=parent_ctx_msg_uuid,
            requesting_msg_uuid=requesting_msg_uuid,
            prev_msg_uuid=latest_message_uuid,
            hidden_from_history=hidden_from_history,
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
        #  in parallel ? should the conversation history be grouped by requesting_msg_uuid to account for that ?
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
