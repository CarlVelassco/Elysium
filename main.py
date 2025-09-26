import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

# --- Загрузка переменных окружения ---
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ROLE_ID = os.getenv('ADMIN_ROLE_ID') # Новая переменная для ID роли администратора

# Проверка наличия обязательных переменных
if not all([TOKEN, os.getenv('PARSE_CHANNEL_ID'), os.getenv('LOG_CHANNEL_ID'), ADMIN_ROLE_ID]):
    print("Ошибка: Одна или несколько обязательных переменных окружения не установлены.")
    print("Убедитесь, что DISCORD_TOKEN, PARSE_CHANNEL_ID, LOG_CHANNEL_ID и ADMIN_ROLE_ID заданы в .env файле.")
    exit()

# --- Настройка намерений (Intents) ---
intents = discord.Intents.default()
intents.message_content = True # Необходимо для некоторых операций
intents.members = True # Необходимо для доступа к информации об участниках

# --- Класс кастомного бота ---
class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Путь для сохранения данных. На Railway это будет /data
        self.data_path = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '.')
        print(f"Путь для сохранения данных: {self.data_path}")
        # Создаем директорию, если она не существует
        os.makedirs(self.data_path, exist_ok=True)
        self.initial_cogs = [
            'cogs.category_cog',
            'cogs.blum_cog',
            'cogs.logs_cog',
            'cogs.help_cog' # Новый ког для команды /help
        ]

    async def setup_hook(self):
        """Выполняется при запуске бота для загрузки когов."""
        for cog in self.initial_cogs:
            try:
                await self.load_extension(cog)
                print(f"Ког '{cog.split('.')[-1]}' успешно загружен.")
            except Exception as e:
                print(f"Не удалось загрузить ког '{cog.split('.')[-1]}': {e}")
    
    async def on_ready(self):
        """Вызывается, когда бот готов к работе."""
        print(f'Бот {self.user} успешно запущен!')
        try:
            # Синхронизация команд с Discord
            synced = await self.tree.sync()
            print(f"Синхронизировано {len(synced)} команд.")
        except Exception as e:
            print(f"Ошибка при синхронизации команд: {e}")

# --- Вспомогательная функция для проверки прав администратора ---
def is_admin():
    """Проверяет, имеет ли пользователь необходимую роль для выполнения команды."""
    async def predicate(interaction: discord.Interaction) -> bool:
        # Получаем объект роли по ID
        admin_role = interaction.guild.get_role(int(ADMIN_ROLE_ID))
        if admin_role is None:
            await interaction.response.send_message("Ошибка конфигурации: Роль администратора не найдена на сервере.", ephemeral=True)
            return False
            
        # Проверяем, есть ли у пользователя эта роль
        if admin_role in interaction.user.roles:
            return True
        else:
            await interaction.response.send_message("У вас нет прав для выполнения этой команды.", ephemeral=True)
            return False
    return app_commands.check(predicate)

# --- Основная функция для запуска ---
async def main():
    bot = MyBot(command_prefix="!", intents=intents)
    await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Критическая ошибка при запуске бота: {e}")

