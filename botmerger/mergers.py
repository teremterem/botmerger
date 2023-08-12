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
from botmerger.models import MergedParticipant, MergedBot, MergedUser, MergedMessage, OriginalMessage, ForwardedMessage
from botmerger.utils import str_shorten


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
        if key in self._immutable_objects:
            # TODO move this check to the base class ?
            raise ValueError(f"Object with key {key} already exists.")
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
        serialized_obj = await self._yaml_serializer.serialize(obj)

        append_delimiter = self._yaml_log_file.exists() and self._yaml_log_file.stat().st_size > 0
        with self._yaml_log_file.open("a", encoding="utf-8") as file:
            if append_delimiter:
                file.write("\n---\n\n")
            yaml.dump(serialized_obj, file, allow_unicode=True, indent=4)


class YamlSerializer(MergedSerializerVisitor):
    """A YAML serializer for merged objects."""

    # TODO is this really YAML specific ? maybe it should be called something else ?

    async def serialize_bot(self, obj: MergedBot) -> Dict[str, Any]:
        return self._pre_serialize(obj, include={"uuid", "alias"})

    async def serialize_user(self, obj: MergedUser) -> Dict[str, Any]:
        return self._pre_serialize(obj, exclude={"is_human"})

    async def serialize_original_message(self, obj: OriginalMessage) -> Dict[str, Any]:
        return await self._pre_serialize_message(obj)

    async def serialize_forwarded_message(self, obj: ForwardedMessage) -> Dict[str, Any]:
        result = await self._pre_serialize_message(obj)
        self._add_related_msg_preview(result, "original_message", obj.original_message)
        return result

    async def _pre_serialize_message(self, obj: MergedMessage) -> Dict[str, Any]:
        result = self._pre_serialize(
            obj,
            exclude={
                "sender",
                "receiver",
                "original_message",
                "prev_msg_uuid",
                "requesting_msg_uuid",
                "parent_ctx_msg_uuid",
            },
        )
        if not result.get("still_thinking"):
            result.pop("still_thinking", None)
        if not result.get("invisible_to_bots"):
            result.pop("invisible_to_bots", None)

        def _repr_participant(participant: MergedParticipant) -> Dict[str, Any]:
            if isinstance(participant, MergedBot):
                return {
                    "uuid": str(participant.uuid),
                    "bot_alias": participant.alias,
                }
            if isinstance(participant, MergedUser):
                return {
                    "uuid": str(participant.uuid),
                    "human_name": participant.name,
                }
            raise ValueError(f"Unknown participant type: {type(participant)}")

        result["sender"] = _repr_participant(obj.sender)
        result["receiver"] = _repr_participant(obj.receiver)

        self._add_related_msg_preview(result, "previous_message", await obj.get_previous_message())
        self._add_related_msg_preview(result, "requesting_message", await obj.get_requesting_message())
        self._add_related_msg_preview(result, "parent_context", await obj.get_parent_context())

        return result

    @staticmethod
    def _add_related_msg_preview(
        result: Dict[str, Any], field_name: str, related_msg: Optional[MergedMessage]
    ) -> None:
        if not related_msg:
            return
        result[field_name] = {"uuid": str(related_msg.uuid), "preview": str_shorten(related_msg.content)}

    @staticmethod
    def _pre_serialize(obj: MergedObject, **kwargs) -> Dict[str, Any]:
        result = obj.dict(**kwargs, exclude_none=True)
        if not result.get("extra_fields"):
            result.pop("extra_fields", None)
        result["uuid"] = str(result["uuid"])
        result["_type"] = obj.__class__.__name__
        return result
