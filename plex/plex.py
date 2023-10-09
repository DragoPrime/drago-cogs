import discord
from discord.ext import commands
import requests

# Define your Plex server API base URL and token here
PLEX_BASE_URL = 'https://your-plex-server-url.com'
PLEX_TOKEN = 'your-plex-api-token'

class PlexCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def play(self, ctx, media_name):
        """Command to play media from Plex server."""
        try:
            # Build the Plex API URL to search for media by name
            search_url = f'{PLEX_BASE_URL}/search?type=1&query={media_name}'
            
            # Set headers with the Plex token
            headers = {'X-Plex-Token': PLEX_TOKEN}

            # Make a GET request to search for the media
            response = requests.get(search_url, headers=headers)

            # Check if the request was successful
            if response.status_code == 200:
                # Parse the response JSON to get the media URL
                media_url = response.json()['MediaContainer']['Metadata'][0]['Media'][0]['Part'][0]['file']
                
                # Send a message to Discord with the media URL
                await ctx.send(f'Playing {media_name} from Plex: {media_url}')
            else:
                await ctx.send('Failed to find the media.')
        
        except Exception as e:
            await ctx.send(f'An error occurred: {str(e)}')

def setup(bot):
    bot.add_cog(PlexCog(bot))
