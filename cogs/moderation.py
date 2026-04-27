import discord
from discord.ext import commands
from discord import app_commands

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='clean', description='Очищает до 50 сообщений в текущем чате')
    @app_commands.default_permissions(manage_messages=True)
    async def clean(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 50]):
        # Откладываем ответ, так как удаление может занять пару секунд
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Удаляем сообщения
            deleted = await interaction.channel.purge(limit=amount)
            # Отправляем скрытый отчет об успехе
            await interaction.followup.send(f"🧹 Успешно удалено **{len(deleted)}** сообщений.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ У бота нет прав для удаления сообщений в этом канале.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Произошла ошибка: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
