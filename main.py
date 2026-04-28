import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from database import Database
from discord.ext import tasks

# Загружаем переменные окружения
load_dotenv()
TOKEN = os.getenv('TOKEN') or os.getenv('DISCORD_TOKEN')

# Настройка намерений (Intents)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.db = Database()

    async def setup_hook(self):
        # 1. Инициализация БД
        await self.db.initialize()
        
        # 2. Запуск фоновых задач
        self.cleanup_task.start()

        # 3. Загружаем cogs
        cogs = ["logger", "profile", "moderation", "security", "backup"]
        for cog in cogs:
            try:
                await self.load_extension(f"cogs.{cog}")
                print(f"Модуль {cog} загружен.")
            except Exception as e:
                print(f"Ошибка загрузки модуля {cog}: {e}")
        
        # 4. Синхронизация команд (один раз, глобально)
        print("Синхронизация команд...")
        await self.tree.sync()
        print("Команды синхронизированы.")

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        await self.db.cleanup_logs()

    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.wait_until_ready()

    async def on_ready(self):
        print(f'Бот {self.user} запущен! (PID: {os.getpid()})')
        print('---------')

bot = MyBot()

if __name__ == '__main__':
    if not TOKEN:
        print("Ошибка: Токен не найден!")
    else:
        bot.run(TOKEN)
