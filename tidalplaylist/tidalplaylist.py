from redbot.core import commands
import tidalapi
import re
import logging

log = logging.getLogger("red.tidal")

class Tidal(commands.Cog):
"""Play Tidal links (playlist, album, or track) via the Audio cog."""

def __init__(self, bot):
    self.bot = bot
    self.session = tidalapi.Session()
    try:
        # try to reuse session from disk if user already did manual login
        if not self.session.check_login():
            log.warning("Tidal session not logged in. Run the login_oauth_simple() manually on the host.")
    except Exception:
        log.warning("Tidal session not ready. Run login_oauth_simple() manually.")

@commands.command()
async def tidal(self, ctx, url: str):
    """
    Queue Tidal playlist, album, or track.
    Example: >tidal https://tidal.com/browse/playlist/xxxx
    """
    audio_cog = self.bot.get_cog("Audio")
    if not audio_cog:
        await ctx.send("Audio cog is not loaded!")
        return

    if "playlist/" in url:
        await self._queue_playlist(ctx, audio_cog, url)
    elif "album/" in url:
        await self._queue_album(ctx, audio_cog, url)
    elif "track/" in url:
        await self._queue_track(ctx, audio_cog, url)
    else:
        await ctx.send("Unsupported Tidal link. Use a playlist, album, or track URL.")

async def _queue_playlist(self, ctx, audio_cog, url):
    match = re.search(r"playlist/([A-Za-z0-9\-]+)", url)
    if not match:
        await ctx.send("Invalid Tidal playlist URL.")
        return
    playlist_id = match.group(1)
    playlist = self.session.playlist(playlist_id)
    await ctx.send(f"Queuing playlist **{playlist.name}** ({playlist.num_tracks} tracks)...")
    for track in playlist.tracks():
        await self._queue_track_obj(ctx, audio_cog, track)
    await ctx.send("Done queueing playlist.")

async def _queue_album(self, ctx, audio_cog, url):
    match = re.search(r"album/([A-Za-z0-9\-]+)", url)
    if not match:
        await ctx.send("Invalid Tidal album URL.")
        return
    album_id = match.group(1)
    album = self.session.album(album_id)
    await ctx.send(f"Queuing album **{album.name}** ({album.num_tracks} tracks)...")
    for track in album.tracks():
        await self._queue_track_obj(ctx, audio_cog, track)
    await ctx.send("Done queueing album.")

async def _queue_track(self, ctx, audio_cog, url):
    match = re.search(r"track/([A-Za-z0-9\-]+)", url)
    if not match:
        await ctx.send("Invalid Tidal track URL.")
        return
    track_id = match.group(1)
    track = self.session.track(track_id)
    await ctx.send(f"Queuing track: **{track.name}** - {track.artist.name}")
    await self._queue_track_obj(ctx, audio_cog, track)

async def _queue_track_obj(self, ctx, audio_cog, track):
    try:
        track_name = getattr(track, "name", None) or getattr(track, "title", None)
        artist_name = getattr(track.artist, "name", "") if hasattr(track, "artist") else ""
        query = f"ytsearch:{track_name} {artist_name}"
        await ctx.invoke(audio_cog.play, query=query)
    except Exception as e:
        log.exception("Error queueing track")
        await ctx.send(f"Failed to queue track {track_name}: {e}")