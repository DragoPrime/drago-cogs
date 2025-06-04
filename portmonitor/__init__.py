from .portmonitor import PortMonitor


async def setup(bot):
    """Funcția de setup pentru plugin"""
    await bot.add_cog(PortMonitor(bot))
