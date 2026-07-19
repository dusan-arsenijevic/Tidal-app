"""Service for building playlist plans from selected albums."""

from tidal_playlist_builder.model.album import Album
from tidal_playlist_builder.model.artist import Artist
from tidal_playlist_builder.model.playlist_build_plan import PlaylistBuildPlan
from tidal_playlist_builder.model.track import Track


class PlaylistBuildPlanBuilder:
    """Builds PlaylistBuildPlan with validation and duplicate skipping."""

    def build(self, artist: Artist, selected_albums: list[Album]) -> PlaylistBuildPlan:
        """Build a playlist plan from artist and selected albums.

        Duplicate tracks are skipped by track id while preserving first-seen order.
        """
        self._validate_inputs(artist, selected_albums)

        unique_tracks: list[Track] = []
        seen_track_ids: set[str] = set()
        duplicates_skipped = 0

        for album in selected_albums:
            for track in album.tracks:
                if track.id in seen_track_ids:
                    duplicates_skipped += 1
                    continue
                seen_track_ids.add(track.id)
                unique_tracks.append(track)

        duration_seconds = sum(track.duration_seconds for track in unique_tracks)
        track_count = len(unique_tracks)

        return PlaylistBuildPlan(
            artist=artist,
            selected_albums=tuple(selected_albums),
            selected_tracks=tuple(unique_tracks),
            duplicates_skipped=duplicates_skipped,
            duration_seconds=duration_seconds,
            track_count=track_count,
        )

    def _validate_inputs(self, artist: Artist, selected_albums: list[Album]) -> None:
        if not isinstance(artist, Artist):
            raise TypeError("artist must be an Artist")
        if not selected_albums:
            raise ValueError("selected_albums cannot be empty")

        album_ids: set[str] = set()
        for album in selected_albums:
            if not isinstance(album, Album):
                raise TypeError("selected_albums must contain only Album objects")
            if album.artist.id != artist.id:
                raise ValueError("All selected albums must belong to the input artist")
            if album.id in album_ids:
                raise ValueError("selected_albums cannot contain duplicate album ids")
            album_ids.add(album.id)
