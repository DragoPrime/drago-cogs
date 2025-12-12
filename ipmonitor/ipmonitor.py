import discord
from redbot.core import commands, Config, checks
from redbot.core.bot import Red
import aiohttp
import asyncio
from datetime import datetime, time
from typing import Optional


class IPMonitor(commands.Cog):
    """Monitorizează IP-ul bot-ului și trimite notificări când se schimbă."""
    
    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        
        default_global = {
            "user_id": None,
            "channel_id": None,  # Opțional: canal pentru notificări
            "last_ip": None,
            "check_time": "12:00",
            "enabled": True,
            "use_channel": False  # Dacă True, trimite în canal în loc de DM
        }
        
        self.config.register_global(**default_global)
        self.check_task = None
        self.bot.loop.create_task(self.initialize())
    
    async def initialize(self):
        """Inițializează task-ul de verificare."""
        await self.bot.wait_until_ready()
        if self.check_task is None or self.check_task.done():
            self.check_task = self.bot.loop.create_task(self.ip_check_loop())
    
    def cog_unload(self):
        """Oprește task-ul când cog-ul este descărcat."""
        if self.check_task:
            self.check_task.cancel()
    
    async def get_public_ip(self) -> Optional[str]:
        """Obține IP-ul public al bot-ului."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.ipify.org?format=json', timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('ip')
        except Exception as e:
            print(f"Eroare la obținerea IP-ului: {e}")
        return None
    
    async def ip_check_loop(self):
        """Loop principal care verifică IP-ul zilnic."""
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                enabled = await self.config.enabled()
                if not enabled:
                    await asyncio.sleep(3600)
                    continue
                
                check_time_str = await self.config.check_time()
                hours, minutes = map(int, check_time_str.split(':'))
                
                now = datetime.now()
                check_time_today = now.replace(hour=hours, minute=minutes, second=0, microsecond=0)
                
                if now > check_time_today:
                    check_time_today = check_time_today.replace(day=check_time_today.day + 1)
                
                wait_seconds = (check_time_today - now).total_seconds()
                await asyncio.sleep(wait_seconds)
                
                await self.check_and_notify()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Eroare în loop-ul de verificare IP: {e}")
                await asyncio.sleep(3600)
    
    async def check_and_notify(self):
        """Verifică IP-ul și trimite notificare dacă s-a schimbat."""
        current_ip = await self.get_public_ip()
        
        if current_ip is None:
            return
        
        last_ip = await self.config.last_ip()
        user_id = await self.config.user_id()
        channel_id = await self.config.channel_id()
        use_channel = await self.config.use_channel()
        
        if last_ip is None:
            await self.config.last_ip.set(current_ip)
            return
        
        if current_ip != last_ip:
            embed = discord.Embed(
                title="🔄 IP-ul Bot-ului S-a Schimbat",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="IP Vechi", value=f"`{last_ip}`", inline=False)
            embed.add_field(name="IP Nou", value=f"`{current_ip}`", inline=False)
            embed.set_footer(text="IP Monitor")
            
            sent = False
            
            # Încearcă să trimită în canal dacă este configurat
            if use_channel and channel_id:
                try:
                    channel = self.bot.get_channel(channel_id)
                    if channel is None:
                        channel = await self.bot.fetch_channel(channel_id)
                    
                    if channel and isinstance(channel, discord.TextChannel):
                        user_mention = f"<@{user_id}>" if user_id else ""
                        await channel.send(content=user_mention, embed=embed)
                        sent = True
                except Exception as e:
                    print(f"Eroare la trimiterea în canal: {e}")
            
            # Dacă nu s-a trimis în canal, încearcă DM
            if not sent and user_id:
                try:
                    user = self.bot.get_user(user_id)
                    if user is None:
                        user = await self.bot.fetch_user(user_id)
                    
                    if user:
                        await user.send(embed=embed)
                        sent = True
                except discord.Forbidden:
                    print(f"Nu pot trimite DM utilizatorului {user_id}. DM-urile sunt dezactivate.")
                except discord.HTTPException as e:
                    print(f"Eroare HTTP la trimiterea DM: {e}")
                except Exception as e:
                    print(f"Eroare la trimiterea mesajului: {e}")
            
            if sent:
                await self.config.last_ip.set(current_ip)
    
    @commands.group(name="ipmonitor")
    @checks.is_owner()
    async def ipmonitor(self, ctx):
        """Comenzi pentru monitorizarea IP-ului bot-ului."""
        pass
    
    @ipmonitor.command(name="setuser")
    async def set_user(self, ctx, user: discord.User):
        """Setează utilizatorul care va primi notificările.
        
        Exemplu: [p]ipmonitor setuser @User
        Sau: [p]ipmonitor setuser 123456789012345678
        """
        await self.config.user_id.set(user.id)
        await ctx.send(f"✅ Notificările vor fi trimise către {user.mention} (ID: {user.id})")
    
    @ipmonitor.command(name="setchannel")
    async def set_channel(self, ctx, channel: discord.TextChannel = None):
        """Setează un canal pentru notificări în loc de DM.
        
        Exemplu: [p]ipmonitor setchannel #logs
        Pentru a dezactiva: [p]ipmonitor setchannel
        """
        if channel:
            await self.config.channel_id.set(channel.id)
            await self.config.use_channel.set(True)
            await ctx.send(f"✅ Notificările vor fi trimise în {channel.mention}")
        else:
            await self.config.use_channel.set(False)
            await ctx.send("✅ Notificările vor fi trimise prin DM")
    
    @ipmonitor.command(name="settime")
    async def set_time(self, ctx, check_time: str):
        """Setează ora la care se face verificarea zilnică (format HH:MM).
        
        Exemplu: [p]ipmonitor settime 14:30
        """
        try:
            hours, minutes = map(int, check_time.split(':'))
            if not (0 <= hours <= 23 and 0 <= minutes <= 59):
                raise ValueError
            
            await self.config.check_time.set(check_time)
            await ctx.send(f"✅ Ora de verificare setată la {check_time}")
            
            if self.check_task:
                self.check_task.cancel()
            self.check_task = self.bot.loop.create_task(self.ip_check_loop())
            
        except ValueError:
            await ctx.send("❌ Format invalid! Folosește formatul HH:MM (ex: 14:30)")
    
    @ipmonitor.command(name="check")
    async def manual_check(self, ctx):
        """Verifică manual IP-ul curent al bot-ului."""
        async with ctx.typing():
            current_ip = await self.get_public_ip()
            last_ip = await self.config.last_ip()
            
            if current_ip is None:
                await ctx.send("❌ Nu am putut obține IP-ul public.")
                return
            
            embed = discord.Embed(
                title="🌐 Verificare IP",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="IP Curent", value=f"`{current_ip}`", inline=False)
            
            if last_ip:
                embed.add_field(name="Ultimul IP Salvat", value=f"`{last_ip}`", inline=False)
                if current_ip != last_ip:
                    embed.add_field(name="Status", value="⚠️ IP-ul s-a schimbat!", inline=False)
                else:
                    embed.add_field(name="Status", value="✅ IP-ul este același", inline=False)
            
            await ctx.send(embed=embed)
    
    @ipmonitor.command(name="status")
    async def status(self, ctx):
        """Afișează statusul și configurația IP Monitor."""
        user_id = await self.config.user_id()
        channel_id = await self.config.channel_id()
        use_channel = await self.config.use_channel()
        last_ip = await self.config.last_ip()
        check_time = await self.config.check_time()
        enabled = await self.config.enabled()
        
        user_mention = "Nesetat"
        if user_id:
            user = self.bot.get_user(user_id)
            if user:
                user_mention = f"{user.mention} (ID: {user_id})"
            else:
                user_mention = f"ID: {user_id}"
        
        destination = "DM"
        if use_channel and channel_id:
            channel = self.bot.get_channel(channel_id)
            if channel:
                destination = f"Canal: {channel.mention}"
            else:
                destination = f"Canal ID: {channel_id}"
        
        embed = discord.Embed(
            title="📊 Status IP Monitor",
            color=discord.Color.green() if enabled else discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Status", value="🟢 Activ" if enabled else "🔴 Inactiv", inline=False)
        embed.add_field(name="Utilizator Notificat", value=user_mention, inline=False)
        embed.add_field(name="Destinație Notificări", value=destination, inline=False)
        embed.add_field(name="Ultimul IP", value=f"`{last_ip}`" if last_ip else "Necunoscut", inline=False)
        embed.add_field(name="Ora Verificării", value=check_time, inline=False)
        
        await ctx.send(embed=embed)
    
    @ipmonitor.command(name="toggle")
    async def toggle(self, ctx):
        """Activează/dezactivează monitorizarea IP-ului."""
        enabled = await self.config.enabled()
        new_state = not enabled
        await self.config.enabled.set(new_state)
        
        if new_state:
            await ctx.send("✅ Monitorizarea IP-ului a fost activată.")
        else:
            await ctx.send("⏸️ Monitorizarea IP-ului a fost dezactivată.")
    
    @ipmonitor.command(name="forcesave")
    async def force_save(self, ctx):
        """Salvează forțat IP-ul curent ca referință."""
        current_ip = await self.get_public_ip()
        if current_ip:
            await self.config.last_ip.set(current_ip)
            await ctx.send(f"✅ IP-ul curent (`{current_ip}`) a fost salvat ca referință.")
        else:
            await ctx.send("❌ Nu am putut obține IP-ul public.")
    
    @ipmonitor.command(name="testsend")
    async def test_send(self, ctx):
        """Testează trimiterea unei notificări de test."""
        user_id = await self.config.user_id()
        channel_id = await self.config.channel_id()
        use_channel = await self.config.use_channel()
        
        embed = discord.Embed(
            title="🧪 Mesaj de Test",
            description="Acesta este un test pentru notificările IP Monitor.",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        embed.set_footer(text="IP Monitor - Test")
        
        sent = False
        
        if use_channel and channel_id:
            try:
                channel = self.bot.get_channel(channel_id)
                if channel and isinstance(channel, discord.TextChannel):
                    user_mention = f"<@{user_id}>" if user_id else ""
                    await channel.send(content=user_mention, embed=embed)
                    sent = True
                    await ctx.send(f"✅ Mesaj de test trimis în {channel.mention}")
            except Exception as e:
                await ctx.send(f"❌ Eroare la trimiterea în canal: {e}")
        
        if not sent and user_id:
            try:
                user = self.bot.get_user(user_id)
                if user is None:
                    user = await self.bot.fetch_user(user_id)
                
                if user:
                    await user.send(embed=embed)
                    await ctx.send(f"✅ Mesaj de test trimis prin DM către {user.mention}")
                else:
                    await ctx.send("❌ Nu am putut găsi utilizatorul.")
            except discord.Forbidden:
                await ctx.send("❌ Nu pot trimite DM utilizatorului. DM-urile sunt dezactivate sau bot-ul nu are acces.")
            except Exception as e:
                await ctx.send(f"❌ Eroare la trimiterea DM: {e}")


def setup(bot: Red):
    """Funcție necesară pentru a încărca cog-ul."""
    cog = IPMonitor(bot)
    bot.add_cog(cog)
