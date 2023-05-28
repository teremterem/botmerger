# pylint: disable=protected-access
"""
A bot, whose fulfillment_func is called once per the whole user interaction. NonEventBasedChatSession is used
send and receive messages in an algorithmic way, without events.
"""
import asyncio
from typing import Awaitable, Callable, AsyncGenerator

from pydantic import PrivateAttr

from mergedbots.models import MergedBot, MergedMessage, MergedObject, MergedParticipant

SessionFulfillmentFunc = Callable[["NonEventBasedMergedBot", "NonEventBasedChatSession"], Awaitable[None]]

_INBOUND_MSG_SENTINEL = object()
_SESSION_ENDED_SENTINEL = object()


class NonEventBasedMergedBot(MergedBot):
    """
    A bot, whose fulfillment_func is called once per the whole user interaction. NonEventBasedChatSession is used to
    send and receive messages in an algorithmic way, without events.
    """

    # TODO convert this class into a wrapper around MergedBot rather than a subclass

    fulfillment_func: SessionFulfillmentFunc = None

    _sessions: PrivateAttr(dict["MergedParticipant", "NonEventBasedChatSession"]) = PrivateAttr(default_factory=dict)

    async def fulfill(self, message: "MergedMessage") -> AsyncGenerator["MergedMessage", None]:
        """Fulfill a message."""
        session = self._sessions.get(message.originator)
        if session:
            await session._inbound_queue.put(message)
        else:
            # TODO first message should also be read via `wait_for_next_message`
            session = NonEventBasedChatSession(bot=self, originator=message.originator, current_inbound_msg=message)
            self._sessions[message.originator] = session
            asyncio.create_task(self._run_session_till_the_end(session))

        while True:
            response = await session._outbound_queue.get()

            if response is _INBOUND_MSG_SENTINEL:
                # new incoming message is now being awaited for - exit current `fulfill` and let it be processed
                # by a new call to `fulfill`
                return
            if response is _SESSION_ENDED_SENTINEL:
                # the session has finished running - make room for a new session from the same originator in the future
                self._sessions.pop(session.originator)
                return

            yield response

    async def _run_session_till_the_end(self, session: "NonEventBasedChatSession") -> None:
        await self.fulfillment_func(self, session)
        await session._outbound_queue.put(_SESSION_ENDED_SENTINEL)

    def __call__(self, fulfillment_func: SessionFulfillmentFunc) -> SessionFulfillmentFunc:
        self.fulfillment_func = fulfillment_func
        return fulfillment_func


class NonEventBasedChatSession(MergedObject):
    """
    An object that represents a chat session between a bot and a user (or, more generally, an originator, because
    this might be two bots talking to each other).
    """

    bot: MergedBot
    originator: MergedParticipant

    current_inbound_msg: MergedMessage = None

    _inbound_queue: asyncio.Queue[MergedMessage] = PrivateAttr(default_factory=asyncio.Queue)
    _outbound_queue: asyncio.Queue[MergedMessage | object] = PrivateAttr(default_factory=asyncio.Queue)

    async def wait_for_next_message(self) -> MergedMessage:
        """Wait for the next message from the originator."""
        await self._outbound_queue.put(_INBOUND_MSG_SENTINEL)
        message = await self._inbound_queue.get()
        self.current_inbound_msg = message
        return message

    async def send_message(self, message: MergedMessage) -> None:
        """Send a message to the originator."""
        await self._outbound_queue.put(message)
