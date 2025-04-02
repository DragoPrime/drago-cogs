from .jellyfin_monitor import JellyfinMonitor

async def setup(bot):
    await bot.add_cog(JellyfinMonitor(bot))
