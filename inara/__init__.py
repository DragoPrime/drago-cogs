from .inara import inara


async def setup(bot):
    await bot.add_cog(inara(bot))
