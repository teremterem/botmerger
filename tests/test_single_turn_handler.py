# pylint: disable=protected-access,unused-argument
"""Tests for the `register_local_single_turn_handler` method of BotMerger."""
import asyncio

import pytest

from mergedbots.botmerger.base import SingleTurnContext
from mergedbots.botmerger.core import InMemoryBotMerger
from mergedbots.botmerger.errors import BotAliasTakenError


def test_register_local_single_turn_handlers() -> None:
    """Test the `register_local_single_turn_handler` method."""
    merger = InMemoryBotMerger()

    assert not merger._single_turn_handlers

    @merger.create_bot("test_bot")
    def _dummy_bot_func(context: SingleTurnContext) -> None:
        """Dummy bot function."""

    assert _dummy_bot_func.bot == asyncio.run(merger.find_bot("test_bot"))
    assert merger._single_turn_handlers == {_dummy_bot_func.bot.uuid: _dummy_bot_func}

    @merger.create_bot("test_bot2")
    def _dummy_bot_func2(context: SingleTurnContext) -> None:
        """Dummy bot function 2."""

    assert _dummy_bot_func.bot == asyncio.run(merger.find_bot("test_bot"))
    assert _dummy_bot_func2.bot == asyncio.run(merger.find_bot("test_bot2"))
    assert merger._single_turn_handlers == {
        _dummy_bot_func.bot.uuid: _dummy_bot_func,
        _dummy_bot_func2.bot.uuid: _dummy_bot_func2,
    }


def test_register_same_bot_alias_twice() -> None:
    """Test the `register_local_single_turn_handler` method when the same bot alias is used twice."""
    merger = InMemoryBotMerger()

    assert not merger._single_turn_handlers

    @merger.create_bot("test_bot")
    def _dummy_bot_func(context: SingleTurnContext) -> None:
        """Dummy bot function."""

    assert _dummy_bot_func.bot == asyncio.run(merger.find_bot("test_bot"))
    assert merger._single_turn_handlers == {_dummy_bot_func.bot.uuid: _dummy_bot_func}

    with pytest.raises(BotAliasTakenError):

        @merger.create_bot("test_bot")
        def _dummy_bot_func2(context: SingleTurnContext) -> None:
            """Dummy bot function 2."""

    assert _dummy_bot_func.bot == asyncio.run(merger.find_bot("test_bot"))
    assert merger._single_turn_handlers == {_dummy_bot_func.bot.uuid: _dummy_bot_func}


def test_register_local_single_turn_handler_method() -> None:
    """Test the `register_local_single_turn_handler` method with a method."""
    merger = InMemoryBotMerger()

    assert not merger._single_turn_handlers

    class DummyClass:
        """Dummy class."""

        async def _dummy_bot_method(self, context: SingleTurnContext) -> None:
            """Dummy bot method."""

    dummy_object = DummyClass()
    test_bot = merger.create_bot("test_bot", single_turn=dummy_object._dummy_bot_method)

    assert merger._single_turn_handlers == {test_bot.uuid: dummy_object._dummy_bot_method}
