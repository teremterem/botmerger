"""Tests for the `MergedChannel` class."""
import pytest

from botmerger.core import InMemoryBotMerger


@pytest.mark.asyncio
async def test_find_or_create_user_channel():
    # TODO TODO TODO
    """
    Test the `find_or_create_user_channel` method.
    - Assert that the same channel is returned when the same channel type and channel id are provided.
    - Assert that different channels are returned when different channel types or channel ids are provided.
    - Assert that the owner is the same when the same channel is returned.
    - Assert that the owner is different when different channels are returned.
    """
    merger = InMemoryBotMerger()

    channel = await merger.find_or_create_user_channel("channel type", 123, "User Name")
    same_channel = await merger.find_or_create_user_channel("channel type", 123, "User Name changed")
    another_channel = await merger.find_or_create_user_channel("channel type", 4321, "another User Name")
    another_channel_type = await merger.find_or_create_user_channel("channel type 2", 123, "yet another User Name")

    assert channel == same_channel
    assert channel != another_channel
    assert channel != another_channel_type
    assert another_channel != another_channel_type

    assert channel.owner == same_channel.owner
    assert channel.owner != another_channel.owner
    assert channel.owner != another_channel_type.owner
    assert another_channel.owner != another_channel_type.owner

    assert channel.channel_type == "channel type"
    assert channel.channel_id == 123
    assert channel.owner.name == "User Name"

    assert another_channel.channel_type == "channel type"
    assert another_channel.channel_id == 4321
    assert another_channel.owner.name == "another User Name"

    assert another_channel_type.channel_type == "channel type 2"
    assert another_channel_type.channel_id == 123
    assert another_channel_type.owner.name == "yet another User Name"
