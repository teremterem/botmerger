"""MergedBots package."""
from .core import BotManager, InMemoryObjectManager
from .errors import MergedBotsError, ErrorWrapper
from .models import FulfillmentFunc, MergedMessage, MergedBot, MergedUser, ObjectManager

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
