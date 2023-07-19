from .elited import EliteD


async def setup(bot):
    await bot.add_cog(EliteD(bot))