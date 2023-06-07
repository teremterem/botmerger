"""Tests for the `MergedObject` class."""
from mergedbots.botmerger.base import BotMerger, MergedObject
from mergedbots.botmerger.models import MergedBot


def test_merged_object() -> None:
    """Test the `MergedObject` class."""

    class TestMerger(BotMerger):
        """A test merger."""

        def create_bot(self, alias: str, name: str = None, **kwargs) -> MergedBot:
            """Create a merged bot while outside an async context."""

        async def create_bot_async(self, alias: str, name: str = None, **kwargs) -> MergedBot:
            """Create a merged bot while inside an async context."""

        async def find_bot(self, alias: str) -> MergedBot:
            """Fetch a bot by its alias."""

    merger = TestMerger()
    obj1 = MergedObject(merger=merger)
    obj2 = MergedObject(merger=merger)
    assert obj1 != obj2
    assert hash(obj1) == hash(obj1)
    assert hash(obj1) != hash(obj2)
    assert obj1.merger is merger
    assert obj1.uuid != obj2.uuid
    assert obj1.extra_fields == {}
    assert obj2.extra_fields == {}
    assert obj1.extra_fields is not obj2.extra_fields
    # TODO assert obj1.dict() == {"uuid": obj1.uuid, "extra_fields": {}}
    assert MergedObject(merger=merger, extra_fields={"test": "test"}).extra_fields == {"test": "test"}
