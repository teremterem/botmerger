"""Utility functions for MergedBots library."""
import traceback
from typing import Generator, Any


def get_text_chunks(text: str, chunk_size: int) -> Generator[str, None, None]:
    """Split text into chunks of size chunk_size."""
    return (text[i : i + chunk_size] for i in range(0, len(text), chunk_size))


def format_error_with_full_tb(error: BaseException) -> str:
    """Format an error for display to the user."""
    return "".join(traceback.format_exception(type(error), error, error.__traceback__))


def generate_merged_bot_key(handle: str) -> tuple[str, str]:
    """Generate a key for a bot."""
    return "bot_handle", handle


def generate_merged_user_key(channel_type: str, channel_specific_id: Any) -> tuple[str, str, str]:
    """Generate a key for a user."""
    return "user_id", channel_type, channel_specific_id


def assert_correct_obj_type_or_none(obj: Any, expected_type: type, key: Any) -> None:
    """Assert that the object is of the expected type or None."""
    if obj and not isinstance(obj, expected_type):
        raise TypeError(
            f"wrong type of object by the key {key!r}: "
            f"expected {expected_type.__name__!r}, got {type(obj).__name__!r}",
        )
