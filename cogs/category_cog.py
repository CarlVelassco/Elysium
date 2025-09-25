import discord
from discord import app_commands
from discord.ext import commands
import json
import os

class CategoryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Получаем путь к данным из основного объекта бота для централизованного управления
        self.data_path = getattr(self.bot, 'data_path', '.')
        self.categories_file = os.path.join(self.data_path, 'categories.json')
        self.categories = self._load_json()

    def _load_json(self):
        """Загружает данные из JSON файла. Если файл не существует, создает его."""
        try:
            with open(self.categories_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # Если файл не найден или пуст, создаем его с пустым словарем
            self._save_json({})
            return {}

    def _save_json(self, data=None):
        """Сохраняет данные в JSON файл."""
        with open(self.categories_file, 'w', encoding='utf-8') as f:
            json.dump(data if data is not None else self.categories, f, ensure_ascii=False, indent=4)

    category = app_commands.Group(name="category", description="Команды для управления категориями ивентов")

    @category.command(name="create", description="Создать новую категорию.")
    @app_commands.describe(название="Название новой категории")
    async def create(self, interaction: discord.Interaction, название: str):
        self.categories = self._load_json()
        if название in self.categories:
            await interaction.response.send_message(f"Категория '{название}' уже существует.", ephemeral=True)
        else:
            self.categories[название] = []
            self._save_json()
            await interaction.response.send_message(f"Категория '{название}' успешно создана.", ephemeral=True)

    @category.command(name="delete", description="Удалить существующую категорию.")
    @app_commands.describe(название="Название категории для удаления")
    async def delete(self, interaction: discord.Interaction, название: str):
        self.categories = self._load_json()
        if название not in self.categories:
            await interaction.response.send_message(f"Категория '{название}' не найдена.", ephemeral=True)
        else:
            del self.categories[название]
            self._save_json()
            await interaction.response.send_message(f"Категория '{название}' успешно удалена.", ephemeral=True)

    @category.command(name="add", description="Добавить ивент в категорию.")
    @app_commands.describe(категория="Категория, в которую добавляем", ивент="Название ивента")
    async def add(self, interaction: discord.Interaction, категория: str, ивент: str):
        self.categories = self._load_json()
        if категория not in self.categories:
            await interaction.response.send_message(f"Категория '{категория}' не найдена.", ephemeral=True)
            return
        
        # Проверка на дубликаты без учета регистра
        if ивент.lower() in [e.lower() for e in self.categories[категория]]:
            await interaction.response.send_message(f"Ивент '{ивент}' уже есть в категории '{категория}'.", ephemeral=True)
        else:
            self.categories[категория].append(ивент)
            self._save_json()
            await interaction.response.send_message(f"Ивент '{ивент}' успешно добавлен в категорию '{категория}'.", ephemeral=True)

    @category.command(name="remove", description="Удалить ивент из категории.")
    @app_commands.describe(категория="Категория, из которой удаляем", ивент="Название ивента")
    async def remove(self, interaction: discord.Interaction, категория: str, ивент: str):
        self.categories = self._load_json()
        if категория not in self.categories:
            await interaction.response.send_message(f"Категория '{категория}' не найдена.", ephemeral=True)
            return
        
        # Ищем ивент без учета регистра для корректного удаления
        event_to_remove = next((e for e in self.categories[категория] if e.lower() == ивент.lower()), None)
        
        if not event_to_remove:
            await interaction.response.send_message(f"Ивент '{ивент}' не найден в категории '{категория}'.", ephemeral=True)
        else:
            self.categories[категория].remove(event_to_remove)
            self._save_json()
            await interaction.response.send_message(f"Ивент '{ивент}' успешно удален из категории '{категория}'.", ephemeral=True)

    @category.command(name="list", description="Показать список всех категорий и их ивентов.")
    async def list(self, interaction: discord.Interaction):
        self.categories = self._load_json()
        if not self.categories:
            await interaction.response.send_message("Нет созданных категорий.", ephemeral=True)
            return

        embed = discord.Embed(title="Список категорий и ивентов", color=discord.Color.blue())
        for category, events in self.categories.items():
            event_list = "\n".join(f"- {event}" for event in events) if events else "*Пусто*"
            embed.add_field(name=f"📁 {category}", value=event_list, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(CategoryCog(bot))

