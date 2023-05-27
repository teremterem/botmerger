"""MergedBots package."""
from .core import BotManager, ObjectManager, InMemoryObjectManager
from .errors import MergedBotsError, ErrorWrapper
from .models import FulfillmentFunc, MergedMessage, MergedBot, MergedUser

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
