"""
BotMerger is a library for merging multiple bots into a single bot.
"""
from botmerger.base import BotMerger, BotResponses, SingleTurnContext
from botmerger.core import InMemoryBotMerger
from botmerger.models import MergedParticipant, MergedBot, MergedUser, MergedChannel, MergedMessage, MessageEnvelope

__all__ = [
    "BotMerger",
    "BotResponses",
    "InMemoryBotMerger",
    "MergedBot",
    "MergedChannel",
    "MergedMessage",
    "MergedParticipant",
    "MergedUser",
    "MessageEnvelope",
    "SingleTurnContext",
]
