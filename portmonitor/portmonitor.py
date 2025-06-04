import asyncio
import socket
from datetime import datetime
from typing import Optional

import discord
from redbot.core import commands, Config, tasks
from redbot.core.bot import Red


class PortMonitor(commands.Cog):
    """
    Plugin pentru monitorizarea porturilor și trimiterea de notificări
    când un port devine inaccesibil.
    """

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        # Configurația implicită
        default_guild = {
            "monitors": {},  # {"monitor_id": {"ip": "...", "port": ..., "channel_id": ..., "last_status": True}}
            "notification_channel": None
        }
        
        self.config.register_guild(**default_guild)
        self.monitor_task.start()

    def cog_unload(self):
        """Oprește task-ul când cog-ul este descărcat"""
        self.monitor_task.cancel()

    async def check_port(self, ip: str, port: int, timeout: int = 5) -> bool:
        """
        Verifică dacă un port este accesibil pe un IP dat.
        
        Args:
            ip: Adresa IP de verificat
            port: Portul de verificat
            timeout: Timeout în secunde pentru conexiune
            
        Returns:
            True dacă portul este accesibil, False altfel
        """
        try:
            # Creează o conexiune socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            # Încearcă să se conecteze
            result = sock.connect_ex((ip, port))
            sock.close()
            
            # Dacă result este 0, conexiunea a reușit
            return result == 0
            
        except Exception:
            return False

    @tasks.loop(hours=1)
    async def monitor_task(self):
        """Task care rulează din oră în oră pentru a verifica porturile"""
        try:
            for guild in self.bot.guilds:
                guild_config = await self.config.guild(guild).all()
                monitors = guild_config.get("monitors", {})
                
                for monitor_id, monitor_data in monitors.items():
                    ip = monitor_data["ip"]
                    port = monitor_data["port"]
                    channel_id = monitor_data["channel_id"]
                    last_status = monitor_data.get("last_status", True)
                    
                    # Verifică statusul portului
                    current_status = await asyncio.to_thread(self.check_port, ip, port)
                    
                    # Dacă statusul s-a schimbat de la accesibil la inaccesibil
                    if last_status and not current_status:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="🚨 Port Inaccesibil",
                                description=f"Portul **{port}** de pe **{ip}** nu mai este accesibil!",
                                color=discord.Color.red(),
                                timestamp=datetime.utcnow()
                            )
                            embed.add_field(name="IP", value=ip, inline=True)
                            embed.add_field(name="Port", value=str(port), inline=True)
                            embed.add_field(name="Status", value="❌ Offline", inline=True)
                            
                            try:
                                await channel.send(embed=embed)
                            except discord.HTTPException:
                                pass  # Ignoră erorile de trimitere
                    
                    # Dacă portul a revenit online
                    elif not last_status and current_status:
                        channel = self.bot.get_channel(channel_id)
                        if channel:
                            embed = discord.Embed(
                                title="✅ Port Accesibil",
                                description=f"Portul **{port}** de pe **{ip}** este din nou accesibil!",
                                color=discord.Color.green(),
                                timestamp=datetime.utcnow()
                            )
                            embed.add_field(name="IP", value=ip, inline=True)
                            embed.add_field(name="Port", value=str(port), inline=True)
                            embed.add_field(name="Status", value="✅ Online", inline=True)
                            
                            try:
                                await channel.send(embed=embed)
                            except discord.HTTPException:
                                pass
                    
                    # Actualizează statusul în configurație
                    if current_status != last_status:
                        async with self.config.guild(guild).monitors() as monitors_config:
                            monitors_config[monitor_id]["last_status"] = current_status
                            
        except Exception as e:
            print(f"Eroare în monitor_task: {e}")

    @monitor_task.before_loop
    async def before_monitor_task(self):
        """Așteaptă ca bot-ul să fie gata înainte de a începe monitorizarea"""
        await self.bot.wait_until_ready()

    @commands.group(name="portmonitor", aliases=["pm"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def portmonitor(self, ctx):
        """Comenzi pentru monitorizarea porturilor"""
        pass

    @portmonitor.command(name="add")
    async def add_monitor(self, ctx, ip: str, port: int, channel: Optional[discord.TextChannel] = None):
        """
        Adaugă un nou monitor pentru un IP și port.
        
        Exemple:
        `[p]portmonitor add 192.168.1.1 80`
        `[p]portmonitor add google.com 443 #alerts`
        """
        if not (1 <= port <= 65535):
            await ctx.send("❌ Portul trebuie să fie între 1 și 65535!")
            return
        
        if channel is None:
            channel = ctx.channel
        
        # Verifică dacă IP-ul este valid făcând un test
        is_accessible = await asyncio.to_thread(self.check_port, ip, port)
        
        # Generează un ID unic pentru monitor
        monitor_id = f"{ip}:{port}"
        
        async with self.config.guild(ctx.guild).monitors() as monitors:
            monitors[monitor_id] = {
                "ip": ip,
                "port": port,
                "channel_id": channel.id,
                "last_status": is_accessible,
                "added_by": ctx.author.id,
                "added_at": datetime.utcnow().isoformat()
            }
        
        status_emoji = "✅" if is_accessible else "❌"
        status_text = "Online" if is_accessible else "Offline"
        
        embed = discord.Embed(
            title="📊 Monitor Adăugat",
            description=f"Monitorizarea pentru **{ip}:{port}** a fost configurată!",
            color=discord.Color.blue()
        )
        embed.add_field(name="IP", value=ip, inline=True)
        embed.add_field(name="Port", value=str(port), inline=True)
        embed.add_field(name="Canal", value=channel.mention, inline=True)
        embed.add_field(name="Status Curent", value=f"{status_emoji} {status_text}", inline=True)
        embed.add_field(name="Verificare", value="Din oră în oră", inline=True)
        
        await ctx.send(embed=embed)

    @portmonitor.command(name="remove", aliases=["delete", "rm"])
    async def remove_monitor(self, ctx, ip: str, port: int):
        """
        Elimină un monitor existent.
        
        Exemplu:
        `[p]portmonitor remove 192.168.1.1 80`
        """
        monitor_id = f"{ip}:{port}"
        
        async with self.config.guild(ctx.guild).monitors() as monitors:
            if monitor_id in monitors:
                del monitors[monitor_id]
                await ctx.send(f"✅ Monitorizarea pentru **{ip}:{port}** a fost eliminată!")
            else:
                await ctx.send(f"❌ Nu există nicio monitorizare pentru **{ip}:{port}**!")

    @portmonitor.command(name="list", aliases=["show"])
    async def list_monitors(self, ctx):
        """Afișează toate monitoarele configurate pentru acest server"""
        monitors = await self.config.guild(ctx.guild).monitors()
        
        if not monitors:
            await ctx.send("📭 Nu există monitoare configurate pentru acest server!")
            return
        
        embed = discord.Embed(
            title="📊 Monitoare Active",
            description=f"Lista tuturor monitoarelor configurate în **{ctx.guild.name}**",
            color=discord.Color.blue()
        )
        
        for monitor_id, monitor_data in monitors.items():
            ip = monitor_data["ip"]
            port = monitor_data["port"]
            channel_id = monitor_data["channel_id"]
            last_status = monitor_data.get("last_status", True)
            
            channel = self.bot.get_channel(channel_id)
            channel_mention = channel.mention if channel else "Canal șters"
            
            status_emoji = "✅" if last_status else "❌"
            status_text = "Online" if last_status else "Offline"
            
            embed.add_field(
                name=f"{ip}:{port}",
                value=f"Canal: {channel_mention}\nStatus: {status_emoji} {status_text}",
                inline=True
            )
        
        await ctx.send(embed=embed)

    @portmonitor.command(name="test")
    async def test_port(self, ctx, ip: str, port: int):
        """
        Testează manual accesibilitatea unui port.
        
        Exemplu:
        `[p]portmonitor test google.com 80`
        """
        if not (1 <= port <= 65535):
            await ctx.send("❌ Portul trebuie să fie între 1 și 65535!")
            return
        
        await ctx.send(f"🔍 Testez conexiunea la **{ip}:{port}**...")
        
        is_accessible = await asyncio.to_thread(self.check_port, ip, port)
        
        if is_accessible:
            embed = discord.Embed(
                title="✅ Port Accesibil",
                description=f"Portul **{port}** de pe **{ip}** este accesibil!",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Port Inaccesibil",
                description=f"Portul **{port}** de pe **{ip}** nu este accesibil!",
                color=discord.Color.red()
            )
        
        embed.add_field(name="IP", value=ip, inline=True)
        embed.add_field(name="Port", value=str(port), inline=True)
        embed.timestamp = datetime.utcnow()
        
        await ctx.send(embed=embed)

    @portmonitor.command(name="status")
    async def check_status(self, ctx):
        """Verifică statusul task-ului de monitorizare"""
        if self.monitor_task.is_running():
            next_run = self.monitor_task.next_iteration
            if next_run:
                time_until_next = next_run - datetime.now(next_run.tzinfo)
                minutes_left = int(time_until_next.total_seconds() / 60)
                
                embed = discord.Embed(
                    title="📊 Status Monitorizare",
                    description="Task-ul de monitorizare este activ!",
                    color=discord.Color.green()
                )
                embed.add_field(name="Următoarea verificare", value=f"În {minutes_left} minute", inline=True)
                embed.add_field(name="Interval", value="Din oră în oră", inline=True)
            else:
                embed = discord.Embed(
                    title="📊 Status Monitorizare",
                    description="Task-ul de monitorizare este activ!",
                    color=discord.Color.green()
                )
        else:
            embed = discord.Embed(
                title="⚠️ Status Monitorizare",
                description="Task-ul de monitorizare nu este activ!",
                color=discord.Color.orange()
            )
        
        await ctx.send(embed=embed)
