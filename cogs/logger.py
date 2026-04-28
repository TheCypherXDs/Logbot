import discord
from discord.ext import commands
import os
import aiohttp
import asyncio
import discord.utils
from datetime import datetime, timedelta

class LoggerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_logs = {} # Кэш для предотвращения дубликатов: {guild_id: (content_hash, timestamp)}

    async def send_log(self, guild, log_type, title, description, color=discord.Color.blurple(), user=None):
        """
        Отправляет красивый Embed с метаданными и защитой от дублей.
        """
        # Анти-дубликат: проверяем, не отправляли ли мы то же самое секунду назад
        log_hash = hash(f"{log_type}{title}{description}{user.id if user else ''}")
        now = datetime.now()
        
        if guild.id in self.last_logs:
            old_hash, old_time = self.last_logs[guild.id]
            if old_hash == log_hash and (now - old_time).total_seconds() < 2:
                return # Игнорируем дубликат

        self.last_logs[guild.id] = (log_hash, now)

        try:
            channel_id = await self.bot.db.get_setting(guild.id, f"log_channel_{log_type}")
            embed = discord.Embed(title=title, description=description, color=color)
            embed.timestamp = discord.utils.utcnow()
            
            if user:
                embed.set_author(name=f"{user} (ID: {user.id})", icon_url=user.display_avatar.url)
                embed.set_footer(text=f"User ID: {user.id}")
            
            # 1. Пытаемся отправить в канал (Priority)
            sent_to_channel = False
            if channel_id:
                channel = guild.get_channel(int(channel_id))
                if not channel: # Если канала нет в кэше, пробуем его получить
                    try: channel = await guild.fetch_channel(int(channel_id))
                    except: channel = None
                
                if channel:
                    await channel.send(embed=embed)
                    sent_to_channel = True

            # 2. Если в канал НЕ отправили, пробуем вебхуки (Fallback)
            if not sent_to_channel:
                webhook_urls = [os.getenv('WEBHOOK_URL_1'), os.getenv('WEBHOOK_URL_2')]
                valid_urls = list(set([url for url in webhook_urls if url and "твой_" not in url]))
                if valid_urls:
                    async with aiohttp.ClientSession() as session:
                        for url in valid_urls:
                            webhook = discord.Webhook.from_url(url, session=session)
                            await webhook.send(embed=embed)
                            
        except Exception as e:
            print(f"[Logger Error] {e}")

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild: return
        content = message.content or "*Текст отсутствует*"
        details = f"**Канал:** {message.channel.mention}\n**Содержимое:**\n{content}"
        await self.bot.db.log_event(message.guild.id, message.author.id, "MESSAGE_DELETE", content)
        await self.send_log(message.guild, "message", "🗑️ Удалено сообщение", details, discord.Color.red(), user=message.author)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content: return
        details = f"**Канал:** {before.channel.mention}\n**Было:** {before.content}\n**Стало:** {after.content}"
        await self.bot.db.log_event(before.guild.id, before.author.id, "MESSAGE_EDIT", f"Old: {before.content} | New: {after.content}")
        await self.send_log(before.guild, "message", "✏️ Изменено сообщение", details, discord.Color.orange(), user=before.author)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self.bot.db.log_event(member.guild.id, member.id, "MEMBER_JOIN", "Joined server")
        await self.send_log(member.guild, "server", "👋 Новый участник", f"{member.mention} присоединился к серверу.", discord.Color.green(), user=member)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        executor, reason = None, "Не указана"
        try:
            async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                    executor, reason = entry.user, entry.reason or "Не указана"
                    break
        except: pass

        if executor:
            await self.bot.db.log_event(member.guild.id, member.id, "MEMBER_KICK", f"By {executor}: {reason}")
            await self.send_log(member.guild, "moderation", "👢 Участник кикнут", f"Модератор: {executor.mention}\nПричина: {reason}", discord.Color.red(), user=member)
        else:
            await self.bot.db.log_event(member.guild.id, member.id, "MEMBER_LEAVE", "Left server")
            await self.send_log(member.guild, "server", "🚪 Участник вышел", f"{member.name} покинул сервер.", discord.Color.dark_grey(), user=member)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel: return
        
        # 1. Join
        if before.channel is None:
            await self.bot.db.save_voice_entry(member.guild.id, member.id)
            await self.send_log(member.guild, "voice", "🎙️ Вход в голос", f"Зашел в **{after.channel.name}**", discord.Color.green(), user=member)
        
        # 2. Leave
        elif after.channel is None:
            join_time_str = await self.bot.db.pop_voice_entry(member.guild.id, member.id)
            duration_str = "Неизвестно"
            if join_time_str:
                try:
                    join_time = datetime.fromisoformat(join_time_str)
                    delta = datetime.now() - join_time
                    minutes, seconds = divmod(int(delta.total_seconds()), 60)
                    hours, minutes = divmod(minutes, 60)
                    duration_str = f"{hours}ч {minutes}м {seconds}с"
                except: pass
            
            await self.bot.db.log_voice(member.guild.id, member.id, before.channel.id, "LEAVE", duration_str)
            await self.send_log(member.guild, "voice", "🔇 Выход из голоса", f"Вышел из **{before.channel.name}**\n**Длительность:** {duration_str}", discord.Color.red(), user=member)
        
        # 3. Move
        else:
            await self.bot.db.log_voice(member.guild.id, member.id, after.channel.id, "MOVE")
            await self.send_log(member.guild, "voice", "🔄 Переход в голосе", f"Перешел из **{before.channel.name}** в **{after.channel.name}**", discord.Color.gold(), user=member)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            added = [r.mention for r in after.roles if r not in before.roles]
            removed = [r.mention for r in before.roles if r not in after.roles]
            if added or removed:
                details = ""
                if added: details += f"✅ **Выданы роли:** {', '.join(added)}\n"
                if removed: details += f"❌ **Сняты роли:** {', '.join(removed)}"
                await self.send_log(after.guild, "role", "🎭 Изменение ролей", details, discord.Color.blue(), user=after)

async def setup(bot):
    await bot.add_cog(LoggerCog(bot))
