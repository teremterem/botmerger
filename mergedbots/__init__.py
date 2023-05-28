"""MergedBots package."""
from mergedbots.core import (
    BotManager,
    FulfillmentFunc,
    InMemoryObjectManager,
    MergedBot,
    MergedMessage,
    ObjectManager,
    MergedUser,
)
from mergedbots.errors import ErrorWrapper, MergedBotsError

__all__ = [
    "BotManager",
    "ErrorWrapper",
    "FulfillmentFunc",
    "InMemoryObjectManager",
    "MergedBot",
    "MergedBotsError",
    "MergedMessage",
    "ObjectManager",
    "MergedUser",
]
