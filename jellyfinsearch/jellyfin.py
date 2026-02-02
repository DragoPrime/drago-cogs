from redbot.core import commands, Config
import aiohttp
import urllib.parse
import discord
from datetime import datetime
from typing import List, Dict, Any
import asyncio


class JellyfinSearchView(discord.ui.View):
    """View for paginated Jellyfin search results"""
    
    def __init__(self, cog, ctx, items: List[Dict[Any, Any]], query: str, total_results: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.items = items
        self.query = query
        self.total_results = total_results
        self.current_page = 0
        self.total_pages = len(items)
        
        self._update_buttons()
    
    def _update_buttons(self):
        """Actualizează starea butoanelor în funcție de pagina curentă"""
        self.children[0].disabled = self.current_page == 0
        self.children[1].disabled = self.current_page >= self.total_pages - 1
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Verifică dacă utilizatorul care interacționează este cel care a inițiat comanda"""
        if interaction.user != self.ctx.author:
            await interaction.response.send_message(
                "Doar persoana care a inițiat comanda poate naviga prin rezultate.", 
                ephemeral=True
            )
            return False
        return True
    
    def get_current_page_embed(self) -> discord.Embed:
        """Creează un embed pentru un singur rezultat (pagina curentă)"""
        item = self.items[self.current_page]
        
        title = item.get('Name', 'Titlu necunoscut')
        if year := item.get('ProductionYear'):
            title += f" ({year})"
            
        embed = discord.Embed(
            title=f"Rezultatul {self.current_page + 1} pentru '{self.query}'",
            description=title,
            color=discord.Color.blue()
        )
        
        item_type = item.get('Type', 'Tip necunoscut')
        if item_type == "Movie":
            item_type = "Film"
        elif item_type == "Series":
            item_type = "Serial"
        embed.add_field(name="Tip", value=item_type, inline=True)
        
        # Adăugăm numele serverului
        server_name = item.get('ServerName', 'Necunoscut')
        embed.add_field(name="Server", value=server_name, inline=True)
        
        runtime = self.cog.format_runtime(item.get('RunTimeTicks'))
        if runtime != "N/A":
            embed.add_field(name="Durată", value=runtime, inline=True)

        if community_rating := item.get('CommunityRating'):
            embed.add_field(name="Rating", value=f"⭐ {community_rating:.1f}", inline=True)

        if overview := item.get('Overview'):
            if len(overview) > 300:
                overview = overview[:297] + "..."
            embed.add_field(name="Descriere", value=overview, inline=False)

        if item.get('TMDBOverview'):
            tmdb_overview = item.get('TMDBOverview')
            if len(tmdb_overview) > 300:
                tmdb_overview = tmdb_overview[:297] + "..."
            embed.add_field(name="Descriere TMDB", value=tmdb_overview, inline=False)

        if genres := item.get('Genres'):
            embed.add_field(name="Genuri", value=", ".join(genres[:4]), inline=False)
            
        if item.get('TMDBPosterPath'):
            thumbnail_url = f"https://image.tmdb.org/t/p/w342{item['TMDBPosterPath']}"
            embed.set_thumbnail(url=thumbnail_url)
        elif item.get('Id') and item.get('ServerURL') and item.get('ServerAPIKey'):
            thumbnail_url = f"{item['ServerURL']}/Items/{item['Id']}/Images/Primary?maxHeight=400&maxWidth=266&quality=90&api_key={item['ServerAPIKey']}"
            embed.set_thumbnail(url=thumbnail_url)
        
        item_id = item.get('Id')
        server_url = item.get('ServerURL')
        server_name = item.get('ServerName', 'Server')
        if item_id and server_url:
            web_url = f"{server_url}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Vizionare Online:", value=f"[{server_name}]({web_url})", inline=False)
        
        embed.set_footer(text=f"Pagina {self.current_page + 1}/{self.total_pages} • S-au găsit {self.total_results} rezultate în total")
        
        return embed
    
    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Buton pentru navigarea la pagina anterioară"""
        self.current_page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_current_page_embed(), view=self)
    
    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Buton pentru navigarea la pagina următoare"""
        self.current_page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.get_current_page_embed(), view=self)
        
    @discord.ui.button(emoji="🔍", style=discord.ButtonStyle.secondary)
    async def info_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Buton pentru afișarea mai multor detalii despre titlul curent"""
        item = self.items[self.current_page]
        item_id = item.get('Id')
        server_url = item.get('ServerURL')
        server_name = item.get('ServerName', 'Server')
        
        if not item_id or not server_url:
            await interaction.response.send_message("Nu sunt disponibile informații suplimentare pentru acest titlu.", ephemeral=True)
            return
            
        item_name = item.get('Name', 'Titlu necunoscut')
        web_url = f"{server_url}/web/index.html#!/details?id={item_id}"
        
        await interaction.response.send_message(
            f"**{item_name}**\nPoți accesa direct acest titlu din {server_name} folosind link-ul: {web_url}", 
            ephemeral=True
        )
    
    async def on_timeout(self):
        """Dezactivează butoanele după timeout"""
        for child in self.children:
            child.disabled = True
            
        try:
            message = self.message
            if message:
                await message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class JellyfinSearch(commands.Cog):
    """Jellyfin search commands for Red Discord Bot"""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=856712356)
        default_global = {
            "servers": {},  # Format: {"server_name": {"url": "...", "api_key": "..."}}
            "tmdb_api_key": None
        }
        self.config.register_global(**default_global)
        self.servers = {}
        self.tmdb_api_key = None
    
    async def cog_load(self):
        """Load cached settings when cog loads"""
        self.servers = await self.config.servers()
        self.tmdb_api_key = await self.config.tmdb_api_key()

    async def get_servers(self):
        """Get all configured servers"""
        return self.servers or await self.config.servers()
    
    async def get_tmdb_api_key(self):
        """Get the stored TMDB API key"""
        return self.tmdb_api_key or await self.config.tmdb_api_key()

    @commands.group(name="jellyfinset")
    @commands.is_owner()
    async def jellyfinset(self, ctx):
        """Configurare servere Jellyfin"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @jellyfinset.command(name="addserver")
    async def add_server(self, ctx, server_name: str, url: str, api_key: str):
        """
        Adaugă un server Jellyfin nou
        
        Exemplu: !jellyfinset addserver Freia https://jellyfin.example.com api_key_aici
        """
        url = url.rstrip('/')
        
        servers = await self.config.servers()
        servers[server_name] = {
            "url": url,
            "api_key": api_key
        }
        await self.config.servers.set(servers)
        self.servers = servers
        
        await ctx.send(f"✅ Serverul **{server_name}** a fost adăugat cu succes!")
        try:
            await ctx.message.delete()
        except:
            pass

    @jellyfinset.command(name="removeserver")
    async def remove_server(self, ctx, server_name: str):
        """
        Elimină un server Jellyfin
        
        Exemplu: !jellyfinset removeserver Freia
        """
        servers = await self.config.servers()
        
        if server_name not in servers:
            return await ctx.send(f"❌ Serverul **{server_name}** nu există în configurare.")
        
        del servers[server_name]
        await self.config.servers.set(servers)
        self.servers = servers
        
        await ctx.send(f"✅ Serverul **{server_name}** a fost eliminat.")

    @jellyfinset.command(name="listservers")
    async def list_servers(self, ctx):
        """Afișează toate serverele configurate"""
        servers = await self.config.servers()
        
        if not servers:
            return await ctx.send("❌ Nu există servere configurate. Folosește `!jellyfinset addserver` pentru a adăuga unul.")
        
        embed = discord.Embed(
            title="🎬 Servere Jellyfin Configurate",
            color=discord.Color.green()
        )
        
        for server_name, server_data in servers.items():
            embed.add_field(
                name=server_name,
                value=f"URL: {server_data['url']}",
                inline=False
            )
        
        await ctx.send(embed=embed)

    @jellyfinset.command(name="tmdb")
    async def set_tmdb(self, ctx, api_key: str):
        """
        Setează cheia API TMDB
        
        Exemplu: !jellyfinset tmdb api_key_aici
        """
        await self.config.tmdb_api_key.set(api_key)
        self.tmdb_api_key = api_key
        await ctx.send("✅ Cheia API TMDB a fost setată.")
        try:
            await ctx.message.delete()
        except:
            pass

    def format_runtime(self, runtime_ticks):
        """Convert runtime ticks to hours and minutes"""
        if not runtime_ticks:
            return "N/A"
        minutes = int(runtime_ticks / (10000000 * 60))
        hours = minutes // 60
        remaining_minutes = minutes % 60
        if hours > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{remaining_minutes}m"
    
    async def search_tmdb(self, query: str):
        """Search TMDB for movies and TV shows and collect all titles"""
        if not self.tmdb_api_key:
            return []
        
        all_titles = set()
        
        # Căutăm atât filme cât și seriale
        for media_type in ['movie', 'tv']:
            encoded_query = urllib.parse.quote(query)
            search_url = f"https://api.themoviedb.org/3/search/{media_type}?api_key={self.tmdb_api_key}&query={encoded_query}&language=ro-RO"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(search_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            for item in data.get('results', [])[:10]:  # Limităm la primele 10 rezultate per tip
                                tmdb_id = item.get('id')
                                
                                # Adăugăm titlul principal
                                main_title = item.get('title') if media_type == 'movie' else item.get('name')
                                if main_title:
                                    all_titles.add(main_title)
                                
                                # Adăugăm titlul original dacă diferă
                                original_title = item.get('original_title') if media_type == 'movie' else item.get('original_name')
                                if original_title and original_title != main_title:
                                    all_titles.add(original_title)
                                
                                # Obținem și titlurile alternative
                                alternative_titles = await self.get_alternative_titles(tmdb_id, media_type)
                                all_titles.update(alternative_titles)
                                
                except Exception as e:
                    pass
        
        return list(all_titles)
    
    async def get_alternative_titles(self, tmdb_id: int, media_type: str):
        """Get alternative titles from TMDB"""
        if not self.tmdb_api_key:
            return []
        
        titles = []
        endpoint = "alternative_titles" if media_type == "movie" else "alternative_titles"
        url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/{endpoint}?api_key={self.tmdb_api_key}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        results_key = "titles" if media_type == "movie" else "results"
                        
                        for item in data.get(results_key, []):
                            if media_type == "movie":
                                title = item.get('title')
                            else:
                                title = item.get('name')
                            if title:
                                titles.append(title)
            except Exception as e:
                pass
        
        return titles
    
    async def get_tmdb_info(self, item):
        """Get additional information from TMDB API"""
        if not self.tmdb_api_key:
            return item
        
        media_type = "movie" if item.get('Type') == "Movie" else "tv"
        
        tmdb_id = None
        if providers := item.get('ProviderIds', {}):
            tmdb_id = providers.get('Tmdb')
        
        if not tmdb_id:
            name = item.get('Name')
            year = item.get('ProductionYear', '')
            
            if not name:
                return item
                
            search_query = f"{name}"
            if year:
                search_query += f" {year}"
                
            encoded_query = urllib.parse.quote(search_query)
            # Căutăm mai întâi în engleză pentru rezultate mai bune
            search_url = f"https://api.themoviedb.org/3/search/{media_type}?api_key={self.tmdb_api_key}&query={encoded_query}&language=en-US"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(search_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            results = data.get('results', [])
                            
                            if results:
                                tmdb_id = results[0].get('id')
                                
                                if poster_path := results[0].get('poster_path'):
                                    item['TMDBPosterPath'] = poster_path
                                
                                if overview := results[0].get('overview'):
                                    item['TMDBOverview'] = overview
                except Exception as e:
                    pass
        
        if tmdb_id:
            # Încercăm să obținem descrierea în română
            overview_found = False
            for language in ['ro-RO', 'en-US']:
                details_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={self.tmdb_api_key}&language={language}"
                
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get(details_url, timeout=10) as response:
                            if response.status == 200:
                                data = await response.json()
                                
                                # Dacă găsim descriere, o salvăm și ieșim din bucla
                                if overview := data.get('overview'):
                                    if overview.strip():  # Verificăm că nu e goală
                                        item['TMDBOverview'] = overview
                                        overview_found = True
                                
                                # Salvăm posterul doar o dată (prima iterație)
                                if not item.get('TMDBPosterPath'):
                                    if poster_path := data.get('poster_path'):
                                        item['TMDBPosterPath'] = poster_path
                                
                                # Dacă am găsit descriere, nu mai încercăm alte limbi
                                if overview_found:
                                    break
                    except Exception as e:
                        pass
        
        return item

    async def search_on_server(self, server_name: str, server_data: dict, search_titles: List[str]) -> List[Dict]:
        """Search for content on a single Jellyfin server"""
        all_items = []
        seen_ids = set()
        
        base_url = server_data['url']
        api_key = server_data['api_key']
        
        for title in search_titles[:20]:  # Limităm la primele 20 titluri
            encoded_query = urllib.parse.quote(title)
            search_url = f"{base_url}/Items?searchTerm={encoded_query}&IncludeItemTypes=Movie,Series&Recursive=true&SearchType=String&IncludeMedia=true&IncludeOverview=true&Limit=50&api_key={api_key}"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(search_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            items = data.get('Items', [])
                            
                            # Adăugăm doar itemele noi (fără duplicate)
                            for item in items:
                                item_id = item.get('Id')
                                if item_id and item_id not in seen_ids:
                                    seen_ids.add(item_id)
                                    # Adăugăm informații despre server
                                    item['ServerName'] = server_name
                                    item['ServerURL'] = base_url
                                    item['ServerAPIKey'] = api_key
                                    all_items.append(item)
                except Exception as e:
                    pass
            
            # Adăugăm un mic delay între cereri
            await asyncio.sleep(0.2)
        
        return all_items

    @commands.command(name="cauta")
    async def cauta(self, ctx, *, query: str):
        """Caută conținut pe toate serverele Jellyfin configurate"""
        self.servers = await self.get_servers()
        self.tmdb_api_key = await self.get_tmdb_api_key()
        
        if not self.servers:
            return await ctx.send("❌ Nu există servere configurate. Administratorul trebuie să adauge servere folosind `!jellyfinset addserver`")
        
        async with ctx.typing():
            # Căutăm toate titlurile de pe TMDB (dacă există cheie API)
            tmdb_titles = []
            if self.tmdb_api_key:
                wait_msg = await ctx.send("🔍 Se caută pe TMDB și se colectează toate titlurile...")
                tmdb_titles = await self.search_tmdb(query)
                await wait_msg.delete()
            
            # Creăm lista de titluri de căutat pe Jellyfin
            # Începem cu query-ul original
            search_titles = [query]
            
            # Adăugăm titlurile de pe TMDB
            if tmdb_titles:
                search_titles.extend(tmdb_titles)
            
            # Eliminăm duplicatele păstrând ordinea
            seen = set()
            unique_titles = []
            for title in search_titles:
                if title.lower() not in seen:
                    seen.add(title.lower())
                    unique_titles.append(title)
            
            # Căutăm pe toate serverele Jellyfin
            all_items = []
            
            wait_msg = await ctx.send(f"🔍 Se caută pe {len(self.servers)} servere Jellyfin cu {len(unique_titles)} titluri diferite...")
            
            # Căutăm pe fiecare server
            for server_name, server_data in self.servers.items():
                server_items = await self.search_on_server(server_name, server_data, unique_titles)
                all_items.extend(server_items)
            
            await wait_msg.delete()
            
            if not all_items:
                return await ctx.send("❌ Nu s-au găsit rezultate pe niciun server Jellyfin.")
            
            # Procesăm primele 10 rezultate pentru a obține informații TMDB îmbogățite
            enhanced_items = []
            
            if self.tmdb_api_key and all_items:
                wait_msg = await ctx.send("📊 Se îmbogățesc rezultatele cu informații TMDB...")
                
                for item in all_items[:10]:
                    enhanced_item = await self.get_tmdb_info(item)
                    enhanced_items.append(enhanced_item)
                    await asyncio.sleep(0.5)
                
                await wait_msg.delete()
            else:
                enhanced_items = all_items[:10]
            
            # Adăugăm restul rezultatelor fără îmbogățire
            if len(all_items) > 10:
                enhanced_items.extend(all_items[10:])
            
            # Creăm view-ul pentru paginare
            view = JellyfinSearchView(self, ctx, enhanced_items, query, len(all_items))
            embed = view.get_current_page_embed()
            message = await ctx.send(embed=embed, view=view)
            view.message = message
