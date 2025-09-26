import discord
from discord import app_commands  # <-- Добавлен этот импорт
from discord.ext import commands
import json
import os
from main import is_admin  # Импортируем наш декоратор для проверки прав


class BlumCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Получаем путь к данным из основного объекта бота
        self.data_path = getattr(self.bot, 'data_path', '.')
        self.blum_file = os.path.join(self.data_path, 'blum_list.json')

    # --- Вспомогательные функции ---
    def _load_blum_list(self):
        """Загружает список Blum из файла."""
        try:
            with open(self.blum_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_blum_list(self, data):
        """Сохраняет список Blum в файл."""
        with open(self.blum_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)

    # --- Группа команд /blum ---
    blum_group = app_commands.Group(name="blum", description="Команды для управления списком Blum")

    @blum_group.command(name="add", description="Добавить пользователя в список Blum.")
    @app_commands.guild_only()
    @is_admin()  # <-- Проверка прав
    async def add_blum(self, interaction: discord.Interaction, пользователь: discord.User):
        blum_list = self._load_blum_list()
        if пользователь.id in blum_list:
            await interaction.response.send_message(f"Пользователь {пользователь.mention} уже в списке Blum.",
                                                      ephemeral=True)
        else:
            blum_list.append(пользователь.id)
            self._save_blum_list(blum_list)
            await interaction.response.send_message(f"Пользователь {пользователь.mention} успешно добавлен в список Blum.",
                                                      ephemeral=True)

    @blum_group.command(name="remove", description="Убрать пользователя из списка Blum.")
    @app_commands.guild_only()
    @is_admin()  # <-- Проверка прав
    async def remove_blum(self, interaction: discord.Interaction, пользователь: discord.User):
        blum_list = self._load_blum_list()
        if пользователь.id not in blum_list:
            await interaction.response.send_message(f"Пользователь {пользователь.mention} не найден в списке Blum.",
                                                      ephemeral=True)
        else:
            blum_list.remove(пользователь.id)
            self._save_blum_list(blum_list)
            await interaction.response.send_message(f"Пользователь {пользователь.mention} успешно убран из списка Blum.",
                                                      ephemeral=True)

    @blum_group.command(name="list", description="Показать всех пользователей в списке Blum.")
    @app_commands.guild_only()
    @is_admin()  # <-- Проверка прав
    async def list_blum(self, interaction: discord.Interaction):
        blum_list = self._load_blum_list()
        if not blum_list:
            await interaction.response.send_message("Список Blum пуст.", ephemeral=True)
            return

        description = "\n".join([f"<@{user_id}>" for user_id in blum_list])
        embed = discord.Embed(title="Список Blum", description=description, color=discord.Color.purple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @blum_group.command(name="clear", description="Полностью очистить список Blum.")
    @app_commands.guild_only()
    @is_admin()  # <-- Проверка прав
    async def clear_blum(self, interaction: discord.Interaction):
        self._save_blum_list([])
        await interaction.response.send_message("Список Blum был полностью очищен.", ephemeral=True)


async def setup(bot: commands.Bot):
    cog = BlumCog(bot)
    # Групповые команды нужно добавлять в дерево команд бота напрямую
    bot.tree.add_command(cog.blum_group)

