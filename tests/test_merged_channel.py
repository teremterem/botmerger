"""Tests for the `MergedChannel` class."""
import pytest

from botmerger import InMemoryBotMerger


@pytest.mark.asyncio
async def test_find_or_create_user_channel():
    """
    Test the `find_or_create_user_channel` method.
    - Assert that the same channel is returned when the same channel type and channel id are provided.
    - Assert that different channels are returned when different channel types or channel ids are provided.
    - Assert that the user is the same when the same channel is returned.
    - Assert that the users are different when different channels are returned.
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

    assert channel.sender == same_channel.sender
    assert channel.sender != another_channel.sender
    assert channel.sender != another_channel_type.sender
    assert another_channel.sender != another_channel_type.sender

    assert channel.extra_fields["channel_type"] == "channel type"
    assert channel.extra_fields["channel_id"] == 123
    assert channel.sender.name == "User Name"

    assert another_channel.extra_fields["channel_type"] == "channel type"
    assert another_channel.extra_fields["channel_id"] == 4321
    assert another_channel.sender.name == "another User Name"

    assert another_channel_type.extra_fields["channel_type"] == "channel type 2"
    assert another_channel_type.extra_fields["channel_id"] == 123
    assert another_channel_type.sender.name == "yet another User Name"
