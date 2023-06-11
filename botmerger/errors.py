"""This module contains all BotMerger errors."""
import traceback


class BotMergerError(Exception):
    """Base class for all BotMerger errors."""


class BotAliasTakenError(BotMergerError):
    """Raised when a bot with the same alias already exists."""


class BotNotFoundError(BotMergerError):
    """Raised when a bot with the given handle does not exist."""


class ErrorWrapper(BotMergerError):
    """This wrapper is used to contain errors that occurred outside main coroutine."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        # TODO is there a better way to automatically display the full traceback of the nested error except
        #  preformatting the whole thing into the wrapper error message ?
        super().__init__(
            "\n\nSEE NESTED EXCEPTION BELOW\n\n"
            + "".join(traceback.format_exception(type(error), error, error.__traceback__))
        )
        # super().__init__(f"{type(error).__module__}.{type(error).__name__}: {error}")
