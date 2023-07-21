from redbot.core import commands
import requests

class inara(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def inara(self, ctx, image_variable):
        try:
            # Replace 'YOUR_URL' with the base URL containing the variable
            url = f'https://inara.cz/data/sig/400/{image_variable}.jpg'
            response = requests.get(url)

            # Check if the request was successful
            if response.status_code == 200:
                # Get the image file name from the URL (you can adjust this based on your URL structure)
                file_name = url.split('/')[-1]

                # Create a discord.File object from the image data
                file = discord.File(response.content, filename=file_name)

                # Send the image as an attachment
                await ctx.send(file=file)
            else:
                await ctx.send("Image not found.")
        except Exception as e:
            await ctx.send(f"An error occurred: {e}")
