"""Tests for the MergedMessage subclasses."""
from botmerger import MergedUser, MergedChannel, InMemoryBotMerger
from botmerger.models import ForwardedMessage, OriginalMessage


def test_original_and_forwarded_message() -> None:
    """Test the `OriginalMessage` and `ForwardedMessage` models."""
    merger = InMemoryBotMerger()
    merged_user = MergedUser(
        merger=merger,
        name="name of the user",
    )
    merged_channel = MergedChannel(
        merger=merger,
        channel_type="channel_type",
        channel_id="channel_id",
        owner=merged_user,
    )

    original_message = OriginalMessage(
        merger=merger,
        channel=merged_channel,
        sender=merged_user,
        content="some content",
    )
    original_message_dict = original_message.dict()
    assert "sender" in original_message_dict
    assert original_message_dict["content"] == "some content"

    forwarded_message = ForwardedMessage(
        merger=merger,
        channel=merged_channel,
        original_message=original_message,
    )
    assert forwarded_message.sender.uuid == merged_user.uuid
    assert forwarded_message.content == "some content"
    forwarded_message_dict = forwarded_message.dict()
    assert "sender" not in forwarded_message_dict
    assert "content" not in forwarded_message_dict
