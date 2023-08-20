# pylint: disable=no-name-in-module
"""Various concrete implementations of the BotMerger interface."""
import asyncio
from pathlib import Path
from typing import Any, Optional, Dict, Union
from uuid import UUID

import yaml
from pydantic import UUID4

from botmerger.base import (
    MergedObject,
    ObjectKey,
    MergedSerializerVisitor,
    BotMerger,
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

    def __init__(self, yaml_log_file: Union[str, Path], serialization_enabled: bool = True) -> None:
        super().__init__()
        self._yaml_log_file = yaml_log_file if isinstance(yaml_log_file, Path) else Path(yaml_log_file)
        self._non_empty_yaml_log_exists = self._yaml_log_file.exists() and self._yaml_log_file.stat().st_size > 0
        self._yaml_serializer = YamlSerializer()

        # TODO don't just disable serialization temporarily, find a better way to prevent it upon loading serialized
        #  objects
        self._serialization_enabled = False

        if self._non_empty_yaml_log_exists:
            # TODO decide if it is a bad hack or not (because of this `run` merger can only be constructed before
            #  event loop is created)
            asyncio.run(self._read_existing_yaml_log())

        self._serialization_enabled = serialization_enabled

    async def _read_existing_yaml_log(self) -> None:
        with self._yaml_log_file.open("r", encoding="utf-8") as file:
            for obj in yaml.safe_load_all(file):
                await self._yaml_serializer.deserialize_object(self, obj)

    async def _register_merged_object(self, obj: MergedObject) -> None:
        await super()._register_merged_object(obj)
        if not self._serialization_enabled:
            return

        serialized_obj = await self._yaml_serializer.serialize(obj)

        self._yaml_log_file.parent.mkdir(parents=True, exist_ok=True)
        with self._yaml_log_file.open("a", encoding="utf-8") as file:
            if self._non_empty_yaml_log_exists:
                file.write("\n---\n\n")
            yaml.dump(serialized_obj, file, allow_unicode=True, indent=4)
            self._non_empty_yaml_log_exists = True


class YamlSerializer(MergedSerializerVisitor):
    """A YAML serializer for merged objects."""

    # TODO is this really YAML specific ? maybe it should be called something else ?
    # TODO don't list each field individually during deserialization, exclude the special ones (process them
    #  separately) and then feed the rest into the merged objects in one go

    async def deserialize_object(self, merger: BotMerger, obj: Dict[str, Any]) -> None:
        obj_type = obj.pop("_type")
        if obj_type == "MergedBot":
            await self.deserialize_bot(merger, obj)
        elif obj_type == "MergedUser":
            await self.deserialize_user(merger, obj)
        elif obj_type == "OriginalMessage":
            await self.deserialize_original_message(merger, obj)
        elif obj_type == "ForwardedMessage":
            await self.deserialize_forwarded_message(merger, obj)
        else:
            raise ValueError(f"Unknown object type: {obj_type}")

    async def serialize_bot(self, obj: MergedBot) -> Dict[str, Any]:
        return self._pre_serialize(obj, include={"uuid", "alias"})

    async def deserialize_bot(self, merger: BotMerger, obj: Dict[str, Any]) -> None:
        # TODO when a bot with the same alias is created, make sure to merge it with the loaded one
        bot = MergedBot(
            merger=merger,
            uuid=UUID(obj["uuid"]),
            alias=obj["alias"],
            # TODO this is a hack until I figure out how to merge loaded bots with ones that are being set up
            name=obj["alias"],
        )
        # TODO solve the following problem - the method below belongs to BotMergerBase class, not to BotMerger
        await merger._register_bot(bot)

    async def serialize_user(self, obj: MergedUser) -> Dict[str, Any]:
        return self._pre_serialize(obj, exclude={"is_human"})

    async def deserialize_user(self, merger: BotMerger, obj: Dict[str, Any]) -> None:
        # TODO is it a bad idea to pop keys out of the original dictionary that was passed ?
        user_uuid = UUID(obj.pop("uuid"))
        user = MergedUser(merger=merger, uuid=user_uuid, **obj)
        # TODO solve the following problem - the method below belongs to BotMergerBase class, not to BotMerger
        await merger._register_merged_object(user)

    async def serialize_original_message(self, obj: OriginalMessage) -> Dict[str, Any]:
        return await self._pre_serialize_message(obj)

    async def deserialize_original_message(self, merger: BotMerger, obj: Dict[str, Any]) -> None:
        # TODO is it a bad idea to pop keys out of the original dictionary that was passed ?
        msg_uuid = UUID(obj.pop("uuid"))
        sender_uuid = UUID(obj.pop("sender")["uuid"])
        receiver_uuid = UUID(obj.pop("receiver")["uuid"])
        prev_msg_uuid = UUID(obj.pop("previous_message")["uuid"]) if obj.get("previous_message") else None
        requesting_msg_uuid = UUID(obj.pop("requesting_message")["uuid"]) if obj.get("requesting_message") else None
        parent_ctx_msg_uuid = UUID(obj.pop("parent_context")["uuid"]) if obj.get("parent_context") else None
        still_thinking = obj.pop("still_thinking") if obj.get("still_thinking") else False
        # TODO solve the following problem - `_get_correct_object` belongs to BotMergerBase class, not to BotMerger
        message = OriginalMessage(
            merger=merger,
            uuid=msg_uuid,
            sender=await merger._get_correct_object(sender_uuid, MergedParticipant),
            receiver=await merger._get_correct_object(receiver_uuid, MergedParticipant),
            prev_msg_uuid=prev_msg_uuid,
            requesting_msg_uuid=requesting_msg_uuid,
            parent_ctx_msg_uuid=parent_ctx_msg_uuid,
            still_thinking=still_thinking,
            **obj,
        )
        # TODO solve the following problem - the methods below belong to BotMergerBase class, not to BotMerger
        await merger._register_message(message)

        # TODO do not explicitly rely on the presence of the `channel_type` and `channel_id` fields explicitly ?
        #  support more generic serialization/deserialization at the level of `_register_immutable_object` instead ?
        channel_type = message.extra_fields.get("channel_type")
        channel_id = message.extra_fields.get("channel_id")
        if channel_type and channel_id:
            key = merger._generate_channel_key(channel_type=channel_type, channel_id=channel_id)
            await merger._register_immutable_object(key, message.uuid)

    async def serialize_forwarded_message(self, obj: ForwardedMessage) -> Dict[str, Any]:
        result = await self._pre_serialize_message(obj)
        self._add_related_msg_preview(result, "original_message", obj.original_message)
        return result

    async def deserialize_forwarded_message(self, merger: BotMerger, obj: Dict[str, Any]) -> None:
        # TODO get rid of duplicate code
        # TODO is it a bad idea to pop keys out of the original dictionary that was passed ?
        msg_uuid = UUID(obj.pop("uuid"))
        original_msg_uuid = UUID(obj.pop("original_message")["uuid"])
        sender_uuid = UUID(obj.pop("sender")["uuid"])
        receiver_uuid = UUID(obj.pop("receiver")["uuid"])
        prev_msg_uuid = UUID(obj.pop("previous_message")["uuid"]) if obj.get("previous_message") else None
        requesting_msg_uuid = UUID(obj.pop("requesting_message")["uuid"]) if obj.get("requesting_message") else None
        parent_ctx_msg_uuid = UUID(obj.pop("parent_context")["uuid"]) if obj.get("parent_context") else None
        still_thinking = obj.pop("still_thinking") if obj.get("still_thinking") else False
        # TODO solve the following problem - `_get_correct_object` belongs to BotMergerBase class, not to BotMerger
        message = ForwardedMessage(
            merger=merger,
            uuid=msg_uuid,
            original_message=await merger.find_message(original_msg_uuid),
            sender=await merger._get_correct_object(sender_uuid, MergedParticipant),
            receiver=await merger._get_correct_object(receiver_uuid, MergedParticipant),
            prev_msg_uuid=prev_msg_uuid,
            requesting_msg_uuid=requesting_msg_uuid,
            parent_ctx_msg_uuid=parent_ctx_msg_uuid,
            still_thinking=still_thinking,
            **obj,
        )
        # TODO solve the following problem - the method below belongs to BotMergerBase class, not to BotMerger
        await merger._register_message(message)

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
        if not result.get("hidden_from_history"):
            result.pop("hidden_from_history", None)

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
