"""Global exception handling for production runtime."""

from collections.abc import Callable
from dataclasses import dataclass
import logging
import sys
import threading
from types import TracebackType

from PySide6.QtWidgets import QApplication, QMessageBox

logger = logging.getLogger(__name__)

_USER_ERROR_TITLE = "Unexpected Error"
_USER_ERROR_MESSAGE = "An unexpected error occurred and the application needs to close."
_DialogPresenter = Callable[[str, str], None]


@dataclass
class _HandlerState:
    installed: bool = False
    presenter: _DialogPresenter | None = None
    previous_sys_hook: (
        Callable[[type[BaseException], BaseException, TracebackType | None], object]
        | None
    ) = None
    previous_thread_hook: Callable[[threading.ExceptHookArgs], object] | None = None


_state = _HandlerState()


def install_global_exception_handler() -> None:
    """Install global exception hooks for GUI and background threads."""
    if _state.installed:
        return
    _state.previous_sys_hook = sys.excepthook
    _state.previous_thread_hook = threading.excepthook
    sys.excepthook = _handle_sys_exception
    threading.excepthook = _handle_thread_exception
    _state.installed = True


def uninstall_global_exception_handler() -> None:
    """Restore prior exception hooks."""
    if not _state.installed:
        return
    if _state.previous_sys_hook is not None:
        sys.excepthook = _state.previous_sys_hook
    if _state.previous_thread_hook is not None:
        threading.excepthook = _state.previous_thread_hook
    _state.installed = False
    _state.presenter = None


def set_exception_dialog_presenter(presenter: _DialogPresenter) -> None:
    """Set presenter used to show user-friendly error dialogs."""
    _state.presenter = presenter


def _handle_sys_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_traceback: TracebackType | None,
) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        if _state.previous_sys_hook is not None:
            _state.previous_sys_hook(exc_type, exc_value, exc_traceback)
        return

    logger.exception(
        "Unhandled GUI exception",
        exc_info=(exc_type, exc_value, exc_traceback),
    )
    _show_user_error()
    _quit_application()


def _handle_thread_exception(args: threading.ExceptHookArgs) -> None:
    if issubclass(args.exc_type, KeyboardInterrupt):
        if _state.previous_thread_hook is not None:
            _state.previous_thread_hook(args)
        return

    exc_value = args.exc_value
    if exc_value is None:
        exc_value = RuntimeError("Unknown background exception")
    logger.exception(
        "Unhandled background exception thread=%s",
        args.thread.name if args.thread is not None else "unknown",
        exc_info=(args.exc_type, exc_value, args.exc_traceback),
    )
    _show_user_error()
    _quit_application()


def _show_user_error() -> None:
    presenter = _state.presenter
    if presenter is not None:
        try:
            presenter(_USER_ERROR_TITLE, _USER_ERROR_MESSAGE)
            return
        except Exception:  # pragma: no cover - safety path for production UX
            logger.exception("Global exception dialog presenter failed")
    QMessageBox.critical(None, _USER_ERROR_TITLE, _USER_ERROR_MESSAGE)


def _quit_application() -> None:
    app = QApplication.instance()
    if app is not None:
        app.quit()
