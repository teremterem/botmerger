# pylint: disable=protected-access,unused-argument
"""Tests for the `register_local_single_turn_responder` method of BotMerger."""
import asyncio

from mergedbots.botmerger.base import InteractionContext
from mergedbots.botmerger.core import InMemoryBotMerger


def test_register_local_single_turn_responder() -> None:
    """Test the `register_local_single_turn_responder` method."""
    merger = InMemoryBotMerger()

    assert not merger._single_turn_responders

    @merger.create_bot("test_bot")
    def _dummy_bot_func(context: InteractionContext) -> None:
        """Dummy bot function."""

    assert list(merger._single_turn_responders.values()) == [_dummy_bot_func]
    assert _dummy_bot_func.bot == asyncio.run(merger.find_bot("test_bot"))


def test_register_local_single_turn_responder_method() -> None:
    """Test the `register_local_single_turn_responder` method with a method."""
    merger = InMemoryBotMerger()

    assert not merger._single_turn_responders

    class DummyClass:
        """Dummy class."""

        async def _dummy_bot_method(self, context: InteractionContext) -> None:
            """Dummy bot method."""

    dummy_object = DummyClass()
    merger.create_bot("test_bot", single_turn=dummy_object._dummy_bot_method)

    assert list(merger._single_turn_responders.values()) == [dummy_object._dummy_bot_method]
