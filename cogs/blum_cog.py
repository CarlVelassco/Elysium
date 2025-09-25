import discord
from discord.ext import commands
from discord import app_commands
import json

class BlumCog(commands.Cog):
    """Ког для управления списком пользователей Blum."""
    def __init__(self, bot):
        self.bot = bot
        self.blum_file = 'blum_list.json'

    def load_blum_list(self):
        """Загружает список Blum из JSON файла."""
        with open(self.blum_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_blum_list(self, data):
        """Сохраняет список Blum в JSON файл."""
        with open(self.blum_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    blum_group = app_commands.Group(name="blum", description="Команды для управления списком Blum")

    @blum_group.command(name="add", description="Добавить пользователя в список Blum")
    @app_commands.describe(user="Пользователь, которого нужно добавить")
    async def add_user(self, interaction: discord.Interaction, user: discord.User):
        """Добавляет пользователя в список Blum."""
        blum_list = self.load_blum_list()
        if user.id in blum_list:
            await interaction.response.send_message(f"Пользователь {user.mention} уже в списке Blum.", ephemeral=True)
            return
        blum_list.append(user.id)
        self.save_blum_list(blum_list)
        await interaction.response.send_message(f"Пользователь {user.mention} успешно добавлен в список Blum.", ephemeral=True)

    @blum_group.command(name="remove", description="Удалить пользователя из списка Blum")
    @app_commands.describe(user="Пользователь, которого нужно удалить")
    async def remove_user(self, interaction: discord.Interaction, user: discord.User):
        """Удаляет пользователя из списка Blum."""
        blum_list = self.load_blum_list()
        if user.id not in blum_list:
            await interaction.response.send_message(f"Пользователь {user.mention} не найден в списке Blum.", ephemeral=True)
            return
        blum_list.remove(user.id)
        self.save_blum_list(blum_list)
        await interaction.response.send_message(f"Пользователь {user.mention} удален из списка Blum.", ephemeral=True)

    @blum_group.command(name="list", description="Показать всех пользователей в списке Blum")
    async def list_users(self, interaction: discord.Interaction):
        """Выводит список всех пользователей Blum."""
        blum_list = self.load_blum_list()
        if not blum_list:
            await interaction.response.send_message("Список Blum пуст.", ephemeral=True)
            return

        description = []
        for user_id in blum_list:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if user:
                description.append(f"- {user.mention} (`{user.name}`)")
            else:
                description.append(f"- <@{user_id}> (Пользователь не найден)")

        embed = discord.Embed(
            title="🌙 Список пользователей Blum",
            description="\n".join(description),
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @blum_group.command(name="clear", description="Полностью очистить список Blum")
    async def clear_list(self, interaction: discord.Interaction):
        """Очищает список Blum."""
        self.save_blum_list([])
        await interaction.response.send_message("Список Blum был полностью очищен.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(BlumCog(bot))
