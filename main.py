import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from discord import app_commands

# --- Загрузка переменных окружения ---
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ROLE_ID = os.getenv('ADMIN_ROLE_ID')

# Проверка наличия обязательных переменных
if not all([TOKEN, os.getenv('PARSE_CHANNEL_ID'), os.getenv('LOG_CHANNEL_ID'), ADMIN_ROLE_ID]):
    print("Ошибка: Одна или несколько обязательных переменных окружения не установлены.")
    print("Убедитесь, что DISCORD_TOKEN, PARSE_CHANNEL_ID, LOG_CHANNEL_ID и ADMIN_ROLE_ID заданы.")
    exit()

# --- Настройка намерений (Intents) ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# --- Класс кастомного бота ---
class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_path = os.environ.get('RAILWAY_VOLUME_MOUNT_PATH', '.')
        print(f"Путь для сохранения данных: {self.data_path}")
        os.makedirs(self.data_path, exist_ok=True)
        self.initial_cogs = [
            'cogs.category_cog',
            'cogs.blum_cog',
            'cogs.logs_cog',
            'cogs.help_cog',
            'cogs.point_cog'
        ]

    async def on_tree_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Глобальный обработчик ошибок для слэш-команд."""
        if isinstance(error, app_commands.CheckFailure):
            # Отправляем сообщение, если проверка is_admin не пройдена
            await interaction.response.send_message("У вас нет прав для выполнения этой команды.", ephemeral=True)
        else:
            print(f"Необработанная ошибка в дереве команд: {error}")
            # Отправляем общее сообщение об ошибке, если ответ еще не был отправлен
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла непредвиденная ошибка при выполнении команды.", ephemeral=True)
            else:
                await interaction.followup.send("Произошла непредвиденная ошибка при выполнении команды.", ephemeral=True)

    async def setup_hook(self):
        """Выполняется при запуске бота для загрузки когов и установки обработчика ошибок."""
        self.tree.on_error = self.on_tree_error # Привязываем обработчик ошибок
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
            synced = await self.tree.sync()
            print(f"Синхронизировано {len(synced)} команд.")
        except Exception as e:
            print(f"Ошибка при синхронизации команд: {e}")

# --- Новая, корректная функция для проверки прав администратора ---
def is_admin():
    """
    Проверяет, имеет ли пользователь необходимую роль.
    Эта версия не отправляет сообщений, а просто возвращает True/False,
    позволяя глобальному обработчику ошибок отправлять ответ.
    """
    async def predicate(interaction: discord.Interaction) -> bool:
        try:
            admin_role = interaction.guild.get_role(int(ADMIN_ROLE_ID))
            # Проверка вернет True если роль существует и есть у пользователя
            return admin_role in interaction.user.roles
        except (ValueError, AttributeError):
            # Если ADMIN_ROLE_ID не установлен или некорректен, прав нет
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

