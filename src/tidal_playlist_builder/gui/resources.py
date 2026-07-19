"""GUI resource loading helpers."""

from importlib.resources import as_file, files

from PySide6.QtGui import QIcon


def load_application_icon() -> QIcon:
    """Load application icon from packaged resources."""
    resource = files("tidal_playlist_builder.resources.icons").joinpath("app-icon.svg")
    with as_file(resource) as resolved:
        return QIcon(str(resolved))
