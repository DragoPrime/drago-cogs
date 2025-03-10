import discord
from redbot.core import commands, Config
import aiohttp
import asyncio
from datetime import datetime, timedelta

class JellyfinLibraryStats(commands.Cog):
    """Cog pentru monitorizarea statisticilor bibliotecilor Jellyfin"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        # Configurație persistentă pentru Jellyfin
        self.config.register_global(
            jellyfin_url=None,
            jellyfin_api_key=None,
            update_channel_id=None,
            update_message_id=None,
            last_update=None
        )
        
        # Task pentru actualizare
        self.update_task = None

    @commands.group(name="jellyfinstats")
    @commands.admin()
    async def jellyfin_stats(self, ctx):
        """Comenzi pentru configurarea statisticilor Jellyfin"""
        if not ctx.invoked_subcommand:
            # Afișează configurarea curentă
            url = await self.config.jellyfin_url()
            channel_id = await self.config.update_channel_id()
            
            if url and channel_id:
                await ctx.send(f"Configurare curentă:\n"
                               f"Jellyfin URL: {url}\n"
                               f"Canal actualizare: <#{channel_id}>")
            else:
                await ctx.send("Nicio configurare salvată. Utilizați !jellyfinstats setup pentru a configura.")

    @jellyfin_stats.command(name="setup")
    async def setup_jellyfin_stats(self, ctx, jellyfin_url: str, api_key: str, channel: discord.TextChannel):
        """Configurează URL-ul Jellyfin, API key-ul și canalul de actualizare"""
        # Salvează configurația
        await self.config.jellyfin_url.set(jellyfin_url)
        await self.config.jellyfin_api_key.set(api_key)
        await self.config.update_channel_id.set(channel.id)
        
        # Trimite mesajul inițial care va fi actualizat
        message = await channel.send("Actualizare statistici biblioteci Freia...")
        await self.config.update_message_id.set(message.id)

        # Declanșează actualizarea imediată
        await self.update_stats_message(force_update=True)

        await ctx.send("Configurare Jellyfin stats completată cu succes!")

    @jellyfin_stats.command(name="update")
    async def manual_update(self, ctx):
        """Actualizează manual statisticile"""
        await self.update_stats_message(force_update=True)
        await ctx.send("Statistici actualizate manual!")

    async def fetch_jellyfin_libraries(self):
        """Preia informațiile bibliotecilor de pe serverul Jellyfin"""
        jellyfin_url = await self.config.jellyfin_url()
        api_key = await self.config.jellyfin_api_key()

        if not jellyfin_url or not api_key:
            return None

        headers = {
            "X-Emby-Token": api_key
        }

        async with aiohttp.ClientSession() as session:
            # Preia lista de biblioteci
            async with session.get(f"{jellyfin_url}/Library/MediaFolders", headers=headers) as libraries_response:
                if libraries_response.status == 200:
                    libraries = await libraries_response.json()
                    
                    # Colectează statisticile pentru fiecare bibliotecă
                    library_stats = {}
                    for library in libraries.get('Items', []):
                        library_id = library.get('Id')
                        library_name = library.get('Name')
                        
                        # Preia numărul de elemente pentru fiecare bibliotecă
                        async with session.get(f"{jellyfin_url}/Items/Counts?parentId={library_id}", headers=headers) as count_response:
                            if count_response.status == 200:
                                counts = await count_response.json()
                                library_stats[library_name] = counts.get('ItemCount', 0)
                    
                    return library_stats
                else:
                    return None

    async def update_stats_message(self, force_update=False):
        """Actualizează mesajul cu statisticile bibliotecilor"""
        # Verifică dacă sunt configurate toate elementele necesare
        jellyfin_url = await self.config.jellyfin_url()
        channel_id = await self.config.update_channel_id()
        message_id = await self.config.update_message_id()
        
        if not all([jellyfin_url, channel_id, message_id]):
            return

        try:
            # Preia statisticile bibliotecilor
            library_stats = await self.fetch_jellyfin_libraries()

            if library_stats:
                channel = self.bot.get_channel(channel_id)
                
                # Construiește mesajul cu statistici
                embed = discord.Embed(
                    title="📊 Statistici Biblioteci Freia",
                    description=f"Actualizat la: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    color=discord.Color.blue()
                )
                
                # Adaugă statistici pentru fiecare bibliotecă
                for library_name, item_count in library_stats.items():
                    embed.add_field(name=library_name, value=str(item_count), inline=False)

                # Actualizează mesajul
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)

                # Salvează ultima dată de actualizare
                await self.config.last_update.set(datetime.now().isoformat())

        except Exception as e:
            print(f"Eroare la actualizarea statisticilor: {e}")

    async def background_update(self):
        """Task de fundal pentru actualizare zilnică"""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                # Actualizează o dată la 24 de ore
                await self.update_stats_message()
                await asyncio.sleep(86400)  # 24 de ore
            except Exception as e:
                print(f"Eroare în task-ul de fundal: {e}")
                await asyncio.sleep(3600)  # Așteaptă o oră în caz de eroare

    def cog_unload(self):
        """Oprește task-ul când cog-ul este descărcat"""
        if self.update_task:
            self.update_task.cancel()

    async def cog_load(self):
        """Pornește task-ul de actualizare când cog-ul este încărcat"""
        # Pornește actualizarea inițială
        await self.update_stats_message(force_update=True)
        
        # Pornește task-ul de fundal pentru actualizări zilnice
        self.update_task = self.bot.loop.create_task(self.background_update())
