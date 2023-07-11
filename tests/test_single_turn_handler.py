# pylint: disable=protected-access,unused-argument
"""Tests for the `register_local_single_turn_handler` method of BotMerger."""
import asyncio
from unittest.mock import MagicMock

import pytest

from botmerger.base import SingleTurnContext
from botmerger.core import InMemoryBotMerger
from botmerger.errors import BotAliasTakenError, ErrorWrapper


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


@pytest.mark.asyncio
async def test_trigger_bot() -> None:
    """Test the `trigger_bot` method."""
    merger = InMemoryBotMerger()

    call_mock = MagicMock()
    call_mock.assert_not_called()

    @(await merger.create_bot_async("test_bot"))
    async def _dummy_bot_func(context: SingleTurnContext) -> None:
        """Dummy bot function."""
        call_mock()
        await context.yield_interim_response("response 1")
        call_mock()
        await context.yield_interim_response("response 2")
        call_mock()
        await context.yield_final_response({"response": "3"})
        call_mock()

    responses = await _dummy_bot_func.bot.trigger("test request")

    call_mock.assert_not_called()
    assert not responses.responses_so_far

    await anext(responses)

    # even though we only requested one response all responses were calculated already (the rest are in the queue)
    assert call_mock.call_count == 4
    assert len(responses.responses_so_far) == 1

    assert len(await responses.get_all_responses()) == 3
    assert call_mock.call_count == 4
    assert len(responses.responses_so_far) == 3

    # check that calling `get_all_responses` again does not cause any exceptions and does not change any state
    assert len(await responses.get_all_responses()) == 3
    assert call_mock.call_count == 4
    assert len(responses.responses_so_far) == 3


@pytest.mark.asyncio
async def test_trigger_bot_exception() -> None:
    """Test the `trigger_bot` method when the bot raises an exception."""
    merger = InMemoryBotMerger()

    call_mock = MagicMock()
    call_mock.assert_not_called()

    @(await merger.create_bot_async("test_bot"))
    async def _dummy_bot_func(context: SingleTurnContext) -> None:
        """Dummy bot function."""
        call_mock()
        await context.yield_final_response("response 1")
        call_mock()
        raise ValueError("test")

    responses = await _dummy_bot_func.bot.trigger("test request")

    call_mock.assert_not_called()
    assert not responses.responses_so_far

    await anext(responses)

    # even though we only requested one response all responses were calculated already (the rest are in the queue)
    assert call_mock.call_count == 2
    assert len(responses.responses_so_far) == 1

    with pytest.raises(ErrorWrapper) as exc_info:
        await responses.get_all_responses()
    assert isinstance(exc_info.value.error, ValueError)

    assert call_mock.call_count == 2
    assert len(responses.responses_so_far) == 1
