import discord
from discord.ext import commands
from discord import app_commands
import json

class CategoryCog(commands.Cog):
    """Ког для управления категориями ивентов."""
    def __init__(self, bot):
        self.bot = bot
        self.categories_file = 'categories.json'

    def load_categories(self):
        """Загружает категории из JSON файла."""
        with open(self.categories_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_categories(self, data):
        """Сохраняет категории в JSON файл."""
        with open(self.categories_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    category_group = app_commands.Group(name="category", description="Команды для управления категориями")

    @category_group.command(name="create", description="Создать новую категорию")
    @app_commands.describe(name="Название новой категории")
    async def create_category(self, interaction: discord.Interaction, name: str):
        """Создает новую категорию для ивентов."""
        categories = self.load_categories()
        if name in categories:
            await interaction.response.send_message(f"Категория `{name}` уже существует.", ephemeral=True)
            return
        categories[name] = []
        self.save_categories(categories)
        await interaction.response.send_message(f"Категория `{name}` успешно создана.", ephemeral=True)

    @category_group.command(name="delete", description="Удалить существующую категорию")
    @app_commands.describe(name="Название категории для удаления")
    async def delete_category(self, interaction: discord.Interaction, name: str):
        """Удаляет существующую категорию."""
        categories = self.load_categories()
        if name == "Other":
            await interaction.response.send_message("Нельзя удалить категорию по умолчанию `Other`.", ephemeral=True)
            return
        if name not in categories:
            await interaction.response.send_message(f"Категория `{name}` не найдена.", ephemeral=True)
            return

        # Перемещаем ивенты из удаляемой категории в 'Other'
        events_to_move = categories[name]
        if "Other" in categories:
             categories["Other"].extend(events_to_move)
        else:
             categories["Other"] = events_to_move

        del categories[name]
        self.save_categories(categories)
        await interaction.response.send_message(f"Категория `{name}` удалена. Все ивенты перемещены в `Other`.", ephemeral=True)

    @delete_category.autocomplete('name')
    async def delete_category_autocomplete(self, interaction: discord.Interaction, current: str):
        """Автодополнение для команды удаления категории."""
        categories = self.load_categories()
        return [
            app_commands.Choice(name=cat, value=cat)
            for cat in categories if current.lower() in cat.lower() and cat != "Other"
        ]

    @category_group.command(name="add", description="Добавить ивент в категорию")
    @app_commands.describe(category_name="Название категории", event_name="Название ивента")
    async def add_event_to_category(self, interaction: discord.Interaction, category_name: str, event_name: str):
        """Добавляет ивент в указанную категорию."""
        categories = self.load_categories()
        if category_name not in categories:
            await interaction.response.send_message(f"Категория `{category_name}` не найдена.", ephemeral=True)
            return
        # Удаляем ивент из всех других категорий, чтобы избежать дублирования
        for cat, events in categories.items():
            if event_name in events:
                events.remove(event_name)

        categories[category_name].append(event_name)
        self.save_categories(categories)
        await interaction.response.send_message(f"Ивент `{event_name}` добавлен в категорию `{category_name}`.", ephemeral=True)

    @add_event_to_category.autocomplete('category_name')
    async def add_event_autocomplete(self, interaction: discord.Interaction, current: str):
        """Автодополнение для выбора категории при добавлении ивента."""
        categories = self.load_categories()
        return [
            app_commands.Choice(name=cat, value=cat)
            for cat in categories if current.lower() in cat.lower()
        ]

    @category_group.command(name="remove", description="Удалить ивент из категории")
    @app_commands.describe(category_name="Название категории", event_name="Название ивента")
    async def remove_event_from_category(self, interaction: discord.Interaction, category_name: str, event_name: str):
        """Удаляет ивент из категории и перемещает его в 'Other'."""
        categories = self.load_categories()
        if category_name not in categories:
            await interaction.response.send_message(f"Категория `{category_name}` не найдена.", ephemeral=True)
            return
        if event_name not in categories[category_name]:
            await interaction.response.send_message(f"Ивент `{event_name}` не найден в категории `{category_name}`.", ephemeral=True)
            return

        categories[category_name].remove(event_name)
        # Добавляем в 'Other' если этой категории не существует
        if "Other" not in categories:
            categories["Other"] = []
        categories["Other"].append(event_name)

        self.save_categories(categories)
        await interaction.response.send_message(f"Ивент `{event_name}` удален из категории `{category_name}` и перемещен в `Other`.", ephemeral=True)

    @remove_event_from_category.autocomplete('category_name')
    async def remove_event_category_autocomplete(self, interaction: discord.Interaction, current: str):
        """Автодополнение для выбора категории при удалении ивента."""
        categories = self.load_categories()
        return [
            app_commands.Choice(name=cat, value=cat)
            for cat in categories if current.lower() in cat.lower() and cat != "Other"
        ]
    
    # Здесь мы не можем сделать автодополнение для event_name, так как это потребует выбора категории сначала

    @category_group.command(name="list", description="Показать список всех категорий и их ивентов")
    async def list_categories(self, interaction: discord.Interaction):
        """Выводит список всех категорий и содержащихся в них ивентов."""
        categories = self.load_categories()
        if not categories:
            await interaction.response.send_message("Категории еще не созданы.", ephemeral=True)
            return

        embed = discord.Embed(title="📋 Список категорий и ивентов", color=discord.Color.blue())
        
        # Сортируем категории, чтобы 'Other' была в конце
        sorted_categories = sorted(categories.items(), key=lambda item: item[0] == "Other")
        
        for category, events in sorted_categories:
            event_list = ", ".join(f"`{event}`" for event in events) if events else "Пусто"
            embed.add_field(name=f"📁 {category}", value=event_list, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(CategoryCog(bot))
