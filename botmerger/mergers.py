"""Various concrete implementations of the BotMerger interface."""
# pylint: disable=no-name-in-module
from pathlib import Path
from typing import Any, Optional, Dict, Union

import yaml
from pydantic import UUID4

from botmerger.base import (
    MergedObject,
    ObjectKey,
    MergedSerializerVisitor,
)
from botmerger.core import BotMergerBase
from botmerger.models import MergedBot, MergedUser, MergedMessage, OriginalMessage, ForwardedMessage


class InMemoryBotMerger(BotMergerBase):
    """An in-memory object manager."""

    # TODO should in-memory implementation care about eviction of old objects ?

    def __init__(self) -> None:
        super().__init__()
        self._immutable_objects: Dict[ObjectKey, Any] = {}
        self._mutable_objects: Dict[UUID4, Any] = {}

    async def set_mutable_state(self, key: ObjectKey, state: Any) -> None:
        self._mutable_objects[key] = state

    async def get_mutable_state(self, key: ObjectKey) -> Optional[Any]:
        return self._mutable_objects.get(key)

    async def _register_immutable_object(self, key: ObjectKey, value: Any) -> None:
        self._immutable_objects[key] = value

    async def _get_immutable_object(self, key: ObjectKey) -> Optional[Any]:
        return self._immutable_objects.get(key)


class YamlLogBotMerger(InMemoryBotMerger):
    """A bot merger that logs all the objects to a YAML file."""

    def __init__(self, yaml_log_file: Union[str, Path]) -> None:
        super().__init__()
        self._yaml_log_file = yaml_log_file if isinstance(yaml_log_file, Path) else Path(yaml_log_file)
        self._yaml_serializer = YamlSerializer()

    async def _register_merged_object(self, obj: MergedObject) -> None:
        await super()._register_merged_object(obj)
        serialized_obj = self._yaml_serializer.serialize(obj)

        append_delimiter = self._yaml_log_file.exists() and self._yaml_log_file.stat().st_size > 0
        with self._yaml_log_file.open("a", encoding="utf-8") as file:
            if append_delimiter:
                file.write("\n---\n\n")
            yaml.dump(serialized_obj, file, allow_unicode=True, indent=4)


class YamlSerializer(MergedSerializerVisitor):
    """A YAML serializer for merged objects."""

    def _pre_serialize(self, obj: MergedObject, **kwargs) -> Dict[str, Any]:
        result = obj.dict(**kwargs)
        obj_uuid = result.pop("uuid")
        return {
            "_type": obj.__class__.__name__,
            "uuid": str(obj_uuid),
            **result,
        }

    def serialize_bot(self, obj: MergedBot) -> Dict[str, Any]:
        result = self._pre_serialize(obj)
        # TODO TODO TODO
        return result

    def serialize_user(self, obj: MergedUser) -> Dict[str, Any]:
        result = self._pre_serialize(obj)
        # TODO TODO TODO
        return result

    def _pre_serialize_message(self, obj: MergedMessage) -> Dict[str, Any]:
        result = self._pre_serialize(obj, exclude={"sender, receiver"})

        # TODO TODO TODO
        result.pop("parent_context")
        result.pop("responds_to")
        result.pop("goes_after")

        result["sender"] = {
            "uuid": str(obj.sender.uuid),
            "name": obj.sender.name,
            "is_human": obj.sender.is_human,
        }
        result["receiver"] = {
            "uuid": str(obj.receiver.uuid),
            "name": obj.receiver.name,
            "is_human": obj.receiver.is_human,
        }
        return result

    def serialize_original_message(self, obj: OriginalMessage) -> Dict[str, Any]:
        result = self._pre_serialize_message(obj)
        # TODO TODO TODO
        return result

    def serialize_forwarded_message(self, obj: ForwardedMessage) -> Dict[str, Any]:
        result = self._pre_serialize_message(obj)
        # TODO TODO TODO
        result.pop("original_message")
        return result
