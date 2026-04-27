import discord
from discord.ext import commands
from discord import app_commands

class ProfileCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='profile', description='Показывает информацию о пользователе')
    async def show_profile(self, interaction: discord.Interaction, member: discord.Member = None):
        # Если пользователь не указан, показываем профиль того, кто вызвал команду
        member = member or interaction.user
        
        # Форматируем даты для красивого отображения с помощью встроенных таймштампов Discord
        created_at = int(member.created_at.timestamp())
        joined_at = int(member.joined_at.timestamp()) if member.joined_at else 0
        
        # Собираем роли (исключая @everyone)
        roles = [role.mention for role in member.roles if role.name != '@everyone']
        roles_str = " ".join(roles) if roles else "Нет ролей"
        if len(roles_str) > 1024:
            roles_str = roles_str[:1000] + "..."
            
        # Создаем красивый Embed-ответ
        embed = discord.Embed(
            title=f"Профиль пользователя {member.display_name}",
            color=member.color if member.color != discord.Color.default() else discord.Color.blurple()
        )
        
        embed.set_thumbnail(url=member.display_avatar.url if member.display_avatar else member.default_avatar.url)
        
        embed.add_field(name="🏷️ Имя пользователя (Tag)", value=f"`{member.name}`", inline=True)
        embed.add_field(name="🆔 ID", value=f"`{member.id}`", inline=True)
        
        # Используем Discord Timestamp formatting <t:TIMESTAMP:F> (полная дата) и <t:TIMESTAMP:R> (сколько времени назад)
        embed.add_field(name="📅 Регистрация в Discord", value=f"<t:{created_at}:F> (<t:{created_at}:R>)", inline=False)
        
        if joined_at:
            embed.add_field(name="📥 Зашел на сервер", value=f"<t:{joined_at}:F> (<t:{joined_at}:R>)", inline=False)
            
        embed.add_field(name=f"🎭 Роли [{len(roles)}]", value=roles_str, inline=False)
        
        # Высший ранг (top role)
        embed.set_footer(text=f"Высшая роль: {member.top_role.name}")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ProfileCog(bot))
