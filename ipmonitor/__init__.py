from .ipmonitor import IPMonitor


async def setup(bot):
    """Funcție pentru încărcarea cog-ului."""
    cog = IPMonitor(bot)
    await bot.add_cog(cog)
