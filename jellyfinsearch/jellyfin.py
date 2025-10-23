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
        elif item.get('Id'):
            thumbnail_url = f"{self.cog.base_url}/Items/{item['Id']}/Images/Primary?maxHeight=400&maxWidth=266&quality=90&api_key={self.cog.api_key}"
            embed.set_thumbnail(url=thumbnail_url)
        
        item_id = item.get('Id')
        if item_id:
            web_url = f"{self.cog.base_url}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Vizionare Online:", value=f"[Freia [SERVER 2]]({web_url})", inline=False)
        
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
        
        if not item_id:
            await interaction.response.send_message("Nu sunt disponibile informații suplimentare pentru acest titlu.", ephemeral=True)
            return
            
        item_name = item.get('Name', 'Titlu necunoscut')
        web_url = f"{self.cog.base_url}/web/index.html#!/details?id={item_id}"
        
        await interaction.response.send_message(
            f"**{item_name}**\nPoți accesa direct acest titlu din Freia folosind link-ul: {web_url}", 
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
            "base_url": None,
            "api_key": None,
            "tmdb_api_key": None
        }
        self.config.register_global(**default_global)
        self.base_url = None
        self.api_key = None
        self.tmdb_api_key = None
    
    async def cog_load(self):
        """Load cached settings when cog loads"""
        self.base_url = await self.config.base_url()
        self.api_key = await self.config.api_key()
        self.tmdb_api_key = await self.config.tmdb_api_key()

    async def get_base_url(self):
        """Get the stored base URL"""
        return self.base_url or await self.config.base_url()

    async def get_api_key(self):
        """Get the stored API key"""
        return self.api_key or await self.config.api_key()
    
    async def get_tmdb_api_key(self):
        """Get the stored TMDB API key"""
        return self.tmdb_api_key or await self.config.tmdb_api_key()

    @commands.command()
    @commands.is_owner()
    async def setjellyfinurl(self, ctx, url: str):
        """Set the Jellyfin server URL"""
        url = url.rstrip('/')
        await self.config.base_url.set(url)
        self.base_url = url
        await ctx.send(f"URL-ul serverului Jellyfin a fost setat la: {url}")

    @commands.command()
    @commands.is_owner()
    async def setjellyfinapi(self, ctx, api_key: str):
        """Set the Jellyfin API key"""
        await self.config.api_key.set(api_key)
        self.api_key = api_key
        await ctx.send("Cheia API Jellyfin a fost setată.")
        await ctx.message.delete()
    
    @commands.command()
    @commands.is_owner()
    async def freiatmdb(self, ctx, api_key: str):
        """Set the TMDB API key"""
        await self.config.tmdb_api_key.set(api_key)
        self.tmdb_api_key = api_key
        await ctx.send("Cheia API TMDB a fost setată.")
        await ctx.message.delete()

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
            search_url = f"https://api.themoviedb.org/3/search/{media_type}?api_key={self.tmdb_api_key}&query={encoded_query}&language=ro-RO"
            
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
            details_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={self.tmdb_api_key}&language=ro-RO"
            
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(details_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if overview := data.get('overview'):
                                item['TMDBOverview'] = overview
                            
                            if poster_path := data.get('poster_path'):
                                item['TMDBPosterPath'] = poster_path
                except Exception as e:
                    pass
        
        return item

    @commands.command(name="freia")
    async def freia(self, ctx, *, query: str):
        """Search for content on your Jellyfin server"""
        self.base_url = await self.get_base_url()
        self.api_key = await self.get_api_key()
        self.tmdb_api_key = await self.get_tmdb_api_key()
        
        if not self.base_url or not self.api_key:
            return await ctx.send("Te rog să setezi mai întâi URL-ul și cheia API folosind `setjellyfinurl` și `setjellyfinapi`")
        
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
            
            # Căutăm pe Jellyfin cu toate titlurile
            all_items = []
            seen_ids = set()
            
            wait_msg = await ctx.send(f"🔍 Se caută pe serverul Jellyfin cu {len(unique_titles)} titluri diferite...")
            
            for title in unique_titles[:20]:  # Limităm la primele 20 titluri pentru a nu supraîncărca
                encoded_query = urllib.parse.quote(title)
                search_url = f"{self.base_url}/Items?searchTerm={encoded_query}&IncludeItemTypes=Movie,Series&Recursive=true&SearchType=String&IncludeMedia=true&IncludeOverview=true&Limit=50&api_key={self.api_key}"
                
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get(search_url) as response:
                            if response.status == 200:
                                data = await response.json()
                                items = data.get('Items', [])
                                
                                # Adăugăm doar itemele noi (fără duplicate)
                                for item in items:
                                    item_id = item.get('Id')
                                    if item_id and item_id not in seen_ids:
                                        seen_ids.add(item_id)
                                        all_items.append(item)
                    except Exception as e:
                        pass
                
                # Adăugăm un mic delay între cereri
                await asyncio.sleep(0.2)
            
            await wait_msg.delete()
            
            if not all_items:
                return await ctx.send("Nu s-au găsit rezultate pe serverul Jellyfin.")
            
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
