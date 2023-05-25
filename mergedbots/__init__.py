"""MergedBots package."""
from .core import FulfillmentFunc, MergedMessage, MergedBot, MergedUser
from .errors import MergedBotsError, ErrorWrapper

__all__ = [
    "ErrorWrapper",
    "FulfillmentFunc",
    "MergedBot",
    "MergedBotsError",
    "MergedMessage",
    "MergedUser",
]
