import discord
from redbot.core import commands, Config
import asyncio
import re
import logging

log = logging.getLogger("red.tidalplaylist")

try:
    import tidalapi
    TIDALAPI_AVAILABLE = True
except ImportError:
    TIDALAPI_AVAILABLE = False
    log.error("tidalapi not installed")


class TidalPlaylist(commands.Cog):
    """Play Tidal links via the Audio cog."""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=1234567890,
            force_registration=True
        )
        
        default_global = {
            "token_type": None,
            "access_token": None,
            "refresh_token": None,
            "expiry_time": None
        }
        self.config.register_global(**default_global)
        
        if TIDALAPI_AVAILABLE:
            self.session = tidalapi.Session()
            bot.loop.create_task(self.load_session())
        else:
            self.session = None
    
    async def load_session(self):
        """Load saved session."""
        await self.bot.wait_until_ready()
        
        try:
            token_type = await self.config.token_type()
            access_token = await self.config.access_token()
            refresh_token = await self.config.refresh_token()
            expiry_time = await self.config.expiry_time()
            
            if token_type and access_token and refresh_token:
                self.session.load_oauth_session(
                    token_type=token_type,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expiry_time=expiry_time
                )
                
                if self.session.check_login():
                    log.info("Tidal session loaded")
                else:
                    log.warning("Tidal session expired")
            else:
                log.info("No Tidal credentials found")
        except Exception as e:
            log.error(f"Error loading session: {e}")
    
    @commands.is_owner()
    @commands.command()
    async def tidalsetup(self, ctx):
        """Set up Tidal OAuth."""
        
        if not TIDALAPI_AVAILABLE:
            return await ctx.send(
                "tidalapi is not installed. Install with: pip install tidalapi"
            )
        
        await ctx.send("Starting OAuth setup...")
        
        try:
            login, future = self.session.login_oauth()
            
            embed = discord.Embed(
                title="Tidal OAuth Setup",
                description=f"Visit this URL:\n{login.verification_uri_complete}",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Waiting",
                value="Timeout in 5 minutes",
                inline=False
            )
            await ctx.send(embed=embed)
            
            try:
                await asyncio.wait_for(
                    self.bot.loop.run_in_executor(None, future.result),
                    timeout=300
                )
            except asyncio.TimeoutError:
                return await ctx.send("OAuth timed out")
            
            if self.session.check_login():
                await self.config.token_type.set(self.session.token_type)
                await self.config.access_token.set(self.session.access_token)
                await self.config.refresh_token.set(self.session.refresh_token)
                
                if hasattr(self.session, 'expiry_time') and self.session.expiry_time:
                    await self.config.expiry_time.set(
                        self.session.expiry_time.timestamp()
                    )
                
                await ctx.send("Setup complete!")
                log.info("OAuth setup completed")
            else:
                await ctx.send("Login failed")
                
        except Exception as e:
            await ctx.send(f"Error: {str(e)}")
            log.error(f"OAuth error: {e}")
    
    @commands.command()
    async def tidal(self, ctx, url: str):
        """Queue Tidal playlist, album, or track."""
        
        if not TIDALAPI_AVAILABLE:
            return await ctx.send("tidalapi is not installed")
        
        if not self.session.check_login():
            return await ctx.send(
                "Not authenticated. Owner needs to run tidalsetup"
            )
        
        audio = self.bot.get_cog("Audio")
        if not audio:
            return await ctx.send("Audio cog not loaded")
        
        if not ctx.author.voice:
            return await ctx.send("Join a voice channel first")
        
        if "playlist/" in url:
            await self.queue_playlist(ctx, url)
        elif "album/" in url:
            await self.queue_album(ctx, url)
        elif "track/" in url:
            await self.queue_track(ctx, url)
        else:
            await ctx.send("Invalid Tidal URL")
    
    async def queue_playlist(self, ctx, url):
        """Queue a playlist."""
        
        match = re.search(r"playlist/([A-Za-z0-9\-]+)", url)
        if not match:
            return await ctx.send("Invalid playlist URL")
        
        playlist_id = match.group(1)
        
        try:
            playlist = await self.bot.loop.run_in_executor(
                None,
                self.session.playlist,
                playlist_id
            )
            
            tracks = await self.bot.loop.run_in_executor(
                None,
                playlist.tracks
            )
            
            total = len(tracks)
            await ctx.send(f"Queuing {playlist.name} ({total} tracks)...")
            
            queued = 0
            for track in tracks:
                try:
                    if await self.add_track(ctx, track):
                        queued += 1
                except Exception as e:
                    log.error(f"Error queuing track: {e}")
            
            await ctx.send(f"Queued {queued}/{total} tracks")
            
        except Exception as e:
            await ctx.send(f"Error: {str(e)}")
            log.error(f"Playlist error: {e}")
    
    async def queue_album(self, ctx, url):
        """Queue an album."""
        
        match = re.search(r"album/([0-9]+)", url)
        if not match:
            return await ctx.send("Invalid album URL")
        
        album_id = match.group(1)
        
        try:
            album = await self.bot.loop.run_in_executor(
                None,
                self.session.album,
                album_id
            )
            
            tracks = await self.bot.loop.run_in_executor(
                None,
                album.tracks
            )
            
            total = len(tracks)
            await ctx.send(
                f"Queuing {album.name} by {album.artist.name} ({total} tracks)..."
            )
            
            queued = 0
            for track in tracks:
                try:
                    if await self.add_track(ctx, track):
                        queued += 1
                except Exception as e:
                    log.error(f"Error queuing track: {e}")
            
            await ctx.send(f"Queued {queued}/{total} tracks")
            
        except Exception as e:
            await ctx.send(f"Error: {str(e)}")
            log.error(f"Album error: {e}")
    
    async def queue_track(self, ctx, url):
        """Queue a single track."""
        
        match = re.search(r"track/([0-9]+)", url)
        if not match:
            return await ctx.send("Invalid track URL")
        
        track_id = match.group(1)
        
        try:
            track = await self.bot.loop.run_in_executor(
                None,
                self.session.track,
                track_id
            )
            
            if await self.add_track(ctx, track):
                await ctx.send(f"Queued: {track.name} by {track.artist.name}")
            else:
                await ctx.send(f"Failed to queue: {track.name}")
                
        except Exception as e:
            await ctx.send(f"Error: {str(e)}")
            log.error(f"Track error: {e}")
    
    async def add_track(self, ctx, track):
        """Add track to Audio queue."""
        
        try:
            query = f"{track.artist.name} - {track.name}"
            play_command = self.bot.get_command("play")
            
            if not play_command:
                log.error("Play command not found")
                return False
            
            await ctx.invoke(play_command, query=query)
            return True
            
        except Exception as e:
            log.error(f"Error adding track: {e}")
            return False


async def setup(bot):
    cog = TidalPlaylist(bot)
    await bot.add_cog(cog)