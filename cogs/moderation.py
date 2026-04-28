import discord
from discord.ext import commands
from discord import app_commands
from typing import Optional, Literal
from datetime import datetime

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log_mod_action(self, guild, title, description, color=discord.Color.blue()):
        # Вспомогательная функция для логирования модерации
        logger = self.bot.get_cog("LoggerCog")
        if logger:
            await logger.send_log(guild, "moderation", title, description, color)

    @app_commands.command(name='clean', description='Очищает сообщения в текущем чате')
    @app_commands.default_permissions(manage_messages=True)
    async def clean(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await interaction.channel.purge(limit=amount)
            await interaction.followup.send(f"🧹 Удалено **{len(deleted)}** сообщений.", ephemeral=True)
            await self.log_mod_action(interaction.guild, "🧹 Очистка чата", f"Модератор {interaction.user.mention} удалил {len(deleted)} сообщений в {interaction.channel.mention}")
        except Exception as e:
            await interaction.followup.send(f"❌ Ошибка: {e}", ephemeral=True)

    @app_commands.command(name='warn', description='Выдать предупреждение пользователю')
    @app_commands.default_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await self.bot.db.add_warning(interaction.guild_id, member.id, interaction.user.id, reason)
        embed = discord.Embed(title="⚠️ Предупреждение", color=discord.Color.yellow())
        embed.add_field(name="Пользователь", value=member.mention, inline=True)
        embed.add_field(name="Модератор", value=interaction.user.mention, inline=True)
        embed.add_field(name="Причина", value=reason, inline=False)
        await interaction.response.send_message(embed=embed)
        await self.log_mod_action(interaction.guild, "⚠️ Выдано предупреждение", f"Модератор: {interaction.user.mention}\nПользователь: {member.mention}\nПричина: {reason}")
        try: await member.send(f"Вы получили предупреждение на сервере **{interaction.guild.name}**\nПричина: {reason}")
        except: pass

    @app_commands.command(name='warnings', description='Посмотреть предупреждения пользователя')
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        warns = await self.bot.db.get_warnings(interaction.guild_id, member.id)
        if not warns:
            return await interaction.response.send_message(f"У {member.mention} нет предупреждений.", ephemeral=True)
        embed = discord.Embed(title=f"⚠️ Предупреждения: {member.name}", color=discord.Color.orange())
        for warn_id, mod_id, reason, timestamp in warns:
            embed.add_field(name=f"ID: {warn_id}", value=f"Модератор: <@{mod_id}>\nПричина: {reason}\nДата: {timestamp}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='unwarn', description='Удалить предупреждение по ID')
    @app_commands.default_permissions(moderate_members=True)
    async def unwarn(self, interaction: discord.Interaction, warn_id: int):
        await self.bot.db.delete_warning(warn_id)
        await interaction.response.send_message(f"✅ Предупреждение ID `{warn_id}` удалено.", ephemeral=True)
        await self.log_mod_action(interaction.guild, "✅ Предупреждение удалено", f"Модератор {interaction.user.mention} удалил предупреждение ID `{warn_id}`")

    @app_commands.command(name='setlogchannel', description='Назначить канал для логов')
    @app_commands.default_permissions(administrator=True)
    async def setlogchannel(self, interaction: discord.Interaction, 
                           type: Literal['message', 'voice', 'moderation', 'role', 'server'], 
                           channel: discord.TextChannel):
        await self.bot.db.set_setting(interaction.guild_id, f"log_channel_{type}", channel.id)
        await interaction.response.send_message(f"✅ Канал для логов типа `{type}` установлен: {channel.mention}", ephemeral=True)

    @app_commands.command(name='settings', description='Показать текущие настройки логов')
    @app_commands.default_permissions(administrator=True)
    async def settings(self, interaction: discord.Interaction):
        settings = await self.bot.db.get_all_settings(interaction.guild_id)
        embed = discord.Embed(title="⚙️ Настройки бота", color=discord.Color.blue())
        if not settings:
            embed.description = "Настройки еще не заданы."
        for key, value in settings:
            if key.startswith("log_channel_"):
                type_name = key.replace("log_channel_", "")
                embed.add_field(name=f"Логи: {type_name}", value=f"<#{value}>", inline=True)
            else:
                embed.add_field(name=key, value=value, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='userlog', description='Показать последние действия пользователя')
    @app_commands.default_permissions(moderate_members=True)
    async def userlog(self, interaction: discord.Interaction, member: discord.Member):
        logs = await self.bot.db.get_user_logs(interaction.guild_id, member.id)
        if not logs:
            return await interaction.response.send_message(f"Действий пользователя {member.mention} не найдено.", ephemeral=True)
        embed = discord.Embed(title=f"📋 Логи: {member.name}", color=discord.Color.blue())
        for action, details, timestamp in logs:
            embed.add_field(name=f"{timestamp} | {action}", value=details[:1024], inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='searchlogs', description='Поиск по логам')
    @app_commands.default_permissions(moderate_members=True)
    async def searchlogs(self, interaction: discord.Interaction, 
                         member: Optional[discord.Member] = None, 
                         action: Optional[str] = None, 
                         date: Optional[str] = None):
        user_id = member.id if member else None
        results = await self.bot.db.search_logs(interaction.guild_id, user_id, action, date)
        if not results:
            return await interaction.response.send_message("Ничего не найдено.", ephemeral=True)
        embed = discord.Embed(title="🔍 Результаты поиска", color=discord.Color.blue())
        for u_id, act, det, ts in results:
            embed.add_field(name=f"{ts} | {act}", value=f"Пользователь: <@{u_id}>\nИнфо: {det[:500]}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='modstats', description='Статистика модерации')
    @app_commands.default_permissions(moderate_members=True)
    async def modstats(self, interaction: discord.Interaction):
        stats = await self.bot.db.get_mod_stats(interaction.guild_id)
        embed = discord.Embed(title="📊 Статистика модерации", color=discord.Color.purple())
        
        warn_text = "\n".join([f"<@{m_id}>: {count}" for m_id, count in stats['warns']]) or "Нет данных"
        embed.add_field(name="Предупреждений выдано", value=warn_text, inline=False)
        
        action_text = "\n".join([f"{act}: {count}" for act, count in stats['actions']]) or "Нет данных"
        embed.add_field(name="Всего действий в логах", value=action_text, inline=False)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
