"""Tests for global exception handling."""

from types import SimpleNamespace
import threading
from typing import cast

import tidal_playlist_builder.exception_handling as exception_handling


def test_install_and_uninstall_global_exception_handler() -> None:
    original_sys_hook = exception_handling.sys.excepthook
    original_thread_hook = exception_handling.threading.excepthook
    exception_handling.uninstall_global_exception_handler()

    exception_handling.install_global_exception_handler()

    assert (
        exception_handling.sys.excepthook is exception_handling._handle_sys_exception
    )  # noqa: SLF001
    assert (
        exception_handling.threading.excepthook
        is exception_handling._handle_thread_exception  # noqa: SLF001
    )

    exception_handling.uninstall_global_exception_handler()
    assert exception_handling.sys.excepthook is original_sys_hook
    assert exception_handling.threading.excepthook is original_thread_hook


def test_unhandled_sys_exception_logs_and_reports_user_friendly_message(caplog) -> None:
    shown: list[tuple[str, str]] = []
    quit_called: list[bool] = []
    exception_handling.set_exception_dialog_presenter(
        lambda title, message: shown.append((title, message))
    )

    original_quit = exception_handling._quit_application  # noqa: SLF001
    exception_handling._quit_application = lambda: quit_called.append(True)  # type: ignore[assignment]  # noqa: SLF001
    try:
        try:
            raise RuntimeError("boom")
        except RuntimeError as error:
            with caplog.at_level("ERROR"):
                exception_handling._handle_sys_exception(  # noqa: SLF001
                    type(error),
                    error,
                    error.__traceback__,
                )
    finally:
        exception_handling._quit_application = original_quit  # type: ignore[assignment]  # noqa: SLF001
        exception_handling.set_exception_dialog_presenter(lambda _t, _m: None)

    assert shown == [
        (
            "Unexpected Error",
            "An unexpected error occurred and the application needs to close.",
        )
    ]
    assert quit_called == [True]
    assert "Unhandled GUI exception" in caplog.text


def test_unhandled_thread_exception_logs_and_reports_user_friendly_message(
    caplog,
) -> None:
    shown: list[tuple[str, str]] = []
    quit_called: list[bool] = []
    exception_handling.set_exception_dialog_presenter(
        lambda title, message: shown.append((title, message))
    )

    original_quit = exception_handling._quit_application  # noqa: SLF001
    exception_handling._quit_application = lambda: quit_called.append(True)  # type: ignore[assignment]  # noqa: SLF001
    try:
        try:
            raise ValueError("thread boom")
        except ValueError as error:
            args = cast(
                threading.ExceptHookArgs,
                SimpleNamespace(
                    exc_type=type(error),
                    exc_value=error,
                    exc_traceback=error.__traceback__,
                    thread=SimpleNamespace(name="worker-1"),
                ),
            )
            with caplog.at_level("ERROR"):
                exception_handling._handle_thread_exception(args)  # noqa: SLF001
    finally:
        exception_handling._quit_application = original_quit  # type: ignore[assignment]  # noqa: SLF001
        exception_handling.set_exception_dialog_presenter(lambda _t, _m: None)

    assert shown == [
        (
            "Unexpected Error",
            "An unexpected error occurred and the application needs to close.",
        )
    ]
    assert quit_called == [True]
    assert "Unhandled background exception thread=worker-1" in caplog.text
