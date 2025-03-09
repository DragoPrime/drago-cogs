from .claudeai import setup

async def setup(bot):
    """Add the cog to the bot"""
    await bot.add_cog(ClaudeAI(bot))

__red_end_user_data_statement__ = (
    "This cog stores Discord channel IDs where Claude AI is enabled. "
    "No personal user data is stored."
)
