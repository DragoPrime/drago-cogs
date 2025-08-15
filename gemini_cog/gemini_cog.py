import discord
from redbot.core import commands, Config
import google.generativeai as genai

class GeminiCog(commands.Cog):
    """
    Un cog simplu pentru a interacționa cu Gemini API.
    """

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_global = {
            "api_key": None
        }
        self.config.register_global(**default_global)

    @commands.command()
    async def setgeminikey(self, ctx, api_key: str):
        """
        Setează cheia API pentru Gemini.
        """
        await self.config.api_key.set(api_key)
        await ctx.send("Cheia API pentru Gemini a fost setată cu succes.")

    @commands.command()
    async def askgemini(self, ctx, *, question: str):
        """
        Trimite o întrebare la Gemini și afișează răspunsul.
        Exemplu: `!askgemini Câte planete sunt în sistemul solar?`
        """
        api_key = await self.config.api_key()
        if not api_key:
            await ctx.send("Cheia API pentru Gemini nu a fost configurată. Folosește `!setgeminikey <cheia_ta>` pentru a o seta.")
            return

        genai.configure(api_key=api_key)
        try:
            model = genai.GenerativeModel('gemini-pro')
            response = model.generate_content(question)
            
            if response and response.text:
                await ctx.send(f"**Răspunsul meu:** {response.text}")
            else:
                await ctx.send("Îmi pare rău, nu am putut genera un răspuns valid.")
        except Exception as e:
            await ctx.send(f"A apărut o eroare: {e}")
