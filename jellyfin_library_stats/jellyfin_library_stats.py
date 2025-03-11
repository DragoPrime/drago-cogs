import discord
from redbot.core import commands, Config, app_commands
import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta

# Configurare logging
log = logging.getLogger("red.jellyfinlibs")

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
        # Asigură-te că URL-ul se termină fără slash
        if jellyfin_url.endswith("/"):
            jellyfin_url = jellyfin_url[:-1]
            
        # Salvează configurația
        await self.config.jellyfin_url.set(jellyfin_url)
        await self.config.jellyfin_api_key.set(api_key)
        await self.config.update_channel_id.set(channel.id)
        
        # Trimite mesajul inițial care va fi actualizat
        message = await channel.send("Actualizare statistici biblioteci Jellyfin...")
        await self.config.update_message_id.set(message.id)

        # Încearcă să testezi conexiunea
        success = await self.test_connection()
        if success:
            await ctx.send("Conexiunea la Jellyfin a fost testată și funcționează!")
        else:
            await ctx.send("⚠️ Configurare salvată, dar testul de conexiune a eșuat. Verifică URL-ul și API key-ul.")
        
        # Declanșează actualizarea imediată
        await self.update_stats(force_update=True)
        await ctx.send("Configurare Jellyfin stats completată!")

    @jellyfin_stats.command(name="test")
    async def test_api(self, ctx):
        """Testează conexiunea la API-ul Jellyfin"""
        success = await self.test_connection()
        if success:
            await ctx.send("✅ Conexiunea la Jellyfin funcționează corect!")
        else:
            await ctx.send("❌ Conexiunea la Jellyfin a eșuat. Verifică URL-ul și API key-ul.")

    @jellyfin_stats.command(name="debug")
    async def debug_api(self, ctx):
        """Afișează informații de debug despre API"""
        jellyfin_url = await self.config.jellyfin_url()
        api_key = await self.config.jellyfin_api_key()
        
        if not jellyfin_url or not api_key:
            return await ctx.send("Nicio configurare salvată.")
        
        debug_info = []
        debug_info.append(f"**URL Jellyfin**: {jellyfin_url}")
        debug_info.append(f"**API Key** (primele 4 caractere): {api_key[:4]}...")
        
        # Testează endpoint-ul pentru librării
        async with aiohttp.ClientSession() as session:
            headers = {"X-Emby-Token": api_key}
            
            # Test pentru /System/Info
            try:
                url = f"{jellyfin_url}/System/Info"
                debug_info.append(f"\n**Testare endpoint**: `{url}`")
                async with session.get(url, headers=headers) as response:
                    debug_info.append(f"Status: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        debug_info.append(f"Versiune Jellyfin: {data.get('Version', 'N/A')}")
                    else:
                        debug_info.append("❌ Eroare la accesarea informațiilor despre server")
            except Exception as e:
                debug_info.append(f"❌ Excepție: {str(e)}")
            
            # Test pentru /Library/MediaFolders
            try:
                url = f"{jellyfin_url}/Library/MediaFolders"
                debug_info.append(f"\n**Testare endpoint**: `{url}`")
                async with session.get(url, headers=headers) as response:
                    debug_info.append(f"Status: {response.status}")
                    if response.status == 200:
                        data = await response.json()
                        items = data.get('Items', [])
                        debug_info.append(f"Număr de biblioteci: {len(items)}")
                        for item in items:
                            debug_info.append(f"- ID: {item.get('Id')}, Nume: {item.get('Name')}")
                    else:
                        debug_info.append("❌ Eroare la accesarea bibliotecilor")
            except Exception as e:
                debug_info.append(f"❌ Excepție: {str(e)}")
        
        await ctx.send("\n".join(debug_info))

    @jellyfin_stats.command(name="update")
    async def manual_update(self, ctx):
        """Actualizează manual statisticile"""
        await ctx.send("Începe actualizarea manuală...")
        success = await self.update_stats(force_update=True)
        if success:
            await ctx.send("✅ Statistici actualizate manual!")
        else:
            await ctx.send("❌ Actualizarea manuală a eșuat. Verifică log-urile pentru detalii.")

    async def test_connection(self):
        """Testează dacă conexiunea la Jellyfin funcționează"""
        jellyfin_url = await self.config.jellyfin_url()
        api_key = await self.config.jellyfin_api_key()

        if not jellyfin_url or not api_key:
            return False

        headers = {"X-Emby-Token": api_key}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{jellyfin_url}/System/Info", headers=headers) as response:
                    if response.status == 200:
                        log.info("Conexiune la Jellyfin testată cu succes!")
                        return True
                    else:
                        log.error(f"Conexiunea la Jellyfin a eșuat: Status {response.status}")
                        return False
        except Exception as e:
            log.error(f"Excepție la testarea conexiunii Jellyfin: {e}")
            return False

    async def fetch_jellyfin_libraries(self):
        """Preia informațiile bibliotecilor de pe serverul Jellyfin"""
        jellyfin_url = await self.config.jellyfin_url()
        api_key = await self.config.jellyfin_api_key()

        if not jellyfin_url or not api_key:
            log.error("URL-ul sau API key-ul nu sunt configurate")
            return None

        headers = {"X-Emby-Token": api_key}

        try:
            async with aiohttp.ClientSession() as session:
                # Preia lista de biblioteci
                log.info(f"Preluare biblioteci de la {jellyfin_url}/Library/MediaFolders")
                async with session.get(f"{jellyfin_url}/Library/MediaFolders", headers=headers) as libraries_response:
                    log.info(f"Status răspuns: {libraries_response.status}")
                    
                    if libraries_response.status == 200:
                        libraries_data = await libraries_response.json()
                        libraries = libraries_data.get('Items', [])
                        log.info(f"Număr biblioteci găsite: {len(libraries)}")
                        
                        # Colectează statisticile pentru fiecare bibliotecă
                        library_stats = {}
                        for library in libraries:
                            library_id = library.get('Id')
                            library_name = library.get('Name')
                            
                            # Ignoră biblioteca Playlists
                            if "playlist" in library_name.lower():
                                log.info(f"Ignorare bibliotecă: {library_name} (este playlist)")
                                continue
                            
                            log.info(f"Procesare bibliotecă: {library_name} (ID: {library_id})")
                            
                            # Verifică tipul de colecție
                            collection_type = library.get('CollectionType', '').lower()
                            
                            # Folosește endpoint-ul Items cu parametrii corecți
                            try:
                                items_url = ""
                                if "tvshows" in collection_type or "tv" in collection_type:
                                    # Pentru biblioteci TV, numără doar serialele, nu episoadele
                                    items_url = f"{jellyfin_url}/Items?ParentId={library_id}&IncludeItemTypes=Series&Recursive=true&Limit=0"
                                    log.info(f"Bibliotecă TV detectată, numărare seriale: {items_url}")
                                else:
                                    # Pentru alte tipuri, folosește comportamentul standard
                                    items_url = f"{jellyfin_url}/Items?ParentId={library_id}&Recursive=true&Limit=0"
                                    log.info(f"Bibliotecă standard: {items_url}")
                                
                                async with session.get(items_url, headers=headers) as items_response:
                                    log.info(f"Status răspuns items: {items_response.status}")
                                    
                                    if items_response.status == 200:
                                        items_data = await items_response.json()
                                        total_records = items_data.get('TotalRecordCount', 0)
                                        log.info(f"Total înregistrări în {library_name}: {total_records}")
                                        library_stats[library_name] = total_records
                                    else:
                                        log.error(f"Eroare la accesarea elementelor din biblioteca {library_name}: {items_response.status}")
                                        library_stats[library_name] = 0
                            except Exception as e:
                                log.error(f"Excepție la obținerea numărului pentru biblioteca {library_name}: {e}")
                                library_stats[library_name] = 0
                        
                        if library_stats:
                            log.info(f"Stats colectate cu succes: {library_stats}")
                            return library_stats
                        else:
                            log.error("Nu s-au găsit statistici")
                            return None
                    else:
                        log.error(f"Eroare la accesarea bibliotecilor: {libraries_response.status}")
                        return None
        except Exception as e:
            log.error(f"Excepție generală la preluarea bibliotecilor: {e}")
            return None

    async def update_stats(self, force_update=False):
        """Actualizează mesajul cu statisticile bibliotecilor"""
        # Verifică dacă sunt configurate toate elementele necesare
        jellyfin_url = await self.config.jellyfin_url()
        channel_id = await self.config.update_channel_id()
        message_id = await self.config.update_message_id()
        
        if not all([jellyfin_url, channel_id, message_id]):
            log.error("Configurația nu este completă")
            return False

        try:
            # Preia statisticile bibliotecilor
            log.info("Începe actualizarea statisticilor")
            library_stats = await self.fetch_jellyfin_libraries()

            if library_stats:
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    log.error(f"Canalul {channel_id} nu a fost găsit")
                    return False
                
                # Construiește mesajul cu statistici
                embed = discord.Embed(
                    title="📊 Statistici Biblioteci Jellyfin",
                    description=f"Actualizat la: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    color=discord.Color.blue()
                )
                
                # Adaugă statistici pentru fiecare bibliotecă
                for library_name, item_count in library_stats.items():
                    embed.add_field(name=library_name, value=str(item_count), inline=False)

                # Actualizează mesajul
                try:
                    message = await channel.fetch_message(message_id)
                    await message.edit(embed=embed)
                    log.info("Mesajul a fost actualizat cu succes")
                except discord.NotFound:
                    log.error(f"Mesajul {message_id} nu a fost găsit")
                    return False
                except Exception as e:
                    log.error(f"Eroare la actualizarea mesajului: {e}")
                    return False

                # Salvează ultima dată de actualizare
                await self.config.last_update.set(datetime.now().isoformat())
                return True
            else:
                log.error("Nu s-au putut prelua statisticile bibliotecilor")
                return False

        except Exception as e:
            log.error(f"Eroare generală la actualizarea statisticilor: {e}")
            return False

    async def background_update(self):
        """Task de fundal pentru actualizare săptămânală"""
        await self.bot.wait_until_ready()

        while not self.bot.is_closed():
            try:
                # Actualizează o dată la 7 zile (săptămânal)
                log.info("Pornire actualizare săptămânală")
                await self.update_stats()
                await asyncio.sleep(604800)  # 7 zile (7 * 24 * 60 * 60 = 604800 secunde)
            except Exception as e:
                log.error(f"Eroare în task-ul de fundal: {e}")
                await asyncio.sleep(3600)  # Așteaptă o oră în caz de eroare

    def cog_unload(self):
        """Oprește task-ul când cog-ul este descărcat"""
        if self.update_task:
            self.update_task.cancel()

    async def cog_load(self):
        """Pornește task-ul de actualizare când cog-ul este încărcat"""
        log.info("Cog Jellyfin Library Stats încărcat")
        # Pornește actualizarea inițială
        await self.update_stats(force_update=True)
        
        # Pornește task-ul de fundal pentru actualizări săptămânale
        self.update_task = self.bot.loop.create_task(self.background_update())
