from .inara import InaraCog

async def setup(bot):
    await bot.add_cog(InaraCog(bot))
