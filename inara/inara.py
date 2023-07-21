import discord
from redbot.core import commands
import aiohttp

class inara(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def inara(self, ctx, image_variable):
        try:
            # Replace 'YOUR_URL' with the base URL containing the variable
            url = f'https://inara.cz/data/sig/400/{image_variable}.jpg'

            # Fetch the image data using discord.http
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        # Check if the response content type is an image
                        content_type = response.headers.get("Content-Type", "")
                        if not content_type.startswith("image"):
                            await ctx.send("The URL does not point to an image.")
                            return

                        # Get the image file name from the URL (you can adjust this based on your URL structure)
                        file_name = url.split("/")[-1]

                        # Send the image as an attachment
                        await ctx.send(file=discord.File(await response.read(), filename=file_name))
                    else:
                        await ctx.send("Image not found.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
