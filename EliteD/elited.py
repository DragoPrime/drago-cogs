import discord

from redbot.core import commands, app_commands

class MEliteD(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command()
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hello World!", ephemeral=True)
