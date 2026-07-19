"""Domain enums used by filtering."""

from enum import Enum


class AlbumType(Enum):
    """Album category."""

    ALBUM = "album"
    EP = "ep"
    SINGLE = "single"
    COMPILATION = "compilation"


class AlbumEdition(Enum):
    """Album edition classification."""

    ORIGINAL = "original"
    DELUXE = "deluxe"
    EXPANDED = "expanded"
    REMASTER = "remaster"
    REMASTER_DELUXE = "remaster_deluxe"
    ANNIVERSARY = "anniversary"
    JAPANESE = "japanese"
    HI_RES = "hi_res"
    EXPLICIT = "explicit"
    CLEAN = "clean"
    LIVE = "live"


class AudioQuality(Enum):
    """Playback quality."""

    LOSSY = "lossy"
    LOSSLESS = "lossless"
    HI_RES = "hi_res"


class DuplicateStatus(Enum):
    """Duplicate filtering mode."""

    ALL = "all"
    CANONICAL_ONLY = "canonical_only"
    VARIANTS_ONLY = "variants_only"
    DUPLICATES_ONLY = "duplicates_only"
    NON_DUPLICATES_ONLY = "non_duplicates_only"
