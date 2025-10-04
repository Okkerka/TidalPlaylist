from redbot.core import commands, Config
import discord
import asyncio
import re
import logging

log = logging.getLogger("red.tidal")

# Try to import tidalapi, but don't fail if it's not installed
try:
    import tidalapi
    TIDALAPI_AVAILABLE = True
except ImportError:
    TIDALAPI_AVAILABLE = False
    log.error("tidalapi not installed! Install with: pip install tidalapi")

class Tidal(commands.Cog):
    """Play Tidal links (playlist, album, or track) via the Audio cog."""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_global = {
            "token_type": None,
            "access_token": None,
            "refresh_token": None,
            "expiry_time": None
        }
        self.config.register_global(**default_global)
        
        if TIDALAPI_AVAILABLE:
            self.session = tidalapi.Session()
            # Try to load session from config
            self.bot.loop.create_task(self._load_session())
        else:
            self.session = None
            log.error("Tidal cog loaded but tidalapi is not available")
    
    async def _load_session(self):
        """Load saved Tidal session on cog load."""
        await self.bot.wait_until_ready()
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
                log.info("No Tidal credentials found. Run [p]tidalsetup")
        except Exception as e:
            log.error(f"Error loading Tidal session: {e}", exc_info=True)
    
    @commands.is_owner()
    @commands.command()
    async def tidalsetup(self, ctx):
        """Set up Tidal OAuth authentication (Bot owner only)."""
        if not TIDALAPI_AVAILABLE:
            await ctx.send("❌ tidalapi library is not installed. Bot owner needs to install it with:\n`pip install tidalapi`")
            return
        
        await ctx.send("Starting Tidal OAuth setup...")
        
        try:
            # Run OAuth flow
            login, future = self.session.login_oauth()
            
            embed = discord.Embed(
                title="🎵 Tidal OAuth Setup",
                description=f"Please visit this URL and authorize the application:\n\n{login.verification_uri_complete}",
                color=discord.Color.blue()
            )
            embed.add_field(name="Waiting...", value="This will timeout in 5 minutes", inline=False)
            await ctx.send(embed=embed)
            
            # Wait for user to complete OAuth (with timeout)
            try:
                await asyncio.wait_for(
                    self.bot.loop.run_in_executor(None, future.result),
                    timeout=300
                )
            except asyncio.TimeoutError:
                await ctx.send("⏱️ OAuth authorization timed out. Please try again.")
                return
            
            # Check if login was successful
            if self.session.check_login():
                # Save session to config
                await self.config.token_type.set(self.session.token_type)
                await self.config.access_token.set(self.session.access_token)
                await self.config.refresh_token.set(self.session.refresh_token)
                if hasattr(self.session, 'expiry_time') and self.session.expiry_time:
                    await self.config.expiry_time.set(self.session.expiry_time.timestamp())
                
                await ctx.send("✅ Tidal OAuth setup complete! You can now use Tidal commands.")
                log.info("Tidal OAuth setup completed successfully")
            else:
                await ctx.send("❌ Login failed. Please try again.")
        except Exception as e:
            await ctx.send(f"❌ Error during OAuth setup: {str(e)}")
            log.error(f"Tidal OAuth error: {e}", exc_info=True)
    
    @commands.command()
    async def tidal(self, ctx, url: str):
        """
        Queue Tidal playlist, album, or track via Audio cog.
        Example: [p]tidal https://tidal.com/browse/playlist/xxxx
        """
        if not TIDALAPI_AVAILABLE:
            await ctx.send("❌ tidalapi library is not installed.")
            return
        
        if not self.session.check_login():
            await ctx.send("❌ Tidal is not authenticated. Bot owner needs to run `[p]tidalsetup` first.")
            return
        
        audio_cog = self.bot.get_cog("Audio")
        if not audio_cog:
            await ctx.send("❌ Audio cog is not loaded! Load it with `[p]load audio`")
            return
        
        # Check if user is in a voice channel
        if not ctx.author.voice:
            await ctx.send("❌ You need to be in a voice channel!")
            return
        
        if "playlist/" in url:
            await self._queue_playlist(ctx, url)
        elif "album/" in url:
            await self._queue_album(ctx, url)
        elif "track/" in url:
            await self._queue_track(ctx, url)
        else:
            await ctx.send("❌ Unsupported Tidal link. Use a playlist, album, or track URL.")
    
    async def _queue_playlist(self, ctx, url):
        match = re.search(r"playlist/([A-Za-z0-9\-]+)", url)
        if not match:
            await ctx.send("❌ Invalid Tidal playlist URL.")
            return
        
        playlist_id = match.group(1)
        
        try:
            # Run blocking Tidal API call in executor
            playlist = await self.bot.loop.run_in_executor(
                None, self.session.playlist, playlist_id
            )
            tracks = await self.bot.loop.run_in_executor(
                None, playlist.tracks
            )
            
            total = len(tracks)
            await ctx.send(f"⏳ Queuing playlist **{playlist.name}** ({total} tracks)...")
            
            queued = 0
            failed = 0
            
            for track in tracks:
                try:
                    success = await self._add_to_queue(ctx, track)
                    if success:
                        queued += 1
                    else:
                        failed += 1
                except Exception as e:
                    log.error(f"Error queueing track: {e}")
                    failed += 1
            
            result_msg = f"✅ Queued {queued}/{total} tracks"
            if failed > 0:
                result_msg += f" ({failed} failed)"
            await ctx.send(result_msg)
            
        except Exception as e:
            await ctx.send(f"❌ Error loading playlist: {str(e)}")
            log.error(f"Playlist error: {e}", exc_info=True)
    
    async def _queue_album(self, ctx, url):
        match = re.search(r"album/([0-9]+)", url)
        if not match:
            await ctx.send("❌ Invalid Tidal album URL.")
            return
        
        album_id = match.group(1)
        
        try:
            album = await self.bot.loop.run_in_executor(
                None, self.session.album, album_id
            )
            tracks = await self.bot.loop.run_in_executor(
                None, album.tracks
            )
            
            total = len(tracks)
            await ctx.send(f"⏳ Queuing album **{album.name}** by {album.artist.name} ({total} tracks)...")
            
            queued = 0
            failed = 0
            
            for track in tracks:
                try:
                    success = await self._add_to_queue(ctx, track)
                    if success:
                        queued += 1
                    else:
                        failed += 1
                except Exception as e:
                    log.error(f"Error queueing track: {e}")
                    failed += 1
            
            result_msg = f"✅ Queued {queued}/{total} tracks"
            if failed > 0:
                result_msg += f" ({failed} failed)"
            await ctx.send(result_msg)
            
        except Exception as e:
            await ctx.send(f"❌ Error loading album: {str(e)}")
            log.error(f"Album error: {e}", exc_info=True)
    
    async def _queue_track(self, ctx, url):
        match = re.search(r"track/([0-9]+)", url)
        if not match:
            await ctx.send("❌ Invalid Tidal track URL.")
            return
        
        track_id = match.group(1)
        
        try:
            track = await self.bot.loop.run_in_executor(
                None, self.session.track, track_id
            )
            
            success = await self._add_to_queue(ctx, track)
            if success:
                await ctx.send(f"✅ Queued: **{track.name}** by {track.artist.name}")
            else:
                await ctx.send(f"❌ Failed to queue: **{track.name}** by {track.artist.name}")
                
        except Exception as e:
            await ctx.send(f"❌ Error loading track: {str(e)}")
            log.error(f"Track error: {e}", exc_info=True)
    
    async def _add_to_queue(self, ctx, track):
        """
        Add a track to the Audio cog queue using YouTube search.
        Returns True if successful, False otherwise.
        """
        try:
            # Build search query
            query = f"{track.artist.name} - {track.name}"
            
            # Get the play command from Audio cog
            play_command = self.bot.get_command("play")
            
            if not play_command:
                log.error("Play command not found!")
                return False
            
            # Invoke play command with search query (Audio will search YouTube/other sources)
            # We suppress messages by setting a flag that Audio checks
            old_channel = ctx.channel
            
            try:
                # Invoke the play command - Audio cog will search and queue
                await ctx.invoke(play_command, query=query)
                return True
            except Exception as e:
                log.error(f"Error invoking play command: {e}")
                return False
            finally:
                ctx.channel = old_channel
                
        except Exception as e:
            log.error(f"Error adding track to queue: {e}", exc_info=True)
            return False

def setup(bot):
    bot.add_cog(Tidal(bot))