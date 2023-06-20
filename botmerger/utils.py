"""Utility functions for BotMerger library."""
import traceback
from typing import Generator


def get_text_chunks(text: str, chunk_size: int) -> Generator[str, None, None]:
    """Split text into chunks of size chunk_size."""
    return (text[i : i + chunk_size] for i in range(0, len(text), chunk_size))


def format_error_with_full_tb(error: BaseException) -> str:
    """Format an error for display to the user."""
    return "".join(traceback.format_exception(type(error), error, error.__traceback__))
