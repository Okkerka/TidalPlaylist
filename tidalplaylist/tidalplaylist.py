from redbot.core import commands, Config
import tidalapi
import re
import logging
import asyncio

log = logging.getLogger("red.tidal")

class Tidal(commands.Cog):
    """Play Tidal links (playlist, album, or track) via the Audio cog."""
    
    def __init__(self, bot):
        self.bot = bot
        self.session = tidalapi.Session()
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_global = {
            "token_type": None,
            "access_token": None,
            "refresh_token": None,
            "expiry_time": None
        }
        self.config.register_global(**default_global)
        
        # Try to load session from config
        bot.loop.create_task(self._load_session())
    
    async def _load_session(self):
        """Load saved Tidal session on cog load."""
        try:
            token_type = await self.config.token_type()
            access_token = await self.config.access_token()
            refresh_token = await self.config.refresh_token()
            expiry_time = await self.config.expiry_time()
            
            if all([token_type, access_token, refresh_token]):
                self.session.load_oauth_session(
                    token_type=token_type,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expiry_time=expiry_time
                )
                if self.session.check_login():
                    log.info("Tidal session loaded successfully")
                else:
                    log.warning("Tidal session expired, please run [p]tidalsetup")
            else:
                log.warning("No Tidal credentials found. Run [p]tidalsetup")
        except Exception as e:
            log.error(f"Error loading Tidal session: {e}")
    
    @commands.is_owner()
    @commands.command()
    async def tidalsetup(self, ctx):
        """Set up Tidal OAuth authentication (Bot owner only)."""
        await ctx.send("Starting Tidal OAuth setup...")
        
        try:
            # Run OAuth flow
            login, future = self.session.login_oauth()
            
            await ctx.send(
                f"Please visit this URL and authorize the application:\n"
                f"{login.verification_uri_complete}\n\n"
                f"Waiting for authorization (this will timeout in 5 minutes)..."
            )
            
            # Wait for user to complete OAuth (with timeout)
            try:
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, future.result),
                    timeout=300
                )
            except asyncio.TimeoutError:
                await ctx.send("OAuth authorization timed out. Please try again.")
                return
            
            # Check if login was successful
            if self.session.check_login():
                # Save session to config
                await self.config.token_type.set(self.session.token_type)
                await self.config.access_token.set(self.session.access_token)
                await self.config.refresh_token.set(self.session.refresh_token)
                await self.config.expiry_time.set(self.session.expiry_time.timestamp() if self.session.expiry_time else None)
                
                await ctx.send("✅ Tidal OAuth setup complete! You can now use Tidal commands.")
                log.info("Tidal OAuth setup completed successfully")
            else:
                await ctx.send("❌ Login failed. Please try again.")
        except Exception as e:
            await ctx.send(f"Error during OAuth setup: {e}")
            log.error(f"Tidal OAuth error: {e}", exc_info=True)
    
    @commands.command()
    async def tidal(self, ctx, url: str):
        """
        Queue Tidal playlist, album, or track.
        Example: [p]tidal https://tidal.com/browse/playlist/xxxx
        """
        if not self.session.check_login():
            await ctx.send("Tidal is not authenticated. Bot owner needs to run `[p]tidalsetup` first.")
            return
        
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
        
        try:
            # Run blocking Tidal API call in executor
            playlist = await asyncio.get_event_loop().run_in_executor(
                None, self.session.playlist, playlist_id
            )
            tracks = await asyncio.get_event_loop().run_in_executor(
                None, playlist.tracks
            )
            
            await ctx.send(f"Queuing playlist **{playlist.name}** ({playlist.num_tracks} tracks)...")
            
            for track in tracks:
                await self._queue_track_obj(ctx, audio_cog, track)
            
            await ctx.send("✅ Done queueing playlist.")
        except Exception as e:
            await ctx.send(f"Error loading playlist: {e}")
            log.error(f"Playlist error: {e}", exc_info=True)
    
    async def _queue_album(self, ctx, audio_cog, url):
        match = re.search(r"album/([0-9]+)", url)
        if not match:
            await ctx.send("Invalid Tidal album URL.")
            return
        
        album_id = match.group(1)
        
        try:
            album = await asyncio.get_event_loop().run_in_executor(
                None, self.session.album, album_id
            )
            tracks = await asyncio.get_event_loop().run_in_executor(
                None, album.tracks
            )
            
            await ctx.send(f"Queuing album **{album.name}** by {album.artist.name} ({album.num_tracks} tracks)...")
            
            for track in tracks:
                await self._queue_track_obj(ctx, audio_cog, track)
            
            await ctx.send("✅ Done queueing album.")
        except Exception as e:
            await ctx.send(f"Error loading album: {e}")
            log.error(f"Album error: {e}", exc_info=True)
    
    async def _queue_track(self, ctx, audio_cog, url):
        match = re.search(r"track/([0-9]+)", url)
        if not match:
            await ctx.send("Invalid Tidal track URL.")
            return
        
        track_id = match.group(1)
        
        try:
            track = await asyncio.get_event_loop().run_in_executor(
                None, self.session.track, track_id
            )
            await self._queue_track_obj(ctx, audio_cog, track)
            await ctx.send(f"✅ Queued: **{track.name}** by {track.artist.name}")
        except Exception as e:
            await ctx.send(f"Error loading track: {e}")
            log.error(f"Track error: {e}", exc_info=True)
    
    async def _queue_track_obj(self, ctx, audio_cog, track):
        """Queue a track object via the Audio cog."""
        try:
            # Get track stream URL
            stream_url = await asyncio.get_event_loop().run_in_executor(
                None, track.get_url
            )
            
            # Use Audio cog to play (adjust this based on your Audio cog's API)
            # This is a common pattern but may need adjustment
            query = f"{track.artist.name} - {track.name}"
            
            # Try to use Audio cog's play command
            # You may need to adjust this depending on your Audio cog version
            if hasattr(audio_cog, 'command_play'):
                await ctx.invoke(audio_cog.command_play, query=query)
            else:
                # Fallback: just send the search query
                await ctx.send(f"Search for: {query}")
        except Exception as e:
            log.error(f"Error queueing track {track.name}: {e}")

async def setup(bot):
    await bot.add_cog(Tidal(bot))