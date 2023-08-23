import discord
from redbot.core import commands
import aiohttp
import os

class inara(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def inara(self, ctx, image_variable: str):
        try:
            base_url = 'https://inara.cz/data/sig/400/'
            image_url = base_url + image_variable + '.jpg'

            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status == 200:
                        content_type = response.headers.get("Content-Type", "")
                        if not content_type.startswith("image"):
                            await ctx.send("The URL does not point to an image.")
                            return

                        image_data = await response.read()

                        # Save image data to a temporary file
                        temp_file_path = f"temp_{image_variable}.jpg"
                        with open(temp_file_path, "wb") as temp_file:
                            temp_file.write(image_data)

                        # Send the saved image as an attachment
                        await ctx.send(file=discord.File(temp_file_path))

                        # Delete the temporary file after sending
                        os.remove(temp_file_path)
                    else:
                        await ctx.send("Image not found.")
        except aiohttp.ClientError as e:
            await ctx.send("An error occurred while fetching the image.")
