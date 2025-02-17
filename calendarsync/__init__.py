from .calendarsync import CalendarSync

async def setup(bot):
    await bot.add_cog(CalendarSync(bot))
