from .jellyfin_library_stats import JellyfinLibraryStats

async def setup(bot):
    await bot.add_cog(JellyfinLibraryStats(bot))
