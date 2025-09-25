import discord
from discord.ext import commands
import os
import json
from dotenv import load_dotenv

# --- Загрузка конфигурации ---
# Загружаем переменные окружения из файла .env
load_dotenv()

# Получаем токен и ID каналов из переменных окружения
# ВАЖНО: Создайте файл .env в той же директории, что и main.py
# и добавьте в него следующие строки, заменив значения на свои:
# TOKEN="ВАШ_ТОКЕН_БОТА"
# PARSE_CHANNEL_ID=ID_КАНАЛА_ДЛЯ_ПАРСИНГА
# LOG_CHANNEL_ID=ID_КАНАЛА_ДЛЯ_ОТПРАВКИ_ЛОГОВ
TOKEN = os.getenv("TOKEN")
PARSE_CHANNEL_ID = int(os.getenv("PARSE_CHANNEL_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))

# --- Настройка бота ---
# Определяем необходимые намерения (Intents)
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.message_content = True

# Создаем экземпляр бота
bot = commands.Bot(command_prefix="/", intents=intents)

# --- Инициализация файлов данных ---
# При запуске проверяем, существуют ли файлы для хранения данных.
# Если нет, создаем их с пустыми структурами.
def initialize_data_files():
    """Инициализирует файлы JSON для хранения данных, если они не существуют."""
    if not os.path.exists('categories.json'):
        with open('categories.json', 'w', encoding='utf-8') as f:
            # Категории хранятся в формате: {"Название категории": ["Ивент1", "Ивент2"]}
            json.dump({"Other": []}, f, ensure_ascii=False, indent=4)
    if not os.path.exists('blum_list.json'):
        with open('blum_list.json', 'w', encoding='utf-8') as f:
            # Blum лист хранится как список ID пользователей
            json.dump([], f, ensure_ascii=False, indent=4)

# --- Событие готовности бота ---
@bot.event
async def on_ready():
    """Событие, которое выполняется при успешном запуске и подключении бота."""
    print(f'Бот {bot.user} успешно запущен!')
    try:
        # Синхронизируем команды с Discord, чтобы они появились в списке
        synced = await bot.tree.sync()
        print(f"Синхронизировано {len(synced)} команд.")
    except Exception as e:
        print(f"Ошибка синхронизации команд: {e}")
    # Инициализируем файлы данных при запуске
    initialize_data_files()

# --- Загрузка расширений (Cogs) ---
# Асинхронная функция для загрузки всех файлов с командами (когов).
async def load_cogs():
    """Загружает все коги из директории cogs."""
    # Мы будем использовать коги для лучшей организации кода.
    # Файлы с командами должны находиться в папке /cogs
    if not os.path.exists('cogs'):
        os.makedirs('cogs')
    # Имена файлов когов (без .py)
    cogs_to_load = ['category_cog', 'blum_cog', 'logs_cog']
    for cog_name in cogs_to_load:
        try:
            await bot.load_extension(f'cogs.{cog_name}')
            print(f"Ког '{cog_name}' успешно загружен.")
        except Exception as e:
            print(f"Не удалось загрузить ког '{cog_name}': {e}")


# --- Основная точка входа ---
async def main():
    """Основная функция для запуска бота."""
    # Передаем ID каналов в коги через атрибуты бота
    bot.parse_channel_id = PARSE_CHANNEL_ID
    bot.log_channel_id = LOG_CHANNEL_ID
    # Загружаем коги
    await load_cogs()
    # Запускаем бота с токеном
    await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio
    # Запускаем основную асинхронную функцию
    asyncio.run(main())
