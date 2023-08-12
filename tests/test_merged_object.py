"""Tests for the `MergedObject` class."""
from typing import Any

import pytest
from pydantic import ValidationError

from botmerger import MergedObject, InMemoryBotMerger
from botmerger.base import MergedSerializerVisitor


class SomeMergedObject(MergedObject):
    """A subclass of `MergedObject` for testing."""

    async def _serialize(self, visitor: MergedSerializerVisitor) -> Any:
        """Empty serialization method to make the class concrete."""


def test_merged_object() -> None:
    """Test the `MergedObject` class."""
    merger = InMemoryBotMerger()
    obj1 = SomeMergedObject(merger=merger)
    obj2 = SomeMergedObject(merger=merger)
    assert obj1 != obj2
    assert hash(obj1) == hash(obj1)
    assert hash(obj1) != hash(obj2)
    assert obj1.merger is merger
    assert obj1.uuid != obj2.uuid
    assert obj1.extra_fields == {}
    assert obj2.extra_fields == {}
    assert obj1.extra_fields is not obj2.extra_fields
    # TODO assert obj1.dict() == {"uuid": obj1.uuid, "extra_fields": {}}
    assert SomeMergedObject(merger=merger, extra_fields={"test": "test"}).extra_fields == {"test": "test"}


def test_merged_object_without_merger() -> None:
    """Test the `MergedObject` class without a merger."""
    with pytest.raises(ValidationError):
        SomeMergedObject()
