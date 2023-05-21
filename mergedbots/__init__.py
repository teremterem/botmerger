"""MergedBots package."""
from .core import FulfillmentFunc, MergedMessage, MergedBot
from .errors import MergedBotsError, ErrorWrapper

__all__ = [
    "ErrorWrapper",
    "FulfillmentFunc",
    "MergedBot",
    "MergedBotsError",
    "MergedMessage",
]
