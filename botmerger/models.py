# pylint: disable=no-name-in-module
"""Models for the BotMerger library."""
from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import Field

from botmerger.base import (
    MergedObject,
    SingleTurnHandler,
    SingleTurnContext,
    BotResponses,
    MessageContent,
    MessageType,
    BaseMessage,
)


class MergedParticipant(MergedObject):
    """A chat participant."""

    name: str
    is_human: bool


class MergedBot(MergedParticipant):
    """A bot that can interact with other bots."""

    is_human: bool = Field(False, const=True)

    alias: str
    description: Optional[str] = None

    # noinspection PyProtectedMember
    async def trigger(
        self,
        request: MessageType = None,
        sender: Optional["MergedParticipant"] = None,
        **kwargs,
    ) -> BotResponses:
        # TODO TODO TODO
        """
        Trigger this bot to respond to a message. Returns an object that can be used to retrieve the bot's
        response(s) in an asynchronous manner.
        """
        # pylint: disable=protected-access
        current_context = SingleTurnContext._current_context.get()
        # TODO override_sender + override_parent_ctx
        # TODO introduce default user
        if sender is None:
            sender = current_context.this_bot
        # if `request` is "plain" content, convert it to OriginalMessage, otherwise wrap it in ForwardedMessage
        request = await self.merger.create_next_message(
            thread_uuid=uuid4(),  # create a brand-new thread
            sender=sender,
            content=request,
            indicate_typing_afterwards=False,
            responds_to=None,
            goes_after=None,
            **kwargs,
        )
        return await self.merger.trigger_bot(self, request)

    async def get_final_response(
        self,
        request: MessageType = None,
        sender: Optional["MergedParticipant"] = None,
        **kwargs,
    ) -> Optional["MergedMessage"]:
        # TODO TODO TODO
        """Get the final response from the bot for a given request."""
        # TODO override_sender + override_parent_ctx
        responses = await self.trigger(request, sender=sender, **kwargs)
        return await responses.get_final_response()

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


class MergedUser(MergedParticipant):
    """A user that can interact with bots."""

    is_human: bool = Field(True, const=True)


class MergedMessage(BaseMessage, MergedObject):
    """A message that was sent in a channel."""

    sender: MergedParticipant
    indicate_typing_afterwards: bool
    parent_context: Optional["MergedMessage"]
    responds_to: Optional["MergedMessage"]
    goes_after: Optional["MergedMessage"]


class OriginalMessage(MergedMessage):
    """This subclass represents an original message. It implements `content` as a Pydantic field."""

    content: Union[str, Any]

    @property
    def original_sender(self) -> MergedParticipant:
        """For an original message, the original sender is the same as the sender."""
        return self.sender


class ForwardedMessage(MergedMessage):
    """
    This subclass represents a forwarded message. It implements `content` as a property that is delegated to the
    original message.
    """

    original_message: OriginalMessage

    @property
    def original_sender(self) -> MergedParticipant:
        """The original sender of the forwarded message."""
        return self.original_message.sender

    @property
    def content(self) -> MessageContent:
        """The content of the original message."""
        return self.original_message.content
