# pylint: disable=no-name-in-module
"""Models for the BotMerger library."""
from typing import Any, Optional

from pydantic import Field

from botmerger.base import MergedObject, SingleTurnHandler, BotResponses, MessageContent


class MergedParticipant(MergedObject):
    """A chat participant."""

    name: str
    is_human: bool


class MergedBot(MergedParticipant):
    """A bot that can interact with other bots."""

    is_human: bool = Field(False, const=True)

    alias: str
    description: Optional[str] = None

    def trigger(self, request: "MergedMessage") -> BotResponses:
        """
        Trigger this bot to respond to a message. Returns an object that can be used to retrieve the bot's
        response(s) in an asynchronous manner.
        """
        return self.merger.trigger_bot(self, request)

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


class MergedChannel(MergedObject):
    """A logical channel where interactions between two or more participants happen."""

    channel_type: str
    channel_id: Any
    owner: MergedParticipant

    async def new_message_from_owner(self, content: MessageContent, **kwargs) -> "MergedMessage":
        """Create a new message in this channel from its owner."""
        return await self.new_message(sender=self.owner, content=content, **kwargs)

    async def new_message(self, sender: MergedParticipant, content: MessageContent, **kwargs) -> "MergedMessage":
        """Create a new message in this channel."""
        return await self.merger.create_message(
            channel=self,
            sender=sender,
            content=content,
            **kwargs,
        )


class BaseMessage:
    """
    Base class for messages. This is not a Pydantic model. `sender` and `content` are properties that must be
    implemented by subclasses one way or another (either as Pydantic fields or as properties).
    """

    sender: MergedParticipant
    content: MessageContent


class MergedMessage(BaseMessage, MergedObject):
    """A message that was sent in a channel."""

    channel: MergedChannel
    show_typing_afterwards: bool = False


class OriginalMessage(MergedMessage):
    """
    This subclass represents an original message. It implements `sender` and `content` as Pydantic fields.
    """

    sender: MergedParticipant
    content: MessageContent


class ForwardedMessage(MergedMessage):
    """
    This subclass represents a forwarded message. It implements `sender` and `content` as properties that are
    delegated to the original message.
    """

    original_message: OriginalMessage

    @property
    def sender(self) -> MergedParticipant:
        """The sender of the original message."""
        return self.original_message.sender

    @property
    def content(self) -> MessageContent:
        """The content of the original message."""
        return self.original_message.content


class MessageEnvelope:
    """TODO DELETE ME"""
