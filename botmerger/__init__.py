"""
BotMerger is a library for merging multiple bots into a single bot.
"""
from botmerger.base import BotMerger, BotResponses, SingleTurnContext, MessageContent
from botmerger.mergers import InMemoryBotMerger, YamlLogBotMerger
from botmerger.models import MergedParticipant, MergedBot, MergedUser, MergedMessage

__all__ = [
    "BotMerger",
    "BotResponses",
    "InMemoryBotMerger",
    "MergedBot",
    "MergedMessage",
    "MergedParticipant",
    "MergedUser",
    "MessageContent",
    "SingleTurnContext",
    "YamlLogBotMerger",
]
