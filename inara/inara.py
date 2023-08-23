import discord
from redbot.core import commands
import aiohttp

class inara(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def inara(self, ctx, image_variable: str):
        try:
            # Sanitize the input by removing null bytes
            image_variable = image_variable.replace("\x00", "")

            base_url = 'https://inara.cz/data/sig/400/'
            url = f'{base_url}{image_variable}.jpg'

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content_type = response.headers.get("Content-Type", "")
                        if not content_type.startswith("image"):
                            await ctx.send("The URL does not point to an image.")
                            return

                        image_data = await response.read()
                        filename = f"{image_variable}.jpg"
                        await ctx.send(file=discord.File(image_data, filename=filename))
                    else:
                        await ctx.send("Image not found.")
        except aiohttp.ClientError as e:
            await ctx.send("An error occurred while fetching the image.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
