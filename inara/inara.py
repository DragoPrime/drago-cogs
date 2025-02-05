from redbot.core import commands
import discord
import aiohttp
from datetime import datetime
from typing import Optional

class InaraCog(commands.Cog):
    """Cog for interacting with Inara.cz API"""
    
    def __init__(self, bot):
        self.bot = bot
        self.api_url = "https://inara.cz/inapi/v1/"
        self.api_key = None
        self.header = {
            "appName": "RedDiscordBot-InaraCog",
            "appVersion": "1.0",
            "isDeveloped": True,
            "APIkey": None
        }

    async def cog_load(self):
        """Initialize the cog when it's loaded."""
        self.api_key = await self.bot.get_shared_api_tokens("inara")
        if self.api_key.get("api_key"):
            self.header["APIkey"] = self.api_key["api_key"]

    @commands.group()
    async def inara(self, ctx: commands.Context):
        """Inara.cz commands"""
        pass

    @inara.command()
    @commands.is_owner()
    async def setapikey(self, ctx: commands.Context, api_key: str):
        """Set the Inara API key (Bot owner only)
        
        Args:
            api_key: Your Inara.cz API key
        """
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.message.delete()
        
        await self.bot.set_shared_api_tokens("inara", api_key=api_key)
        self.header["APIkey"] = api_key
        await ctx.send("API key has been set.", delete_after=5)

    @inara.command()
    @commands.guild_only()
    async def cmdr(self, ctx: commands.Context, *, commander_name: str):
        """Search for a CMDR on Inara
        
        Args:
            commander_name: The name of the commander to search for
        """
        if not self.header.get("APIkey"):
            await ctx.send("API key has not been set. Please have the bot owner set it using `[p]inara setapikey`")
            return

        async with ctx.typing():
            data = {
                "header": self.header,
                "events": [{
                    "eventName": "getCommanderProfile",
                    "eventData": {
                        "searchName": commander_name
                    }
                }]
            }

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(self.api_url, json=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            
                            if "events" in result and result["events"][0].get("eventStatus") == 200:
                                cmdr_data = result["events"][0]["eventData"]
                                
                                embed = discord.Embed(
                                    title=f"CMDR {cmdr_data.get('commanderName', 'Unknown')}",
                                    color=discord.Color.blue(),
                                    url=cmdr_data.get('inaraURL', '')
                                )
                                
                                # Add avatar if available
                                if avatar_url := cmdr_data.get('avatarImageURL'):
                                    embed.set_thumbnail(url=avatar_url)
                                
                                # Basic info
                                if role := cmdr_data.get('preferredGameRole'):
                                    embed.add_field(
                                        name="Preferred Role",
                                        value=role,
                                        inline=True
                                    )
                                
                                if squadron := cmdr_data.get('squadronName'):
                                    embed.add_field(
                                        name="Squadron",
                                        value=squadron,
                                        inline=True
                                    )
                                
                                # Ranks
                                ranks = []
                                if combat_rank := cmdr_data.get('commanderRanksPilot'):
                                    ranks.append(f"Combat: {combat_rank}")
                                if trade_rank := cmdr_data.get('commanderRanksTrade'):
                                    ranks.append(f"Trade: {trade_rank}")
                                if explore_rank := cmdr_data.get('commanderRanksExplorer'):
                                    ranks.append(f"Explorer: {explore_rank}")
                                
                                if ranks:
                                    embed.add_field(
                                        name="Ranks",
                                        value="\n".join(ranks),
                                        inline=False
                                    )
                                
                                # Location and activity
                                if location := cmdr_data.get('preferredAllegianceName'):
                                    embed.add_field(
                                        name="Allegiance",
                                        value=location,
                                        inline=True
                                    )
                                
                                if last_seen := cmdr_data.get('lastActivityDate'):
                                    last_active = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                                    embed.add_field(
                                        name="Last Active",
                                        value=last_active.strftime("%Y-%m-%d %H:%M UTC"),
                                        inline=True
                                    )
                                
                                embed.set_footer(text="Data provided by Inara.cz")
                                await ctx.send(embed=embed)
                            else:
                                await ctx.send(f"No data found for CMDR {commander_name}")
                        else:
                            await ctx.send(f"Error accessing Inara API: {response.status}")
                except Exception as e:
                    await ctx.send(f"Error occurred while fetching data: {str(e)}")

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name: str, api_tokens: Optional[dict]):
        """Update API key if it's changed through Discord."""
        if service_name == "inara" and api_tokens:
            self.header["APIkey"] = api_tokens.get("api_key")
