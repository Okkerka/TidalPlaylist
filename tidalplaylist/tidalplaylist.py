import discord
from redbot.core import commands, Config
import asyncio
import re
import logging

log = logging.getLogger("red.tidalplaylist")


class TidalPlaylist(commands.Cog):
    """Play Tidal links directly via Lavalink with LavaSrc plugin."""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self,
            identifier=1234567890,
            force_registration=True
        )
        
        default_global = {
            "use_direct_streaming": True,
            "quiet_mode": True  # New: suppress per-track messages
        }
        self.config.register_global(**default_global)
    
    @commands.is_owner()
    @commands.command()
    async def tidaldirect(self, ctx, enabled: bool = None):
        """
        Toggle direct Tidal streaming via Lavalink.
        
        If enabled, sends Tidal URLs directly to Lavalink (requires LavaSrc plugin).
        If disabled, falls back to YouTube search.
        """
        if enabled is None:
            current = await self.config.use_direct_streaming()
            status = "enabled" if current else "disabled"
            return await ctx.send(f"Direct Tidal streaming is currently **{status}**.")
        
        await self.config.use_direct_streaming.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"Direct Tidal streaming has been **{status}**.")
        
        if enabled:
            await ctx.send(
                "⚠️ Make sure you have LavaSrc plugin installed on your Lavalink server "
                "with Tidal configured!"
            )
    
    @commands.is_owner()
    @commands.command()
    async def tidalquiet(self, ctx, enabled: bool = None):
        """
        Toggle quiet mode (suppress per-track messages).
        
        When enabled, only shows summary messages for playlists/albums.
        """
        if enabled is None:
            current = await self.config.quiet_mode()
            status = "enabled" if current else "disabled"
            return await ctx.send(f"Quiet mode is currently **{status}**.")
        
        await self.config.quiet_mode.set(enabled)
        status = "enabled" if enabled else "disabled"
        await ctx.send(f"Quiet mode has been **{status}**.")
    
    @commands.command()
    async def tidal(self, ctx, url: str):
        """
        Queue Tidal playlist, album, or track.
        Example: [p]tidal https://tidal.com/browse/playlist/xxxx
        """
        audio = self.bot.get_cog("Audio")
        if not audio:
            return await ctx.send("Audio cog not loaded")
        
        if not ctx.author.voice:
            return await ctx.send("Join a voice channel first")
        
        use_direct = await self.config.use_direct_streaming()
        
        if use_direct:
            # Send Tidal URL directly to Lavalink (requires LavaSrc)
            await self.queue_direct(ctx, url)
        else:
            await ctx.send("Direct streaming is disabled. Enable with `[p]tidaldirect true`")
    
    async def queue_direct(self, ctx, url):
        """Queue Tidal URL directly via Lavalink."""
        try:
            play_command = self.bot.get_command("play")
            
            if not play_command:
                return await ctx.send("Play command not found")
            
            # Clean the URL
            clean_url = url.strip()
            
            quiet_mode = await self.config.quiet_mode()
            
            # Check if it's a playlist or album (multiple tracks)
            is_collection = any(x in clean_url for x in ["playlist/", "album/"])
            
            if is_collection:
                # Show initial message for collections
                loading_msg = await ctx.send("⏳ Loading from Tidal...")
                
                # Invoke play command
                # Temporarily suppress Audio cog messages by invoking without response
                try:
                    # Store original channel
                    original_channel = ctx.channel
                    
                    # If quiet mode, we'll let Audio handle it but add summary after
                    await ctx.invoke(play_command, query=clean_url)
                    
                    # Delete loading message
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                    
                    # Send completion message
                    if quiet_mode:
                        await ctx.send("✅ Tidal playlist/album queued successfully!")
                        
                except Exception as e:
                    await loading_msg.edit(content=f"Error: {str(e)}")
            else:
                # Single track - just invoke normally
                if quiet_mode:
                    # For single tracks in quiet mode, let Audio cog handle the message
                    await ctx.invoke(play_command, query=clean_url)
                else:
                    await ctx.send("🎵 Queueing from Tidal...")
                    await ctx.invoke(play_command, query=clean_url)
            
        except Exception as e:
            await ctx.send(f"Error: {str(e)}\n\nMake sure LavaSrc plugin is installed on Lavalink!")
            log.error(f"Direct Tidal error: {e}")


async def setup(bot):
    """Setup function for Red-DiscordBot."""
    cog = TidalPlaylist(bot)
    await bot.add_cog(cog)