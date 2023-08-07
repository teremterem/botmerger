# pylint: disable=no-name-in-module,too-many-arguments
"""Base classes for the BotMerger library."""
from abc import ABC, abstractmethod
from asyncio import Queue, Lock
from collections import abc
from contextvars import ContextVar
from contextvars import Token
from typing import (
    Any,
    TYPE_CHECKING,
    Optional,
    Dict,
    Callable,
    Awaitable,
    Union,
    List,
    Tuple,
    Iterable,
    AsyncIterable,
)
from uuid import uuid4, UUID

from pydantic import BaseModel, UUID4, Field

from botmerger.errors import ErrorWrapper

if TYPE_CHECKING:
    from botmerger.models import MergedBot, MergedMessage, MergedParticipant, MergedUser

SingleTurnHandler = Callable[["SingleTurnContext"], Awaitable[None]]
MessageContent = Union[str, BaseModel, Any]  # a string, a Pydantic model, a dataclass or a json-serializable object
MessageType = Union["MergedMessage", MessageContent]
ObjectKey = Union[UUID4, Tuple[Any, ...]]


class BotMerger(ABC):
    """
    An abstract factory of everything else in this library and also the low level implementation of everything else
    in this library. Almost all the methods of almost all the other classes in this library are just a facade for
    methods of this class.
    """

    DEFAULT_USER_UUID = UUID("440633de-aac2-41ae-80aa-7bbf1be7591b")
    DEFAULT_MSG_CTX_UUID = UUID("0cff89d8-14a8-49c5-92c5-e5a6445bdb6c")

    DEFAULT_USER_NAME = "USER"
    DEFAULT_MSG_CTX_CONTENT = "DEFAULT MESSAGE CONTEXT"

    async def get_default_user(self) -> "MergedUser":
        """Get the default user."""

    async def get_default_msg_ctx(self) -> "MergedMessage":
        """Get the default message context."""

    @abstractmethod
    def trigger_bot(
        self,
        bot: "MergedBot",
        request: Optional[Union[MessageType, "BotResponses"]] = None,
        requests: Optional[Iterable[Union[MessageType, "BotResponses"]]] = None,
        override_sender: Optional["MergedParticipant"] = None,
        override_parent_ctx: Optional["MergedMessage"] = None,
        rewrite_cache: bool = False,
        **kwargs,
    ) -> "BotResponses":
        """
        Find a bot by its alias and trigger this bot to respond to a message or messages. Returns an object that can
        be used to retrieve the bot's response(s) in an asynchronous manner.
        """

    @abstractmethod
    def create_bot(
        self,
        alias: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        no_cache: bool = False,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> "MergedBot":
        """
        Create a bot. This version of bot creation function is meant to be called outside an async context (for ex.
        as a decorator to single-turn and multi-turn handler functions).
        """

    @abstractmethod
    async def create_bot_async(
        self,
        alias: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        no_cache: bool = False,
        single_turn: Optional[SingleTurnHandler] = None,
        **kwargs,
    ) -> "MergedBot":
        """Create a bot while inside an async context."""

    @abstractmethod
    def register_local_single_turn_handler(self, bot: "MergedBot", handler: SingleTurnHandler) -> None:
        """Register a local function as a single turn handler for a bot."""

    @abstractmethod
    async def find_bot(self, alias: str) -> "MergedBot":
        """Fetch a bot by its alias."""

    @abstractmethod
    async def find_or_create_user_channel(
        self,
        channel_type: str,
        channel_id: Any,
        user_display_name: str,
    ) -> "MergedMessage":
        """
        Find or create a channel with a user as its owner. The channel is represented by a MergedMessage object that
        will serve as parent context for other MergedMessage objects (actual messages that are sent by the user
        via this channel). Parameters `channel_type` and `channel_specific_id` are used to look up the channel.
        Parameter `user_display_name` is used to create a user if the channel does not exist and is ignored if the
        channel already exists.
        """

    @abstractmethod
    async def create_user(self, name: str, **kwargs) -> "MergedUser":
        """Create a user."""

    @abstractmethod
    async def create_next_message(
        self,
        content: "MessageType",
        still_thinking: Optional[bool],
        sender: Optional["MergedParticipant"],
        receiver: "MergedParticipant",
        parent_context: Optional["MergedMessage"],
        responds_to: Optional["MergedMessage"] = None,
        **kwargs,
    ) -> "MergedMessage":
        """
        Create a message in a given channel that goes after the last message in a given thread. If `content` is
        another `MergedMessage` instance, then `ForwardedMessage` will be created instead of `OriginalMessage`.
        """

    @abstractmethod
    async def find_message(self, uuid: UUID4) -> "MergedMessage":
        """Find a message by its uuid."""

    @abstractmethod
    async def set_mutable_state(self, key: ObjectKey, state: Any) -> None:
        """Set a mutable state associated with a given key."""

    @abstractmethod
    async def get_mutable_state(self, key: ObjectKey) -> Optional[Any]:
        """Get a mutable state associated with a given key."""


class MergedObject(BaseModel):
    """
    Base class for all BotMerger models. All the child classes of this class are meant to be immutable. Whatever
    mutable state one needs to associate with these objects should not be stored in the objects directly. Instead,
    such state should be stored at and dynamically looked up via BotMerger instance these objects belong to. This
    should simplify implementation of a distributed deployment of a network of BotMerger instances each with their
    own bots and which interact with each other.

    ATTENTION! Models inheriting from this class should not be instantiated directly. Use the factory methods of
    `BotMerger` instead.
    """

    class Config(BaseModel.Config):
        """
        ATTENTION AGAIN! If you define a new config for a model inheriting from this class, make sure to inherit from
        this config as well.
        """

        allow_mutation = False
        copy_on_model_validation = "none"
        arbitrary_types_allowed = True

    merger: BotMerger
    # TODO replace uuid with something that also includes the id of the BotMerger instance this object belongs to
    uuid: UUID4 = Field(default_factory=uuid4)
    # TODO freeze the contents of `extra_data` upon model creation recursively
    # TODO validate that all values in `extra_fields` are json-serializable
    extra_fields: Dict[str, Any] = Field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        """Check if two models represent the same concept."""
        if not isinstance(other, MergedObject):
            return False
        return self.uuid == other.uuid

    def __hash__(self) -> int:
        """The hash of the model is the hash of its uuid."""
        return hash(self.uuid)


class BaseMessage:
    """
    Base class for messages. This is not a Pydantic model. `content` is property that must be implemented by
    subclasses one way or another (either as a Pydantic field or as a property).
    """

    content: Union[str, Any]
    original_message: "MergedMessage"


class BotResponses:
    """
    A class that represents a stream of responses from a bot. It is an async iterator that yields `MergedMessage`
    objects. It also has a method `get_all_responses` that will block until all the responses are received and then
    return them as a list.
    """

    _END_OF_RESPONSES = object()

    def __init__(self) -> None:
        self.responses_so_far: List["MergedMessage"] = []
        self._response_queue: Optional[Queue[Union["MergedMessage", object, Exception, "BotResponses"]]] = Queue()
        self._error: Optional[ErrorWrapper] = None
        self._cached_bot_response_iterator: Optional[BotResponses._Iterator] = None
        self._lock = Lock()

    def __aiter__(self) -> "BotResponses._Iterator":
        return BotResponses._Iterator(self)

    async def get_all_responses(self) -> List["MergedMessage"]:
        """Wait until all the responses are received and return them as a list."""
        # make sure all responses are fetched
        async for _ in self:
            pass
        return self.responses_so_far

    async def get_final_response(self) -> Optional["MergedMessage"]:
        """Wait until all the responses are received and return the last one or None if there are no responses."""
        responses = await self.get_all_responses()
        return responses[-1] if responses else None

    async def _wait_for_next_response(self) -> "MergedMessage":
        if self._cached_bot_response_iterator is not None:
            # we are yielding responses from a cached BotResponses instance
            response = await anext(self._cached_bot_response_iterator)
        else:
            if self._error:
                raise self._error

            if self._response_queue is None:
                raise StopAsyncIteration

            response = await self._response_queue.get()

            if isinstance(response, BotResponses):
                # we are going to yield responses from a cached BotResponses instance
                self._cached_bot_response_iterator = aiter(response)
                response = await anext(self._cached_bot_response_iterator)

            else:
                if isinstance(response, Exception):
                    self._error = ErrorWrapper(error=response)
                    raise self._error

                if response is self._END_OF_RESPONSES:
                    self._response_queue = None
                    raise StopAsyncIteration

        self.responses_so_far.append(response)
        return response

    class _Iterator:
        def __init__(self, bot_responses: "BotResponses") -> None:
            self._bot_responses = bot_responses
            self._index = 0

        async def __anext__(self) -> "MergedMessage":
            try:
                response = self._bot_responses.responses_so_far[self._index]
            except IndexError:
                async with self._bot_responses._lock:
                    try:
                        response = self._bot_responses.responses_so_far[self._index]
                    except IndexError:
                        # this will also raise StopAsyncIteration if there are no more responses
                        response = await self._bot_responses._wait_for_next_response()

            self._index += 1
            return response


# noinspection PyProtectedMember
class SingleTurnContext:
    # pylint: disable=protected-access,too-many-arguments
    """
    A context object that is passed to a single turn handler function. It is meant to be used as a facade for the
    `MergedBot` and `MergedMessage` objects. It also has a method `yield_response` that is meant to be used by the
    single turn handler function to yield a response to the request.
    """

    requests: Tuple["MergedMessage"]

    _previous_ctx_token: ContextVar[Token] = ContextVar("_previous_ctx_token")
    _current_context: ContextVar[Optional["SingleTurnContext"]] = ContextVar("_current_context", default=None)

    def __init__(
        self,
        merger: BotMerger,
        this_bot: "MergedBot",
        bot_responses: BotResponses,
    ) -> None:
        self.merger = merger
        self.this_bot = this_bot

        self._bot_responses = bot_responses

    @property
    def concluding_request(self) -> "MergedMessage":
        """The last request that was sent to the bot."""
        return self.requests[-1]

    async def get_full_conversation(
        self, max_length: Optional[int] = None, include_invisible_to_bots: bool = False
    ) -> List["MergedMessage"]:
        """Get the full conversation history for this message (including this message)."""
        return await self.concluding_request.get_full_conversation(
            max_length=max_length, include_invisible_to_bots=include_invisible_to_bots
        )

    async def yield_response(
        self, response: MessageType, still_thinking: Optional[bool] = None, **kwargs
    ) -> "MergedMessage":
        """Yield a response to the request."""
        response = await self.merger.create_next_message(
            content=response,
            still_thinking=still_thinking,
            sender=self.this_bot,
            receiver=self.concluding_request.sender,
            parent_context=self.concluding_request.parent_context,
            responds_to=self.concluding_request,
            **kwargs,
        )
        self._bot_responses._response_queue.put_nowait(response)
        return response

    async def yield_interim_response(self, response: MessageType, **kwargs) -> "MergedMessage":
        """Yield an interim response to the request."""
        return await self.yield_response(response, still_thinking=True, **kwargs)

    async def yield_final_response(self, response: MessageType, **kwargs) -> "MergedMessage":
        """Yield a final response to the request."""
        return await self.yield_response(response, still_thinking=False, **kwargs)

    async def yield_from(
        self,
        iterable: Iterable[MessageType] | AsyncIterable[MessageType],
        still_thinking: Optional[bool] = None,
    ) -> None:
        """Yield responses to the request from an iterable."""
        if isinstance(iterable, abc.AsyncIterable):
            async for response in iterable:
                await self.yield_response(response, still_thinking=still_thinking)
        else:
            for response in iterable:
                await self.yield_response(response, still_thinking=still_thinking)

    def __enter__(self) -> "SingleTurnContext":
        """Set this context as the current context."""
        # TODO emphasize that nesting contexts is not supported unless asyncio.create_task is used for each nesting
        previous_ctx_token = self._current_context.set(self)  # <- this is the context switch
        self._previous_ctx_token.set(previous_ctx_token)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Restore the context that was current before this one."""
        previous_ctx_token = self._previous_ctx_token.get()
        self._current_context.reset(previous_ctx_token)
