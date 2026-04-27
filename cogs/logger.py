import discord
from discord.ext import commands
import os
import aiohttp

async def send_webhook_log(title, description, color=discord.Color.blurple()):
    webhook_urls = [
        os.getenv('WEBHOOK_URL_1'),
        os.getenv('WEBHOOK_URL_2')
    ]
    
    # Очищаем список от пустых значений и стандартных заглушек, убираем дубликаты
    valid_urls = list(set([url for url in webhook_urls if url and "твой_" not in url]))
    
    if not valid_urls:
        return
        
    try:
        async with aiohttp.ClientSession() as session:
            embed = discord.Embed(title=title, description=description, color=color)
            for url in valid_urls:
                webhook = discord.Webhook.from_url(url, session=session)
                await webhook.send(embed=embed)
    except Exception as e:
        print(f"[Ошибка Webhook] Не удалось отправить лог: {e}")

class LoggerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot



    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot:
            return
            
        content = message.content
        if message.attachments:
            content += f"\n**[Вложения: {', '.join([a.url for a in message.attachments])}]**"
        if message.embeds:
            content += "\n**[Содержит Embed]**"
            
        if not content.strip():
            content = "*Текст отсутствует (возможно, не включен Message Content Intent в настройках бота)*"
            
        details = (
            f"**Message ID:** {message.id}\n"
            f"**Author:** {message.author.name} (ID: {message.author.id})\n"
            f"**Channel:** {message.channel.mention}\n\n"
            f"**Content:**\n{content}"
        )
        
        # Сохраняем в базу (удаляем markdown для базы, чтобы было чище, или оставляем)
        db_details = details.replace('**', '')
        print(f"[LOG] Сообщение удалено от {message.author}")
        
        # Отправляем в вебхук
        await send_webhook_log("🗑️ Удалено сообщение", details, discord.Color.red())

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.content == after.content:
            return
        details = f"**Channel:** {before.channel.mention}\n**Old:** {before.content}\n**New:** {after.content}"
        await send_webhook_log("✏️ Сообщение изменено", f"**Author:** {before.author.mention}\n" + details, discord.Color.orange())

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await send_webhook_log("👋 Участник зашел", f"{member.mention} присоединился к серверу.", discord.Color.green())

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await send_webhook_log("🚪 Участник вышел", f"{member.name} покинул сервер.", discord.Color.red())

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.nick != after.nick:
            details = f"**Old nick:** {before.nick}\n**New nick:** {after.nick}"
            await send_webhook_log("📝 Изменен никнейм", f"Пользователь: {after.mention}\n{details}", discord.Color.blue())
        
        if before.roles != after.roles:
            added = [r.name for r in after.roles if r not in before.roles]
            removed = [r.name for r in before.roles if r not in after.roles]
            if added or removed:
                details = f"**Added roles:** {', '.join(added)}\n**Removed roles:** {', '.join(removed)}"
                await send_webhook_log("🎭 Изменены роли", f"Пользователь: {after.mention}\n{details}", discord.Color.blue())

        # Проверка на выдачу/снятие тайм-аута
        if before.timed_out_until != after.timed_out_until:
            executor = "Неизвестно"
            try:
                async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target.id == after.id and hasattr(entry.after, 'timed_out_until'):
                        executor = entry.user.mention
                        break
            except discord.Forbidden:
                executor = "Нет прав на просмотр Audit Logs"
                
            if after.timed_out_until:
                # Тайм-аут выдан
                until_fmt = f"<t:{int(after.timed_out_until.timestamp())}:F>"
                await send_webhook_log("⏳ Выдан Тайм-аут", f"Модератор {executor} выдал тайм-аут {after.mention} до {until_fmt}", discord.Color.red())
            else:
                # Тайм-аут снят
                await send_webhook_log("⏳ Снят Тайм-аут", f"Модератор {executor} досрочно снял тайм-аут с {after.mention}", discord.Color.green())

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        import asyncio
        import discord.utils
        
        # 1. Join / Leave / Move
        if before.channel is None and after.channel is not None:
            await send_webhook_log("🎙️ Вход в голос", f"{member.mention} зашел в канал **{after.channel.name}**", discord.Color.green())
            
        elif before.channel is not None and after.channel is None:
            # Задержка, чтобы Discord успел обновить Audit Logs
            await asyncio.sleep(2)
            
            # Проверим, не кикнул ли его модератор
            executor = None
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_disconnect):
                    if entry.target.id == member.id:
                        # Проверяем, что событие свежее (не старше 10 секунд)
                        if (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                            executor = entry.user.mention
                            break
            except discord.Forbidden:
                pass
                
            if executor:
                await send_webhook_log("👢 Кик из голоса", f"Модератор {executor} отключил {member.mention} от канала **{before.channel.name}**", discord.Color.red())
            else:
                await send_webhook_log("🔇 Выход из голоса", f"{member.mention} вышел из канала **{before.channel.name}**", discord.Color.red())
                
        elif before.channel != after.channel:
            # Задержка, чтобы Discord успел обновить Audit Logs
            await asyncio.sleep(2)
            
            # Проверим, не перенес ли его модератор
            executor = None
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_move):
                    if entry.target.id == member.id:
                        if (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                            executor = entry.user.mention
                            break
            except discord.Forbidden:
                pass
                
            if executor:
                await send_webhook_log("🔄 Перенос в голосе", f"Модератор {executor} переместил {member.mention} из **{before.channel.name}** в **{after.channel.name}**", discord.Color.gold())
            else:
                await send_webhook_log("🔄 Переход в голосе", f"{member.mention} перешел из **{before.channel.name}** в **{after.channel.name}**", discord.Color.gold())

        # 2. Серверный мут
        if not before.mute and after.mute:
            await asyncio.sleep(1)
            executor = "Неизвестно"
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target.id == member.id and hasattr(entry.after, 'mute') and entry.after.mute:
                        if (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                            executor = entry.user.mention
                            break
            except discord.Forbidden:
                executor = "Нет прав"
            await send_webhook_log("🤐 Серверный мут", f"Модератор {executor} отключил микрофон пользователю {member.mention}", discord.Color.red())
            
        elif before.mute and not after.mute:
            await asyncio.sleep(1)
            executor = "Неизвестно"
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target.id == member.id and hasattr(entry.after, 'mute') and not entry.after.mute:
                        if (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                            executor = entry.user.mention
                            break
            except discord.Forbidden:
                executor = "Нет прав"
            await send_webhook_log("🎤 Снятие мута", f"Модератор {executor} включил микрофон пользователю {member.mention}", discord.Color.green())

        # 3. Серверное отключение звука (Deafen)
        if not before.deaf and after.deaf:
            await asyncio.sleep(1)
            executor = "Неизвестно"
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target.id == member.id and hasattr(entry.after, 'deaf') and entry.after.deaf:
                        if (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                            executor = entry.user.mention
                            break
            except discord.Forbidden:
                executor = "Нет прав"
            await send_webhook_log("🎧 Отключение звука", f"Модератор {executor} отключил звук пользователю {member.mention}", discord.Color.red())
            
        elif before.deaf and not after.deaf:
            await asyncio.sleep(1)
            executor = "Неизвестно"
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_update):
                    if entry.target.id == member.id and hasattr(entry.after, 'deaf') and not entry.after.deaf:
                        if (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                            executor = entry.user.mention
                            break
            except discord.Forbidden:
                executor = "Нет прав"
            await send_webhook_log("🔊 Включение звука", f"Модератор {executor} включил звук пользователю {member.mention}", discord.Color.green())

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await send_webhook_log("📁 Канал создан", f"Название: **{channel.name}**\nТип: {channel.type}", discord.Color.green())

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await send_webhook_log("🗑️ Канал удален", f"Название: **{channel.name}**\nТип: {channel.type}", discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        executor = "Неизвестно"
        try:
            async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_create):
                if entry.target.id == role.id:
                    executor = entry.user.mention
                    break
        except discord.Forbidden:
            executor = "Нет прав на просмотр Audit Logs"
            
        details = f"**Название:** {role.name}\n**ID:** {role.id}\n**Кто создал:** {executor}"
        await send_webhook_log("🛡️ Роль создана", details, discord.Color.green())

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        executor = "Неизвестно"
        try:
            async for entry in role.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_delete):
                if entry.target.id == role.id:
                    executor = entry.user.mention
                    break
        except discord.Forbidden:
            executor = "Нет прав на просмотр Audit Logs"
            
        details = f"**Название:** {role.name}\n**ID:** {role.id}\n**Кто удалил:** {executor}"
        await send_webhook_log("🛡️ Роль удалена", details, discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if before.name == after.name and before.color == after.color and before.permissions == after.permissions:
            return # Игнорируем изменения позиции и другие мелкие вещи
            
        executor = "Неизвестно"
        try:
            async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.role_update):
                if entry.target.id == after.id:
                    executor = entry.user.mention
                    break
        except discord.Forbidden:
            executor = "Нет прав на просмотр Audit Logs"
            
        changes = []
        if before.name != after.name:
            changes.append(f"Имя: `{before.name}` -> `{after.name}`")
        if before.color != after.color:
            changes.append(f"Цвет: `{before.color}` -> `{after.color}`")
        if before.permissions != after.permissions:
            changes.append("Изменены права доступа")
            
        details = f"**Роль:** {after.mention} ({after.name})\n**Кто изменил:** {executor}\n**Изменения:**\n" + "\n".join(changes)
        await send_webhook_log("🛡️ Роль изменена", details, discord.Color.orange())



async def setup(bot):
    await bot.add_cog(LoggerCog(bot))
