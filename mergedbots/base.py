# pylint: disable=no-name-in-module
"""Base classes for the MergedBots library."""
from abc import ABC, abstractmethod
from typing import Callable, AsyncGenerator
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from mergedbots.models import MergedMessage

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
