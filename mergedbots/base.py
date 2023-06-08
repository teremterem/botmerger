# pylint: disable=no-name-in-module
"""Base classes for the MergedBots library."""
from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING
from typing import Callable, AsyncGenerator

from pydantic import BaseModel

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
