import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from main import is_admin

class CategoryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_path = getattr(self.bot, 'data_path', '.')
        self.categories_file = os.path.join(self.data_path, 'categories.json')

    def _load_categories(self):
        try:
            with open(self.categories_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_categories(self, data):
        with open(self.categories_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    category_group = app_commands.Group(name="category", description="Команды для управления категориями ивентов")

    @category_group.command(name="create", description="Создать новую категорию.")
    @app_commands.guild_only()
    @is_admin()
    async def create_category(self, interaction: discord.Interaction, название: str):
        categories = self._load_categories()
        if название in categories:
            await interaction.response.send_message(f"Категория '{название}' уже существует.", ephemeral=True)
        else:
            categories[название] = []
            self._save_categories(categories)
            await interaction.response.send_message(f"Категория '{название}' успешно создана.", ephemeral=True)

    @category_group.command(name="delete", description="Удалить существующую категорию.")
    @app_commands.guild_only()
    @is_admin()
    async def delete_category(self, interaction: discord.Interaction, название: str):
        categories = self._load_categories()
        if название not in categories:
            await interaction.response.send_message(f"Категория '{название}' не найдена.", ephemeral=True)
        else:
            del categories[название]
            self._save_categories(categories)
            await interaction.response.send_message(f"Категория '{название}' успешно удалена.", ephemeral=True)

    @category_group.command(name="add", description="Добавить ивент в категорию.")
    @app_commands.guild_only()
    @is_admin()
    async def add_to_category(self, interaction: discord.Interaction, категория: str, ивент: str):
        categories = self._load_categories()
        if категория not in categories:
            await interaction.response.send_message(f"Категория '{категория}' не найдена.", ephemeral=True)
        else:
            if ивент in categories[категория]:
                await interaction.response.send_message(f"Ивент '{ивент}' уже находится в категории '{категория}'.", ephemeral=True)
            else:
                categories[категория].append(ивент)
                self._save_categories(categories)
                await interaction.response.send_message(f"Ивент '{ивент}' успешно добавлен в категорию '{категория}'.", ephemeral=True)

    @category_group.command(name="remove", description="Удалить ивент из категории.")
    @app_commands.guild_only()
    @is_admin()
    async def remove_from_category(self, interaction: discord.Interaction, категория: str, ивент: str):
        categories = self._load_categories()
        if категория not in categories:
            await interaction.response.send_message(f"Категория '{категория}' не найдена.", ephemeral=True)
        elif ивент not in categories[категория]:
            await interaction.response.send_message(f"Ивент '{ивент}' не найден в категории '{категория}'.", ephemeral=True)
        else:
            categories[категория].remove(ивент)
            self._save_categories(categories)
            await interaction.response.send_message(f"Ивент '{ивент}' успешно удален из категории '{категория}'.", ephemeral=True)

    @category_group.command(name="list", description="Показать список всех категорий и их ивентов.")
    @app_commands.guild_only()
    @is_admin()
    async def list_categories(self, interaction: discord.Interaction):
        categories = self._load_categories()
        if not categories:
            await interaction.response.send_message("Список категорий пуст.", ephemeral=True)
            return

        embed = discord.Embed(title="Список категорий и их ивентов", color=discord.Color.green())
        for name, events in categories.items():
            event_list = "\n".join(f"- {event}" for event in events) if events else "Пусто"
            embed.add_field(name=f"Категория: {name}", value=event_list, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    cog = CategoryCog(bot)
    bot.tree.add_command(cog.category_group)

