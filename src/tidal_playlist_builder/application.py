"""Production composition root for the application."""

from dataclasses import dataclass
import logging
from typing import cast

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from tidal_playlist_builder.exceptions import CacheError
from tidal_playlist_builder.gui import MainWindow
from tidal_playlist_builder.gui.font_fallback import ensure_ui_font_has_basic_glyphs
from tidal_playlist_builder.gui.models import AlbumFilterProxyModel, AlbumTableModel
from tidal_playlist_builder.repositories import (
    AlbumRepository,
    ArtistRepository,
    PlaylistRepository,
)
from tidal_playlist_builder.services import (
    CacheService,
    JsonCacheBackend,
    PlaylistBuildPlanBuilder,
)
from tidal_playlist_builder.threading import WorkerThreadPool
from tidal_playlist_builder.tidal import (
    HttpClientConfig,
    HttpTidalApiClient,
    TidalApiClient,
    TidalProvider,
)

from .configuration import AppConfig, load_app_config_from_env
from .exception_handling import (
    install_global_exception_handler,
    set_exception_dialog_presenter,
)
from .logging_config import configure_runtime_logging
from .workflow import WorkflowController
from .__about__ import __version__

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppComposition:
    """Composed production dependency graph."""

    config: AppConfig
    settings: QSettings
    cache_backend: JsonCacheBackend | None
    cache_service: CacheService
    api_client: TidalApiClient
    artist_repository: ArtistRepository
    album_repository: AlbumRepository
    playlist_repository: PlaylistRepository
    provider: TidalProvider
    worker_pool: WorkerThreadPool
    workflow: WorkflowController
    album_table_model: AlbumTableModel
    album_proxy_model: AlbumFilterProxyModel
    main_window: MainWindow


def build_production_composition(
    config: AppConfig | None = None,
    *,
    settings: QSettings | None = None,
    api_client: TidalApiClient | None = None,
    album_table_model: AlbumTableModel | None = None,
) -> AppComposition:
    """Build the full production dependency graph."""
    logger.debug("Building production composition")
    # initialize configuration
    app_config = config or load_app_config_from_env()
    app_settings = settings or QSettings(
        app_config.settings_org, app_config.settings_app
    )

    # initialize cache
    cache_backend: JsonCacheBackend | None
    try:
        cache_backend = JsonCacheBackend(app_config.cache_directory)
        cache_service = CacheService(
            cache_directory=None,
            disk_backend=cache_backend,
            max_memory_entries=app_config.max_memory_entries,
            default_ttl_seconds=app_config.default_ttl_seconds,
        )
    except CacheError:
        logger.warning(
            "Disk cache unavailable at %s; using memory-only cache",
            app_config.cache_directory,
            exc_info=True,
        )
        cache_backend = None
        cache_service = CacheService(
            cache_directory=None,
            max_memory_entries=app_config.max_memory_entries,
            default_ttl_seconds=app_config.default_ttl_seconds,
        )

    # initialize HTTP client
    resolved_api_client = api_client or HttpTidalApiClient(
        HttpClientConfig(
            base_url=app_config.base_url,
            timeout_seconds=app_config.timeout_seconds,
            max_retries=app_config.retry_count,
            backoff_base_seconds=app_config.retry_backoff_seconds,
            user_agent=app_config.user_agent,
        )
    )

    # initialize provider
    provider = TidalProvider(
        api_client=resolved_api_client,
        cache_service=cache_service,
        max_retries=app_config.retry_count,
        retry_backoff_seconds=app_config.retry_backoff_seconds,
    )
    if app_config.auth_credentials:
        logger.info("Authenticating provider from configured credentials")
        provider.authenticate(app_config.auth_credentials)

    # initialize repositories
    artist_repository = provider.artist_repository
    album_repository = provider.album_repository
    playlist_repository = provider.playlist_repository

    # initialize workers
    worker_pool = WorkerThreadPool(max_threads=app_config.max_worker_threads)

    # construct MainWindow
    model = album_table_model or AlbumTableModel([])
    proxy = AlbumFilterProxyModel()
    proxy.setSourceModel(model)
    main_window = MainWindow(
        settings=app_settings,
        album_table_model=model,
        album_proxy_model=proxy,
    )
    workflow = WorkflowController(
        main_window=main_window,
        worker_pool=worker_pool,
        provider=provider,
        playlist_builder=PlaylistBuildPlanBuilder(),
        album_table_model=model,
        album_proxy_model=proxy,
    )
    workflow.playlistCreated.connect(
        lambda playlist_id: main_window.show_success_dialog(
            "Playlist Created",
            f"Playlist created successfully: {playlist_id}",
        )
    )
    workflow.operationFailed.connect(
        lambda message: main_window.show_error_dialog("Operation Failed", message)
    )

    return AppComposition(
        config=app_config,
        settings=app_settings,
        cache_backend=cache_backend,
        cache_service=cache_service,
        api_client=resolved_api_client,
        artist_repository=artist_repository,
        album_repository=album_repository,
        playlist_repository=playlist_repository,
        provider=provider,
        worker_pool=worker_pool,
        workflow=workflow,
        album_table_model=model,
        album_proxy_model=proxy,
        main_window=main_window,
    )


def run() -> int:
    """Start the production desktop application."""
    logging_state = configure_runtime_logging()
    logger.info("Application startup version=%s", __version__)
    logger.debug(
        "Logging initialized level=%s file_logging=%s path=%s",
        logging_state.level,
        logging_state.file_logging_enabled,
        logging_state.log_file,
    )
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    ensure_ui_font_has_basic_glyphs(cast(QApplication, app))
    install_global_exception_handler()

    composition = build_production_composition()
    set_exception_dialog_presenter(composition.main_window.show_error_dialog)
    # show UI
    composition.main_window.show()
    exit_code = app.exec()
    logger.info("Application shutdown exit_code=%s", exit_code)
    return exit_code
