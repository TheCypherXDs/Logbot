import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from collections import deque, Counter
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Literal

class SecurityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Anti-raid tracking
        self.join_cache = deque(maxlen=50) # Track timestamps of joins
        self.msg_cache = {} # guild_id -> {user_id: deque(maxlen=5)}
        self.mention_cache = {} # guild_id -> {user_id: count}
        
        # Invite regex
        self.invite_regex = re.compile(r"(discord\.gg|discord\.com/invite|discordapp\.com/invite)/[a-z0-9-]+", re.I)
        self.url_regex = re.compile(r"https?://[^\s]+", re.I)

    async def log_security_action(self, guild, title, description, color=discord.Color.red()):
        logger = self.bot.get_cog("LoggerCog")
        if logger:
            await logger.send_log(guild, "moderation", title, description, color)

    async def is_whitelisted(self, member):
        if member.guild_permissions.administrator: return True
        whitelist_roles = await self.bot.db.get_setting(member.guild.id, "automod_whitelist")
        if whitelist_roles:
            role_ids = [int(r.strip()) for r in whitelist_roles.split(",") if r.strip().isdigit()]
            for role in member.roles:
                if role.id in role_ids: return True
        return False

    @commands.Cog.listener()
    async def on_member_join(self, member):
        now = time.time()
        self.join_cache.append(now)
        
        # Check for mass join (e.g., more than 10 joins in 30 seconds)
        recent_joins = [t for t in self.join_cache if now - t < 30]
        if len(recent_joins) > 10:
            await self.log_security_action(member.guild, "🚨 Anti-Raid: Mass Join", f"Обнаружен массовый заход: {len(recent_joins)} пользователей за 30 сек.")
            
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild: return
        if await self.is_whitelisted(message.author): return

        # 1. Anti-Spam (Same messages)
        guild_id = message.guild.id
        user_id = message.author.id
        if guild_id not in self.msg_cache: self.msg_cache[guild_id] = {}
        if user_id not in self.msg_cache[guild_id]: self.msg_cache[guild_id][user_id] = deque(maxlen=5)
        
        self.msg_cache[guild_id][user_id].append(message.content)
        if len(self.msg_cache[guild_id][user_id]) == 5 and len(set(self.msg_cache[guild_id][user_id])) == 1:
            try:
                await message.delete()
                await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=5), reason="Spam")
                await self.log_security_action(message.guild, "🛡️ Automod: Spam", f"Пользователь {message.author.mention} временно отстранен за спам.")
            except: pass
            return

        # 2. Mass Mentions
        if len(message.mentions) > 5:
            try:
                await message.delete()
                await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=10), reason="Mass Mentions")
                await self.log_security_action(message.guild, "🛡️ Automod: Mass Mentions", f"Пользователь {message.author.mention} отстранен за массовые упоминания.")
            except: pass
            return

        # 3. Invite Links
        if self.invite_regex.search(message.content):
            if await self.bot.db.get_setting(guild_id, "filter_invites", "0") == "1":
                await message.delete()
                await self.log_security_action(message.guild, "🛡️ Automod: Invite Link", f"Удалена ссылка-приглашение от {message.author.mention}")
                return

        # 4. Caps Filter
        if len(message.content) > 10 and message.content.isupper():
            if await self.bot.db.get_setting(guild_id, "filter_caps", "0") == "1":
                await message.delete()
                return

        # 5. Bad Words
        bad_words_str = await self.bot.db.get_setting(guild_id, "bad_words", "")
        if bad_words_str:
            bad_words = [w.strip().lower() for w in bad_words_str.split(",") if w.strip()]
            content_lower = message.content.lower()
            if any(word in content_lower for word in bad_words):
                await message.delete()
                await self.log_security_action(message.guild, "🛡️ Automod: Bad Word", f"Удалено сообщение с запрещенным словом от {message.author.mention}")

    @app_commands.command(name='lockdown', description='Закрыть/открыть канал для сообщений')
    @app_commands.default_permissions(manage_channels=True)
    async def lockdown(self, interaction: discord.Interaction, action: Literal['on', 'off']):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        if action == 'on':
            overwrite.send_messages = False
            msg = "🔒 Канал переведен в режим **Lockdown**."
        else:
            overwrite.send_messages = None
            msg = "🔓 Режим **Lockdown** снят."
        
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message(msg)
        await self.log_security_action(interaction.guild, "🛡️ Lockdown", f"Модератор {interaction.user.mention} {action == 'on' and 'включил' or 'выключил'} режим изоляции для {interaction.channel.mention}")

    @app_commands.command(name='automod_setup', description='Настройка автомодерации')
    @app_commands.default_permissions(administrator=True)
    async def automod_setup(self, interaction: discord.Interaction, 
                             filter_invites: Optional[bool] = None,
                             filter_caps: Optional[bool] = None,
                             bad_words: Optional[str] = None,
                             whitelist_roles: Optional[str] = None):
        if filter_invites is not None:
            await self.bot.db.set_setting(interaction.guild_id, "filter_invites", filter_invites and "1" or "0")
        if filter_caps is not None:
            await self.bot.db.set_setting(interaction.guild_id, "filter_caps", filter_caps and "1" or "0")
        if bad_words is not None:
            await self.bot.db.set_setting(interaction.guild_id, "bad_words", bad_words)
        if whitelist_roles is not None:
            await self.bot.db.set_setting(interaction.guild_id, "automod_whitelist", whitelist_roles)
            
        await interaction.response.send_message("✅ Настройки автомодерации обновлены.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SecurityCog(bot))
