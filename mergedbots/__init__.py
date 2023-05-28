"""MergedBots package."""
from mergedbots.core import (
    BotManager,
    FulfillmentFunc,
    InMemoryBotManager,
    MergedBot,
    MergedMessage,
    MergedUser,
)
from mergedbots.errors import ErrorWrapper, MergedBotsError

__all__ = [
    "BotManager",
    "ErrorWrapper",
    "FulfillmentFunc",
    "InMemoryBotManager",
    "MergedBot",
    "MergedBotsError",
    "MergedMessage",
    "MergedUser",
]
