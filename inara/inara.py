import discord

from redbot.core import commands, app_commands

class inara(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command()
    @app_commands.describe(userid="ID-ul de utilizator de pe Inara.")
    async def inara(self, interaction: discord.Interaction, id: any):
        await interaction.response.send_message(f"ID-ul tau este {id.value}", ephemeral=True)
