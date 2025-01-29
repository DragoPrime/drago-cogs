from .jellyfin import JellyfinSearch

async def setup(bot):
    await bot.add_cog(JellyfinSearch(bot))
