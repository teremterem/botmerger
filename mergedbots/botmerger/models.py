# pylint: disable=no-name-in-module
"""Models for the BotMerger library."""
from typing import Any, Union, Tuple, Optional

from pydantic import Field, BaseModel

from mergedbots.botmerger.base import MergedObject


class MergedParticipant(MergedObject):
    """A chat participant."""

    name: str
    is_human: bool


class MergedBot(MergedParticipant):
    """A bot that can interact with other bots."""

    is_human: bool = Field(False, const=True)

    alias: str
    description: Optional[str] = None


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
    :param show_typing_afterwards: whether to show a typing indicator after these messages are dispatched (and until
           the next "transmission")
    """

    messages: Tuple[MergedMessage, ...]
    show_typing_afterwards: bool
