"""Tests for the `MergedBot` class."""
from mergedbots.botmerger.core import InMemoryBotMerger


def test_merged_bot() -> None:
    """Test the `MergedBot` class."""
    bot = InMemoryBotMerger().create_bot("test", description="test description")
    assert bot.alias == "test"
    assert bot.name == "test"
    assert bot.description == "test description"
    assert bot.is_human is False
