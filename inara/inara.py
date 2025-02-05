from redbot.core import commands
import discord
import aiohttp
import json
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

    @inara.command(name="debug")
    @commands.is_owner()
    async def debug_search(self, ctx: commands.Context, *, commander_name: str):
        """Debug search for a CMDR on Inara (Bot owner only)"""
        if not self.header.get("APIkey"):
            await ctx.send("API key has not been set. Please set it using `[p]inara setapikey`")
            return

        async with ctx.typing():
            # Try different name formats
            search_variations = [
                commander_name,
                commander_name.replace(" ", ""),
                commander_name.replace("'", ""),
                commander_name.lower(),
                commander_name.upper()
            ]

            for search_name in search_variations:
                data = {
                    "header": self.header,
                    "events": [{
                        "eventName": "getCommanderProfile",
                        "eventData": {
                            "searchName": search_name
                        }
                    }]
                }

                await ctx.send(f"Trying search with: {search_name}")

                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.post(self.api_url, json=data) as response:
                            result = await response.json()
                            # Pretty print the full response for debugging
                            formatted_response = json.dumps(result, indent=2)
                            # Split response into chunks to avoid Discord message length limit
                            chunks = [formatted_response[i:i+1994] for i in range(0, len(formatted_response), 1994)]
                            for chunk in chunks:
                                await ctx.send(f"```json\n{chunk}```")
                    except Exception as e:
                        await ctx.send(f"Error with {search_name}: {str(e)}")

    @inara.command()
    @commands.guild_only()
    async def cmdr(self, ctx: commands.Context, *, commander_name: str):
        """Search for a CMDR on Inara"""
        if not self.header.get("APIkey"):
            await ctx.send("API key has not been set. Please have the bot owner set it using `[p]inara setapikey`")
            return

        async with ctx.typing():
            # Remove 'CMDR' prefix if present and strip whitespace
            search_name = commander_name.replace('CMDR', '').strip()
            
            data = {
                "header": self.header,
                "events": [{
                    "eventName": "getCommanderProfile",
                    "eventData": {
                        "searchName": search_name
                    }
                }]
            }

            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(self.api_url, json=data) as response:
                        result = await response.json()
                        
                        if "events" in result and result["events"][0].get("eventStatus") == 200:
                            cmdr_data = result["events"][0]["eventData"]
                            
                            embed = discord.Embed(
                                title=f"CMDR {cmdr_data.get('commanderName', 'Unknown')}",
                                color=discord.Color.blue(),
                                url=cmdr_data.get('inaraURL', '')
                            )
                            
                            # Rest of the embed creation code remains the same...
                            # [Previous embed code here]
                            
                            await ctx.send(embed=embed)
                        else:
                            error_status = result.get("events", [{}])[0].get("eventStatus", "Unknown")
                            error_msg = result.get("events", [{}])[0].get("eventStatusText", "Unknown error")
                            await ctx.send(f"No data found for CMDR {commander_name}. Status: {error_status}, Error: {error_msg}")
                except Exception as e:
                    await ctx.send(f"Error occurred while fetching data: {str(e)}")

    @inara.command()
    @commands.is_owner()
    async def setapikey(self, ctx: commands.Context, api_key: str):
        """Set the Inara API key (Bot owner only)"""
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.message.delete()
        
        await self.bot.set_shared_api_tokens("inara", api_key=api_key)
        self.header["APIkey"] = api_key
        await ctx.send("API key has been set.", delete_after=5)

    @commands.Cog.listener()
    async def on_red_api_tokens_update(self, service_name: str, api_tokens: Optional[dict]):
        """Update API key if it's changed through Discord."""
        if service_name == "inara" and api_tokens:
            self.header["APIkey"] = api_tokens.get("api_key")
