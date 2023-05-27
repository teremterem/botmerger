"""Integration with the LangChain library."""
import asyncio
import io
import sys
import threading
from typing import AsyncGenerator, Coroutine

from langchain.callbacks.base import AsyncCallbackHandler

from ..errors import ErrorWrapper
from ..models import MergedBot, MergedMessage


class LangChainParagraphStreamingCallback(AsyncCallbackHandler):  # pylint: disable=abstract-method
    """
    A callback handler that splits the output into paragraphs and dispatches each paragraph as a separate message.
    """

    # TODO move all the heavy lifting (writing to StringIO and paragraph splitting) from on_llm_new_token() and
    #  on_llm_end() to stream_from_coroutine() ? (check out AsyncIteratorCallbackHandler for inspiration)

    def __init__(self, bot: MergedBot, message: MergedMessage, verbose: bool = False) -> None:
        self._bot = bot
        self._message = message
        self._verbose = verbose

        self._str_io = io.StringIO()
        self._msg_queue: asyncio.Queue[MergedMessage | Exception] = asyncio.Queue()

        # I have a feeling that LangChain triggers callbacks from a multithreaded environment
        self._threading_lock = threading.Lock()

    async def stream_from_coroutine(self, coro: Coroutine) -> AsyncGenerator[MergedMessage, None]:
        """
        Streams the output of the coroutine as a sequence of messages. Coroutine should be running a LangChain
        component that is already preconfigured to use this callback handler.
        """

        async def coro_wrapper() -> None:
            try:
                await coro
            except Exception as exc:  # pylint: disable=broad-exception-caught
                # don't lose the exception
                await self._msg_queue.put(exc)

        asyncio.create_task(coro_wrapper())
        while True:
            msg = await self._msg_queue.get()
            if isinstance(msg, Exception):
                raise ErrorWrapper(error=msg)

            yield msg

            if not msg.is_still_typing:
                break

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        if self._verbose:
            sys.stdout.write(token)
            sys.stdout.flush()

        with self._threading_lock:
            self._str_io.write(token)

            if not token or token.isspace():
                # token is empty, let's wait for a non-empty one (non-empty token would signify that
                # the previous paragraph, if any, is not the last one just yet)
                return

            text_so_far = self._str_io.getvalue()

            inside_code_block = (text_so_far.count("```") % 2) == 1
            if inside_code_block:
                # we don't want to split a code block
                return

            split_idx = text_so_far.rfind("\n\n")
            if split_idx != -1:
                self._msg_queue.put_nowait(self._message.interim_bot_response(self._bot, text_so_far[:split_idx]))
                self._str_io = io.StringIO(text_so_far[split_idx + 2 :])

    async def on_llm_end(self, *args, **kwargs) -> None:  # pylint: disable=unused-argument
        if self._verbose:
            sys.stdout.write("\n")
            sys.stdout.flush()

        with self._threading_lock:
            # emitting the last paragraph
            self._msg_queue.put_nowait(self._message.final_bot_response(self._bot, self._str_io.getvalue()))
            self._str_io = None  # make this callback object unusable
