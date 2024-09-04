import discord
from discord.ext import commands
import aiohttp

class JellyfinCog(commands.Cog):
    def __init__(self, bot, server_url, username, password):
        self.bot = bot
        self.server_url = server_url
        self.username = username
        self.password = password
        self.access_token = None
        self.user_id = None
        
        bot.loop.create_task(self.authenticate())  # Authenticate when the bot starts

    async def authenticate(self):
        """Authenticate with the Jellyfin server and retrieve an access token."""
        auth_url = f"{self.server_url}/Users/AuthenticateByName"
        async with aiohttp.ClientSession() as session:
            async with session.post(auth_url, json={
                "Username": self.username,
                "Pw": self.password
            }) as response:
                if response.status == 200:
                    data = await response.json()
                    self.access_token = data['AccessToken']
                    self.user_id = data['User']['Id']
                else:
                    print(f"Failed to authenticate with Jellyfin: {response.status}")
    
    @commands.command(name='search')
    async def search(self, ctx, *, query):
        """Search for a title in the Jellyfin library."""
        if not self.access_token:
            await ctx.send("I'm not authenticated with the Jellyfin server yet. Please wait a moment.")
            return

        search_url = f"{self.server_url}/Users/{self.user_id}/Items"
        headers = {
            "X-Emby-Token": self.access_token
        }
        params = {
            "searchTerm": query,
            "IncludeItemTypes": "Movie,Series",  # Adjust this to your needs
            "Limit": 1  # Change this if you want more results
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(search_url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if not data['Items']:
                        await ctx.send(f"No results found for '{query}'.")
                        return

                    item = data['Items'][0]
                    title = item['Name']
                    overview = item.get('Overview', 'No description available.')
                    item_id = item['Id']
                    item_type = item['Type']
                    url = f"{self.server_url}/web/index.html#!/details?id={item_id}&type={item_type.lower()}"

                    embed = discord.Embed(title=title, description=overview, url=url)
                    if 'ImageTags' in item and 'Primary' in item['ImageTags']:
                        image_url = f"{self.server_url}/Items/{item_id}/Images/Primary?maxHeight=400"
                        embed.set_image(url=image_url)
                    
                    await ctx.send(embed=embed)
                else:
                    await ctx.send(f"Failed to search Jellyfin: {response.status}")
                    print(f"Failed to search Jellyfin: {response.status}")

def setup(bot):
    # Replace these values with your Jellyfin server details
    server_url = 'http://your-jellyfin-server:8096'
    username = 'your_username'
    password = 'your_password'

    bot.add_cog(JellyfinCog(bot, server_url, username, password))
