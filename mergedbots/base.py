# pylint: disable=no-name-in-module
"""Base classes for the MergedBots library."""
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING
from typing import Callable, AsyncGenerator
from uuid import uuid4

from pydantic import BaseModel, UUID4, Field

if TYPE_CHECKING:
    from mergedbots.models import MergedBot, MergedUser, MergedMessage

# TODO recursively freeze all the MergedObject instances together with their contents after they are created

FulfillmentFunc = Callable[["MergedBot", "MergedMessage"], AsyncGenerator["MergedMessage", None]]


class BotManager(BaseModel, ABC):
    """An abstract factory of everything else in this library."""

    @abstractmethod
    async def fulfill(
        self, bot_handle: str, request: "MergedMessage", fallback_bot_handle: str = None
    ) -> AsyncGenerator["MergedMessage", None]:
        """
        Find a bot by its handle and fulfill a request using that bot. If the bot is not found and
        `fallback_bot_handle` is provided, then the fallback bot is used instead. If the fallback bot is not found
        either, then `BotNotFoundError` is raised.
        """

    @abstractmethod
    def create_bot(self, handle: str, name: str = None, **kwargs) -> "MergedBot":
        """Create a merged bot."""

    @abstractmethod
    async def create_bot_async(self, handle: str, name: str = None, **kwargs) -> "MergedBot":
        """Create a merged bot."""

    @abstractmethod
    async def find_bot(self, handle: str) -> "MergedBot":
        """Fetch a bot by its handle."""

    @abstractmethod
    async def find_or_create_user(
        self, channel_type: str, channel_specific_id: Any, user_display_name: str, **kwargs
    ) -> "MergedUser":
        """Find or create a user."""

    @abstractmethod
    async def get_full_conversion(
        self, conversation_tail: "MergedMessage", include_invisible_to_bots: bool = False
    ) -> list["MergedMessage"]:
        """Fetch the full conversation history up to the given message inclusively (`conversation_tail`)."""

    @abstractmethod
    async def create_originator_message(  # pylint: disable=too-many-arguments
        self,
        channel_type: str,
        channel_id: Any,
        originator: "MergedParticipant",
        content: str,
        is_visible_to_bots: bool = True,
        new_conversation: bool = False,
        **kwargs,
    ) -> "MergedMessage":
        """
        Create a new message from the conversation originator. The originator is typically a human user, but in
        certain scenarios it can also be another bot.
        """

    @abstractmethod
    async def create_bot_response(  # pylint: disable=too-many-arguments
        self,
        bot: "MergedBot",
        in_fulfillment_of: "MergedMessage",
        content: str,
        is_still_typing: bool,
        is_visible_to_bots: bool,
        **kwargs,
    ) -> "MergedMessage":
        """Create a bot response to `in_fulfillment_of` message."""


class MergedObject(BaseModel):
    """Base class for all MergedBots models."""

    # TODO how to prevent library consumers from instantiating these models directly ?

    class Config(BaseModel.Config):
        """Pydantic config."""

        # https://stackoverflow.com/a/72675163
        # TODO how not to forget to subclass this Config in child models should we need to define Config there too ?
        copy_on_model_validation = "none"

    manager: BotManager
    uuid: UUID4 = Field(default_factory=uuid4)
    custom_fields: dict[str, Any] = Field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        """Check if two models represent the same concept."""
        if not isinstance(other, MergedObject):
            return False
        return self.uuid == other.uuid

    def __hash__(self) -> int:
        """Get the hash of the model's uuid."""
        # TODO are we sure we don't want to keep these models non-hashable (pydantic default) ?
        return hash(self.uuid)


class MergedParticipant(MergedObject):
    """A chat participant."""

    name: str
    is_human: bool
