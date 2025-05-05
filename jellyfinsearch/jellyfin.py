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
        self.total_pages = len(items)  # Un rezultat per pagină
        
        # Actualizează starea butoanelor inițial
        self._update_buttons()
    
    def _update_buttons(self):
        """Actualizează starea butoanelor în funcție de pagina curentă"""
        # Dezactivează butonul înapoi dacă suntem pe prima pagină
        self.children[0].disabled = self.current_page == 0
        # Dezactivează butonul înainte dacă suntem pe ultima pagină
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
        # Obține doar un singur item bazat pe indexul paginii curente
        item = self.items[self.current_page]
        
        title = item.get('Name', 'Titlu necunoscut')
        if year := item.get('ProductionYear'):
            title += f" ({year})"
            
        # Creează un embed pentru rezultatul curent
        embed = discord.Embed(
            title=f"Rezultatul {self.current_page + 1} pentru '{self.query}'",
            description=title,
            color=discord.Color.blue()
        )
        
        # Adaugă detalii despre media
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

        # Descrierea este preluată din TMDB în funcție de ID-ul extern TMDB
        # Aceasta va fi adăugată async în background - momentan afișăm descrierea din Jellyfin
        if overview := item.get('Overview'):
            # Limitează descrierea la 300 de caractere dacă e prea lungă
            if len(overview) > 300:
                overview = overview[:297] + "..."
            embed.add_field(name="Descriere", value=overview, inline=False)

        if item.get('TMDBOverview'):
            # Dacă avem deja descriere TMDB din cache, o folosim pe aceasta
            tmdb_overview = item.get('TMDBOverview')
            if len(tmdb_overview) > 300:
                tmdb_overview = tmdb_overview[:297] + "..."
            embed.add_field(name="Descriere TMDB", value=tmdb_overview, inline=False)

        if genres := item.get('Genres'):
            embed.add_field(name="Genuri", value=", ".join(genres[:4]), inline=False)
            
        # Adaugă imagine thumbnail
        # Încercăm să utilizăm imaginea TMDB dacă este disponibilă
        if item.get('TMDBPosterPath'):
            thumbnail_url = f"https://image.tmdb.org/t/p/w342{item['TMDBPosterPath']}"
            embed.set_thumbnail(url=thumbnail_url)
        # Ca fallback, folosim imaginea din Jellyfin
        elif item.get('Id'):
            thumbnail_url = f"{self.cog.base_url}/Items/{item['Id']}/Images/Primary?maxHeight=400&maxWidth=266&quality=90&api_key={self.cog.api_key}"
            embed.set_thumbnail(url=thumbnail_url)
        
        # Adaugă link pentru vizualizare
        item_id = item.get('Id')
        if item_id:
            web_url = f"{self.cog.base_url}/web/index.html#!/details?id={item_id}"
            embed.add_field(name="Vizionare Online:", value=f"[Freia [SERVER 2]]({web_url})", inline=False)
        
        # Adaugă footer cu informații despre paginare
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
            
        # Crează un mesaj cu link-ul direct și alte informații utile
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
            
        # Încercăm să actualizăm mesajul, dar ignorăm erorile dacă mesajul nu mai există
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
        # Delete the message containing the API key for security
        await ctx.message.delete()
    
    @commands.command()
    @commands.is_owner()
    async def freiatmdb(self, ctx, api_key: str):
        """Set the TMDB API key"""
        await self.config.tmdb_api_key.set(api_key)
        self.tmdb_api_key = api_key
        await ctx.send("Cheia API TMDB a fost setată.")
        # Delete the message containing the API key for security
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
    
    async def get_tmdb_info(self, item):
        """Get additional information from TMDB API"""
        if not self.tmdb_api_key:
            return item
        
        # Determină tipul de media pentru URL-ul corect TMDB
        media_type = "movie" if item.get('Type') == "Movie" else "tv"
        
        # Verificăm dacă avem un ID TMDB salvat din providerul extern
        tmdb_id = None
        if providers := item.get('ProviderIds', {}):
            tmdb_id = providers.get('Tmdb')
        
        if not tmdb_id:
            # Dacă nu avem TMDB ID, putem încerca o căutare după nume
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
                    # TMDB API este cunoscut pentru viteza redusă - setăm un timeout mai mare
                    async with session.get(search_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            results = data.get('results', [])
                            
                            if results:
                                # Luăm primul rezultat care se potrivește cel mai bine
                                tmdb_id = results[0].get('id')
                                
                                # Adăugăm și posterul dacă este disponibil
                                if poster_path := results[0].get('poster_path'):
                                    item['TMDBPosterPath'] = poster_path
                                
                                # Adăugăm și descrierea în română dacă este disponibilă
                                if overview := results[0].get('overview'):
                                    item['TMDBOverview'] = overview
                        else:
                            # Error handling - nu putem obține date TMDB
                            pass
                except Exception as e:
                    # Error handling pentru cazul în care cererea eșuează
                    pass
        
        # Dacă avem un ID TMDB, putem obține informații detaliate
        if tmdb_id:
            details_url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={self.tmdb_api_key}&language=ro-RO"
            
            async with aiohttp.ClientSession() as session:
                try:
                    # TMDB API este cunoscut pentru viteza redusă - setăm un timeout mai mare
                    async with session.get(details_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Adăugăm descrierea în română
                            if overview := data.get('overview'):
                                item['TMDBOverview'] = overview
                            
                            # Adăugăm posterul
                            if poster_path := data.get('poster_path'):
                                item['TMDBPosterPath'] = poster_path
                except Exception as e:
                    # Error handling pentru cazul în care cererea eșuează
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

        encoded_query = urllib.parse.quote(query)
        # Utilizăm o limită de 50 de rezultate pentru paginare
        search_url = f"{self.base_url}/Items?searchTerm={encoded_query}&IncludeItemTypes=Movie,Series&Recursive=true&SearchType=String&IncludeMedia=true&IncludeOverview=true&Limit=50&api_key={self.api_key}"

        async with ctx.typing():
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(search_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            items = data.get('Items', [])
                            total_results = data.get('TotalRecordCount', 0)

                            if not items:
                                return await ctx.send("Nu s-au găsit rezultate. Atenție: căutarea se face după titlul de pe TMDB (cel în engleză, nu japoneză).")
                            
                            # Mesaj de așteptare pentru procesarea datelor TMDB
                            wait_msg = await ctx.send("Se caută în librăria Freia, vă rugăm să așteptați...")
                            
                            # Procesăm primele 10 rezultate pentru a obține informații TMDB
                            # Limitarea este necesară pentru a nu face prea multe cereri și a evita rate limiting
                            enhanced_items = []
                            for item in items[:10]:
                                # Utilizăm get_tmdb_info pentru a îmbogăți datele
                                enhanced_item = await self.get_tmdb_info(item)
                                enhanced_items.append(enhanced_item)
                                
                                # Adăugăm un mic delay între cereri pentru a evita rate limiting la TMDB
                                await asyncio.sleep(0.5)
                            
                            # Adăugăm și restul rezultatelor fără îmbogățire
                            if len(items) > 10:
                                enhanced_items.extend(items[10:])
                            
                            # Ștergem mesajul de așteptare
                            await wait_msg.delete()
                            
                            # Creăm view-ul pentru paginare
                            view = JellyfinSearchView(self, ctx, enhanced_items, query, total_results)
                            # Trimitem primul embed cu view-ul atașat
                            embed = view.get_current_page_embed()
                            message = await ctx.send(embed=embed, view=view)
                            # Stocăm mesajul pentru a putea face referință la el în timeout
                            view.message = message
                        else:
                            error_text = await response.text()
                            await ctx.send(f"Eroare: Nu s-a putut căuta pe serverul Jellyfin (Cod status: {response.status})\nDetalii eroare: {error_text}")
                except Exception as e:
                    await ctx.send(f"Eroare la conectarea cu serverul Jellyfin: {str(e)}")
