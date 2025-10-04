from .tidalplaylist import TidalPlaylist

async def setup(bot):
    await bot.add_cog(TidalPlaylist(bot))