# pylint: disable=protected-access,unused-argument
"""Tests for the `register_local_single_turn_handler` method of BotMerger."""
import asyncio

from mergedbots.botmerger.base import SingleTurnContext
from mergedbots.botmerger.core import InMemoryBotMerger


def test_register_local_single_turn_handler() -> None:
    """Test the `register_local_single_turn_handler` method."""
    merger = InMemoryBotMerger()

    assert not merger._single_turn_handlers

    @merger.create_bot("test_bot")
    def _dummy_bot_func(context: SingleTurnContext) -> None:
        """Dummy bot function."""

    assert list(merger._single_turn_handlers.values()) == [_dummy_bot_func]
    assert _dummy_bot_func.bot == asyncio.run(merger.find_bot("test_bot"))


def test_register_local_single_turn_handler_method() -> None:
    """Test the `register_local_single_turn_handler` method with a method."""
    merger = InMemoryBotMerger()

    assert not merger._single_turn_handlers

    class DummyClass:
        """Dummy class."""

        async def _dummy_bot_method(self, context: SingleTurnContext) -> None:
            """Dummy bot method."""

    dummy_object = DummyClass()
    merger.create_bot("test_bot", single_turn=dummy_object._dummy_bot_method)

    assert list(merger._single_turn_handlers.values()) == [dummy_object._dummy_bot_method]
