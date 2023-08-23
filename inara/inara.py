import discord
from redbot.core import commands
import aiohttp
from io import BytesIO

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

                        # Pass image data to a BytesIO object
                        image_bytesio = BytesIO(image_data)

                        # Replace ".jpg" with a slash in the URL and send
                        url_without_extension = image_url.replace(".jpg", "/")
                        await ctx.send(url_without_extension)

                        # Send the image as an attachment
                        await ctx.send(file=discord.File(image_bytesio, filename=f"{image_variable}.jpg"))
                    else:
                        await ctx.send("Image not found.")
        except aiohttp.ClientError as e:
            await ctx.send("An error occurred while fetching the image.")
