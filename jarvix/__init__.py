from .jarvix import Jarvix


async def setup(bot):
    await bot.add_cog(Jarvix(bot))
