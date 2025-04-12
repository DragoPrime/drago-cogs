import asyncio
import aiohttp
import json
import random
import string
from typing import Optional

import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
from redbot.core.config import Group
from redbot.core.utils.chat_formatting import box


class FreiaUsers(commands.Cog):
    """Creează utilizatori pe un server Jellyfin din Discord"""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=82928377292, force_registration=True)
        
        # Setări implicite
        default_guild = {
            "jellyfin_url": "",
            "api_key": "",
            "default_policy": {
                "IsAdministrator": False,
                "IsHidden": False,
                "IsDisabled": False,
                "EnableRemoteControlOfOtherUsers": False,
                "EnableSharedDeviceControl": False,
                "EnableRemoteAccess": True,
                "EnableLiveTvManagement": False,
                "EnableLiveTvAccess": True,
                "EnableMediaPlayback": True,
                "EnableAudioPlaybackTranscoding": True,
                "EnableVideoPlaybackTranscoding": True,
                "EnablePlaybackRemuxing": True,
                "EnableContentDeletion": False,
                "EnableContentDownloading": True,
                "EnableSubtitleDownloading": True,
                "EnableSubtitleManagement": False,
                "EnableSyncTranscoding": True,
                "EnableMediaConversion": False,
                "EnablePublicSharing": False,
                "AccessSchedules": [],
                "BlockedTags": [],
                "EnabledDevices": [],
                "EnableAllDevices": True,
                "EnabledChannels": [],
                "EnableAllChannels": True,
                "EnabledFolders": [],
                "EnableAllFolders": True,
                "InvalidLoginAttemptCount": 0,
                "EnablePublicSharing": False,
                "RemoteClientBitrateLimit": 0,
                "SimultaneousStreamLimit": 3
            }
        }
        
        self.config.register_guild(**default_guild)
        
    def generate_password(self, length=8):
        """Generează o parolă aleatorie cu lungimea specificată"""
        characters = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        return ''.join(random.choice(characters) for _ in range(length))
        
    @commands.group(name="freia")
    @checks.admin_or_permissions(administrator=True)
    async def _freia(self, ctx: commands.Context):
        """Comenzi pentru configurarea și administrarea utilizatorilor Jellyfin"""
        pass
    
    @_freia.command(name="setup")
    async def _setup(self, ctx: commands.Context, jellyfin_url: str, api_key: str):
        """Configurează URL-ul serverului Jellyfin și cheia API
        
        Arguments:
            jellyfin_url -- URL-ul complet al serverului Jellyfin (ex: http://192.168.1.100:8096)
            api_key -- API key pentru autentificare
        """
        # Asigură-te că URL-ul nu se termină cu slash
        if jellyfin_url.endswith("/"):
            jellyfin_url = jellyfin_url[:-1]
        
        await self.config.guild(ctx.guild).jellyfin_url.set(jellyfin_url)
        await self.config.guild(ctx.guild).api_key.set(api_key)
        
        # Verifică conexiunea
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "X-Emby-Token": api_key,
                    "Content-Type": "application/json"
                }
                async with session.get(f"{jellyfin_url}/Users", headers=headers) as resp:
                    if resp.status == 200:
                        await ctx.send("✅ Configurare reușită! Conexiunea cu serverul Jellyfin a fost stabilită.")
                    else:
                        await ctx.send(f"❌ Configurare eșuată! Serverul a răspuns cu codul de stare: {resp.status}")
        except Exception as e:
            await ctx.send(f"❌ Eroare la conectarea la serverul Jellyfin: {str(e)}")
    
    @_freia.command(name="createuser")
    @commands.guild_only()
    async def _create_user(self, ctx: commands.Context, username: str):
        """Creează un utilizator nou pe serverul Jellyfin cu parolă generată automat
        
        Arguments:
            username -- Numele utilizatorului
        """
        # Verifică dacă sunt setate URL-ul și cheia API
        jellyfin_url = await self.config.guild(ctx.guild).jellyfin_url()
        api_key = await self.config.guild(ctx.guild).api_key()
        
        if not jellyfin_url or not api_key:
            return await ctx.send("⚠️ Configurarea serverului Jellyfin nu a fost făcută! Folosește comanda `freia setup` mai întâi.")
        
        # Generează o parolă aleatorie
        password = self.generate_password()
        
        # Obține politica implicită
        default_policy = await self.config.guild(ctx.guild).default_policy()
        
        # Crează utilizatorul
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "X-Emby-Token": api_key,
                    "Content-Type": "application/json"
                }
                
                # Verifică dacă utilizatorul există deja
                async with session.get(f"{jellyfin_url}/Users", headers=headers) as resp:
                    if resp.status == 200:
                        users = await resp.json()
                        if any(user.get("Name", "").lower() == username.lower() for user in users):
                            return await ctx.send(f"❌ Un utilizator cu numele `{username}` există deja!")
                
                # Creează utilizatorul
                user_data = {
                    "Name": username,
                    "Password": password
                }
                
                async with session.post(f"{jellyfin_url}/Users/New", headers=headers, json=user_data) as resp:
                    if resp.status == 200 or resp.status == 204:
                        user_info = await resp.json()
                        user_id = user_info.get("Id")
                        
                        # Setează politica utilizatorului
                        policy_url = f"{jellyfin_url}/Users/{user_id}/Policy"
                        
                        async with session.post(policy_url, headers=headers, json=default_policy) as policy_resp:
                            if policy_resp.status == 200 or policy_resp.status == 204:
                                # Extrage numele serverului Jellyfin (opțional)
                                server_name = "Freia"
                                try:
                                    async with session.get(f"{jellyfin_url}/System/Info", headers=headers) as server_info_resp:
                                        if server_info_resp.status == 200:
                                            server_info = await server_info_resp.json()
                                            if "ServerName" in server_info:
                                                server_name = server_info["ServerName"]
                                except:
                                    pass  # Folosește numele implicit dacă nu putem obține numele serverului
                                
                                # Creează un embed frumos pentru afișarea credențialelor
                                embed = discord.Embed(
                                    title=f"✅ Cont creat pe serverul {server_name}",
                                    description=f"Un nou cont a fost creat cu succes!",
                                    color=discord.Color.green()
                                )
                                embed.add_field(name="📋 Utilizator", value=f"`{username}`", inline=True)
                                embed.add_field(name="🔑 Parolă", value=f"`{password}`", inline=True)
                                embed.add_field(name="🌐 Server", value=f"`{server_name}`", inline=False)
                                embed.set_footer(text="Păstrează aceste credențiale într-un loc sigur!")
                                
                                await ctx.send(embed=embed)
                            else:
                                await ctx.send(f"⚠️ Utilizatorul a fost creat, dar setarea politicii a eșuat: {policy_resp.status}")
                    else:
                        error_text = await resp.text()
                        await ctx.send(f"❌ Crearea utilizatorului a eșuat! Status: {resp.status}\nEroare: {error_text}")
        except Exception as e:
            await ctx.send(f"❌ Eroare la crearea utilizatorului: {str(e)}")
    
    @_freia.command(name="listusers")
    @commands.guild_only()
    async def _list_users(self, ctx: commands.Context):
        """Listează toți utilizatorii de pe serverul Jellyfin"""
        # Verifică dacă sunt setate URL-ul și cheia API
        jellyfin_url = await self.config.guild(ctx.guild).jellyfin_url()
        api_key = await self.config.guild(ctx.guild).api_key()
        
        if not jellyfin_url or not api_key:
            return await ctx.send("⚠️ Configurarea serverului Jellyfin nu a fost făcută! Folosește comanda `freia setup` mai întâi.")
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "X-Emby-Token": api_key,
                    "Content-Type": "application/json"
                }
                
                async with session.get(f"{jellyfin_url}/Users", headers=headers) as resp:
                    if resp.status == 200:
                        users = await resp.json()
                        if not users:
                            return await ctx.send("Nu există utilizatori pe server.")
                        
                        user_list = "Utilizatori Jellyfin:\n"
                        for user in users:
                            admin_status = "👑 " if user.get("Policy", {}).get("IsAdministrator", False) else "👤 "
                            disabled_status = "❌ " if user.get("Policy", {}).get("IsDisabled", False) else ""
                            user_list += f"{admin_status}{disabled_status}{user.get('Name', 'Unknown')}\n"
                        
                        await ctx.send(box(user_list, lang=""))
                    else:
                        await ctx.send(f"❌ Nu am putut obține lista de utilizatori! Status: {resp.status}")
        except Exception as e:
            await ctx.send(f"❌ Eroare la listarea utilizatorilor: {str(e)}")
    
    @_freia.command(name="deleteuser")
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def _delete_user(self, ctx: commands.Context, username: str):
        """Șterge un utilizator de pe serverul Jellyfin
        
        Arguments:
            username -- Numele utilizatorului de șters
        """
        # Verifică dacă sunt setate URL-ul și cheia API
        jellyfin_url = await self.config.guild(ctx.guild).jellyfin_url()
        api_key = await self.config.guild(ctx.guild).api_key()
        
        if not jellyfin_url or not api_key:
            return await ctx.send("⚠️ Configurarea serverului Jellyfin nu a fost făcută! Folosește comanda `freia setup` mai întâi.")
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "X-Emby-Token": api_key,
                    "Content-Type": "application/json"
                }
                
                # Obține ID-ul utilizatorului
                user_id = None
                async with session.get(f"{jellyfin_url}/Users", headers=headers) as resp:
                    if resp.status == 200:
                        users = await resp.json()
                        for user in users:
                            if user.get("Name", "").lower() == username.lower():
                                user_id = user.get("Id")
                                break
                        
                        if not user_id:
                            return await ctx.send(f"❌ Nu am găsit utilizatorul `{username}`!")
                
                # Șterge utilizatorul
                async with session.delete(f"{jellyfin_url}/Users/{user_id}", headers=headers) as resp:
                    if resp.status == 200 or resp.status == 204:
                        await ctx.send(f"✅ Utilizatorul `{username}` a fost șters cu succes!")
                    else:
                        error_text = await resp.text()
                        await ctx.send(f"❌ Ștergerea utilizatorului a eșuat! Status: {resp.status}\nEroare: {error_text}")
        except Exception as e:
            await ctx.send(f"❌ Eroare la ștergerea utilizatorului: {str(e)}")
            
    @_freia.command(name="setpolicy")
    @checks.admin_or_permissions(administrator=True)
    @commands.guild_only()
    async def _set_default_policy(self, ctx: commands.Context, setting: str, value: str):
        """Modifică o setare din politica implicită pentru utilizatori noi
        
        Arguments:
            setting -- Numele setării (ex: EnableRemoteAccess)
            value -- Valoarea setării (true/false sau un număr)
        """
        guild_config = self.config.guild(ctx.guild)
        default_policy = await guild_config.default_policy()
        
        if setting not in default_policy:
            return await ctx.send(f"❌ Setarea `{setting}` nu există în politica implicită!")
        
        # Convertește valoarea la tipul corect
        if value.lower() in ["true", "false"]:
            parsed_value = value.lower() == "true"
        elif value.isdigit():
            parsed_value = int(value)
        else:
            return await ctx.send("❌ Valoarea trebuie să fie `true`, `false` sau un număr!")
        
        # Actualizează politica
        default_policy[setting] = parsed_value
        await guild_config.default_policy.set(default_policy)
        
        await ctx.send(f"✅ Politica implicită a fost actualizată! `{setting}` = `{parsed_value}`")
    
    @_freia.command(name="showpolicy")
    @commands.guild_only()
    async def _show_default_policy(self, ctx: commands.Context):
        """Afișează politica implicită pentru utilizatori noi"""
        default_policy = await self.config.guild(ctx.guild).default_policy()
        
        policy_text = "Politica implicită pentru utilizatori noi:\n"
        for key, value in default_policy.items():
            policy_text += f"{key}: {value}\n"
        
        await ctx.send(box(policy_text, lang="yaml"))

# Această funcție este cerută de Red pentru a încărca cogul
async def setup(bot):
    await bot.add_cog(FreiaUsers(bot))
