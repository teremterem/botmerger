# pylint: disable=no-name-in-module
"""Models for the BotMerger library."""
from typing import Any, Union, Tuple, Optional

from pydantic import Field, BaseModel

from mergedbots.botmerger.base import MergedObject, SingleTurnHandler


class MergedParticipant(MergedObject):
    """A chat participant."""

    name: str
    is_human: bool


class MergedBot(MergedParticipant):
    """A bot that can interact with other bots."""

    is_human: bool = Field(False, const=True)

    alias: str
    description: Optional[str] = None

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

    parent_channel: Optional["MergedChannel"] = None
    originator_channel: Optional["MergedChannel"] = None


class MergedMessage(MergedObject):
    """A message that can be sent by a bot or a user."""

    channel: MergedChannel

    sender: MergedParticipant
    content: Union[str, Any]
    is_visible_to_bots: bool


class MessageEnvelope(BaseModel):
    """
    A volatile packaging for one or more messages. "Volatile" means that the envelope itself is not persisted by
    BotMerger (only the messages are).

    :param messages: the messages in this envelope
    :param show_typing_indicator: whether to show a typing indicator after these messages are dispatched (and
           until the next response) TODO improve this description
    """

    messages: Tuple[MergedMessage, ...]
    show_typing_indicator: bool
