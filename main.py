import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# Получаем токен из переменных окружения
TOKEN = os.getenv('TOKEN') or os.getenv('DISCORD_TOKEN')

# Настройка намерений (Intents) для бота
intents = discord.Intents.default()
intents.message_content = True  # Разрешает боту читать содержимое сообщений
intents.members = True          # Разрешает боту видеть участников сервера
intents.presences = True        # Разрешает боту видеть статусы активности (нужно для некоторых обновлений)

from database import Database
from discord.ext import tasks

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.db = Database()

    async def setup_hook(self):
        # Инициализация БД
        await self.db.initialize()
        
        # Запуск задачи очистки логов (раз в 24 часа)
        self.cleanup_task.start()

        # Загружаем cogs
        await self.load_extension("cogs.logger")
        print("Модуль логирования (cogs.logger) загружен.")
        
        await self.load_extension("cogs.profile")
        print("Модуль профилей (cogs.profile) загружен.")
        
        await self.load_extension("cogs.moderation")
        print("Модуль модерации (cogs.moderation) загружен.")
        
        await self.load_extension("cogs.security")
        print("Модуль безопасности (cogs.security) загружен.")

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        await self.db.cleanup_logs()

    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.wait_until_ready()

    async def on_ready(self):
        print(f'Бот {self.user} успешно запущен и готов к работе!')
        print('---------')
        
        # Чтобы не было дубликатов, мы полностью удаляем серверные (локальные) команды.
        for guild in self.guilds:
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            
        # И оставляем ТОЛЬКО глобальные команды (они дают плашку в профиле).
        await self.tree.sync()
        
        print("Дубликаты удалены, оставлены только 2 глобальные команды. Обновите Discord (Ctrl+R).")

bot = MyBot()



# Запуск бота
if __name__ == '__main__':
    if not TOKEN:
        print("Нет токена в переменных окружения!")
        exit()
    else:
        bot.run(TOKEN)
