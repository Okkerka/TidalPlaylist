from redbot.core import commands, Config
import tidalapi
import re

class TidalPlaylist(commands.Cog):
    """Fetch Tidal playlists and queue them into the Audio cog."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        # store token info if needed later
        self.session = tidalapi.Session()
        try:
            self.session.login_oauth_simple()
        except Exception as e:
            print(f"Tidal login required: {e}")

    @commands.command()
    async def tidalplaylist(self, ctx, playlist_url: str):
        """
        Queue all tracks from a Tidal playlist into the Audio cog.
        Example: [p]tidalplaylist https://tidal.com/browse/playlist/1234abcd
        """
        match = re.search(r"playlist/([A-Za-z0-9]+)", playlist_url)
        if not match:
            await ctx.send("Invalid Tidal playlist URL.")
            return

        playlist_id = match.group(1)

        try:
            playlist = self.session.playlist(playlist_id)
        except Exception as e:
            await ctx.send(f"Failed to fetch playlist: {e}")
            return

        audio_cog = self.bot.get_cog("Audio")
        if not audio_cog:
            await ctx.send("Audio cog is not loaded!")
            return

        await ctx.send(f"Queuing **{playlist.name}** ({playlist.num_tracks} tracks)...")

        for track in playlist.tracks():
            query = f"ytsearch:{track.name} {track.artist.name}"
            try:
                await ctx.invoke(audio_cog.play, query=query)
            except Exception as e:
                await ctx.send(f"Error adding track {track.name}: {e}")
