import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio

# --- Настройка ---
# Загружаем переменные окружения из .env файла
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
PARSE_CHANNEL_ID = os.getenv('PARSE_CHANNEL_ID')
LOG_CHANNEL_ID = os.getenv('LOG_CHANNEL_ID')

# Проверяем, что все переменные окружения заданы
if not all([TOKEN, PARSE_CHANNEL_ID, LOG_CHANNEL_ID]):
    print("Ошибка: Не все переменные окружения (DISCORD_TOKEN, PARSE_CHANNEL_ID, LOG_CHANNEL_ID) заданы.")
    print("Пожалуйста, создайте или проверьте ваш .env файл или переменные на хостинге.")
    exit()

# Определяем намерения (Intents) - разрешения, которые нужны боту
intents = discord.Intents.default()
intents.message_content = True # Необходимо для чтения содержимого сообщений
intents.members = True       # Необходимо для получения информации о пользователях сервера

class MyBot(commands.Bot):
    """
    Основной класс бота, наследуемый от commands.Bot.
    При инициализации он создает путь к постоянному хранилищу, 
    который будет использоваться всеми когами.
    """
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        # Путь к постоянному хранилищу данных (для хостинга с Volume)
        self.data_path = '/data'
        # Убедимся, что директория существует при запуске. Если нет - создаем.
        os.makedirs(self.data_path, exist_ok=True)

    async def setup_hook(self):
        """Выполняется при запуске бота для загрузки модулей (когов)."""
        initial_extensions = [
            'cogs.category_cog',
            'cogs.blum_cog',
            'cogs.logs_cog'
        ]
        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
                print(f"Ког '{extension.split('.')[-1]}' успешно загружен.")
            except Exception as e:
                print(f"Не удалось загрузить ког '{extension.split('.')[-1]}': {e}")
        
        # Синхронизируем слэш-команды с Discord
        try:
            synced = await self.tree.sync()
            print(f"Синхронизировано {len(synced)} команд.")
        except Exception as e:
            print(f"Ошибка при синхронизации команд: {e}")

    async def on_ready(self):
        """Событие, которое выполняется, когда бот успешно подключился к Discord."""
        print(f'Бот {self.user} ({self.user.id}) успешно запущен!')
        await self.change_presence(activity=discord.Game(name="Анализирую логи"))


async def main():
    """Основная асинхронная функция для запуска бота."""
    bot = MyBot()
    async with bot:
        await bot.start(TOKEN)

# --- Точка входа ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TypeError as e:
        if "received NoneType instead" in str(e):
            print("\nКРИТИЧЕСКАЯ ОШИБКА: Токен не найден.")
            print("Убедитесь, что переменная DISCORD_TOKEN правильно установлена в .env файле или на хостинге.\n")
        else:
            raise e
    except discord.errors.LoginFailure:
        print("\nКРИТИЧЕСКАЯ ОШИБКА: Неверный токен.")
        print("Пожалуйста, проверьте правильность токена в .env файле или на хостинге.\n")
    except Exception as e:
        print(f"Произошла непредвиденная ошибка при запуске бота: {e}")

