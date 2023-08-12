# pylint: disable=no-name-in-module,too-many-arguments
"""Models for the BotMerger library."""
from abc import ABC
from typing import Any, Optional, Union, Iterable, List

from pydantic import Field, UUID4

from botmerger.base import (
    MergedObject,
    SingleTurnHandler,
    BotResponses,
    MessageContent,
    MessageType,
    BaseMessage,
    MergedSerializerVisitor,
)


class MergedParticipant(MergedObject, ABC):
    """A chat participant."""

    name: str
    is_human: bool


class MergedBot(MergedParticipant):
    """A bot that can interact with other bots."""

    is_human: bool = Field(False, const=True)

    alias: str
    description: Optional[str] = None
    no_cache: bool = False

    def trigger(
        self,
        request: Optional[Union[MessageType, "BotResponses"]] = None,
        requests: Optional[Iterable[Union[MessageType, "BotResponses"]]] = None,
        override_sender: Optional[MergedParticipant] = None,
        override_parent_ctx: Optional["MergedMessage"] = None,
        rewrite_cache: bool = False,
        **kwargs,
    ) -> BotResponses:
        """
        Trigger this bot to respond to a message or messages. Returns an object that can be used to retrieve the bot's
        response(s) in an asynchronous manner.
        """
        return self.merger.trigger_bot(
            bot=self,
            request=request,
            requests=requests,
            override_sender=override_sender,
            override_parent_ctx=override_parent_ctx,
            rewrite_cache=rewrite_cache,
            **kwargs,
        )

    async def get_final_response(
        self,
        request: Optional[Union[MessageType, "BotResponses"]] = None,
        requests: Optional[Iterable[Union[MessageType, "BotResponses"]]] = None,
        override_sender: Optional[MergedParticipant] = None,
        override_parent_ctx: Optional["MergedMessage"] = None,
        rewrite_cache: bool = False,
        **kwargs,
    ) -> Optional["MergedMessage"]:
        """Get the final response from the bot for a given request."""
        responses = self.trigger(
            request=request,
            requests=requests,
            override_sender=override_sender,
            override_parent_ctx=override_parent_ctx,
            rewrite_cache=rewrite_cache,
            **kwargs,
        )
        return await responses.get_final_response()

    async def get_all_responses(
        self,
        request: Optional[Union[MessageType, "BotResponses"]] = None,
        requests: Optional[Iterable[Union[MessageType, "BotResponses"]]] = None,
        override_sender: Optional[MergedParticipant] = None,
        override_parent_ctx: Optional["MergedMessage"] = None,
        rewrite_cache: bool = False,
        **kwargs,
    ) -> List["MergedMessage"]:
        """Get all the responses from the bot for a given request."""
        responses = self.trigger(
            request=request,
            requests=requests,
            override_sender=override_sender,
            override_parent_ctx=override_parent_ctx,
            rewrite_cache=rewrite_cache,
            **kwargs,
        )
        return await responses.get_all_responses()

    def single_turn(self, handler: SingleTurnHandler) -> SingleTurnHandler:
        """
        A decorator that registers a local single-turn handler function for this MergedBot. Single-turn means that
        the function will be called as an event handler for a single incoming message (or a single set of messages
        if they were sent as a bundle).
        """
        self.merger.register_local_single_turn_handler(self, handler)
        return handler

    def __call__(self, handler: SingleTurnHandler) -> SingleTurnHandler:
        return self.single_turn(handler)

    async def _serialize(self, visitor: MergedSerializerVisitor) -> Any:
        # noinspection PyProtectedMember
        return await visitor.serialize_bot(self)


class MergedUser(MergedParticipant):
    """A user that can interact with bots."""

    is_human: bool = Field(True, const=True)

    async def _serialize(self, visitor: MergedSerializerVisitor) -> Any:
        # noinspection PyProtectedMember
        return await visitor.serialize_user(self)


class MergedMessage(BaseMessage, MergedObject, ABC):
    """A message that was sent in a channel."""

    sender: MergedParticipant
    receiver: MergedParticipant
    still_thinking: bool
    parent_ctx_msg_uuid: Optional[UUID4]
    requesting_msg_uuid: Optional[UUID4]
    prev_msg_uuid: Optional[UUID4]
    invisible_to_bots: bool = False

    async def get_parent_context(self) -> Optional["MergedMessage"]:
        """Get the parent context for this message."""
        if self.parent_ctx_msg_uuid is None:
            return None
        return await self.merger.find_message(self.parent_ctx_msg_uuid)

    async def get_requesting_message(self) -> Optional["MergedMessage"]:
        """Get the message that requested this message."""
        if self.requesting_msg_uuid is None:
            return None
        return await self.merger.find_message(self.requesting_msg_uuid)

    async def get_previous_message(self) -> Optional["MergedMessage"]:
        """Get the previous message in the conversation."""
        if self.prev_msg_uuid is None:
            return None
        return await self.merger.find_message(self.prev_msg_uuid)

    async def get_conversation_history(
        self, max_length: Optional[int] = None, include_invisible_to_bots: bool = False
    ) -> List["MergedMessage"]:
        """Get the conversation history for this message (excluding this message)."""
        # TODO move this implementation to BotMergerBase
        history = []
        msg = await self.get_previous_message()
        while msg and (max_length is None or len(history) < max_length):
            if include_invisible_to_bots or not msg.invisible_to_bots:
                history.append(msg)
            msg = await msg.get_previous_message()
        history.reverse()
        return history

    async def get_full_conversation(
        self, max_length: Optional[int] = None, include_invisible_to_bots: bool = False
    ) -> List["MergedMessage"]:
        """Get the full conversation history for this message (including this message)."""
        # TODO move this implementation to BotMergerBase
        if max_length is not None:
            # let's account for the current message as well
            max_length -= 1
        result = await self.get_conversation_history(
            max_length=max_length, include_invisible_to_bots=include_invisible_to_bots
        )
        if include_invisible_to_bots or not self.invisible_to_bots:
            result.append(self)
        return result

    async def get_ultimate_original_message(self) -> "OriginalMessage":
        """Get the ultimate original message for this message."""
        # TODO does it need to by async ?
        msg = self
        while isinstance(msg, ForwardedMessage):
            msg = msg.original_message
        if not isinstance(msg, OriginalMessage):
            raise RuntimeError("OriginalMessage not found")
        return msg


class OriginalMessage(MergedMessage):
    """This subclass represents an original message. It implements `content` as a Pydantic field."""

    content: Union[str, Any]

    @property
    def original_message(self) -> "MergedMessage":
        """The original message is itself."""
        return self

    async def _serialize(self, visitor: MergedSerializerVisitor) -> Any:
        # noinspection PyProtectedMember
        return await visitor.serialize_original_message(self)


class ForwardedMessage(MergedMessage):
    """
    This subclass represents a forwarded message. It implements `content` as a property that is delegated to the
    original message.
    """

    original_message: MergedMessage

    # TODO does `invisible_to_bots` need to be inherited from the original message as well ?

    @property
    def content(self) -> MessageContent:
        """The content of the original message."""
        return self.original_message.content

    async def _serialize(self, visitor: MergedSerializerVisitor) -> Any:
        # noinspection PyProtectedMember
        return await visitor.serialize_forwarded_message(self)
