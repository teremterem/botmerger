"""Tests for the `MergedBot` class."""
from botmerger import InMemoryBotMerger


def test_merged_bot() -> None:
    """Test the `MergedBot` class."""
    bot = InMemoryBotMerger().create_bot("test", description="test description")
    assert bot.alias == "test"
    assert bot.name == "test"
    assert bot.description == "test description"
    assert bot.is_human is False


def test_merged_bot_with_name() -> None:
    """Test the `MergedBot` class with a name."""
    bot = InMemoryBotMerger().create_bot("test", name="test name")
    assert bot.alias == "test"
    assert bot.name == "test name"
    assert bot.description is None
    assert bot.is_human is False
