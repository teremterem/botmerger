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


class MergedMessage(MergedObject):
    """A message that can be sent by a bot or a user."""

    channel: MergedChannel

    sender: MergedParticipant
    content: MessageContent


class MessageEnvelope:
    """
    A volatile packaging for a message. "Volatile" means that the envelope itself is not persisted by
    BotMerger (only the message is).

    :param message: the message in this envelope
    :param show_typing_indicator: whether to show a typing indicator after this message is dispatched (and
           until the next message)
    """

    def __init__(self, message: MergedMessage, show_typing_indicator: bool = False):
        self.message = message
        self.show_typing_indicator = show_typing_indicator