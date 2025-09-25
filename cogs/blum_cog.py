import discord
from discord import app_commands
from discord.ext import commands
import json

class BlumCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.blum_file = 'blum_list.json'
        self.blum_list = self._load_json()

    def _load_json(self):
        try:
            with open(self.blum_file, 'r', encoding='utf-8') as f:
                # Убедимся, что загружаем список ID в виде целых чисел
                return [int(user_id) for user_id in json.load(f)]
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return []

    def _save_json(self):
        with open(self.blum_file, 'w', encoding='utf-8') as f:
            json.dump(self.blum_list, f, ensure_ascii=False, indent=4)

    blum = app_commands.Group(name="blum", description="Команды для управления списком Blum")

    @blum.command(name="add", description="Добавить пользователя в список Blum.")
    @app_commands.describe(пользователь="Пользователь, которого нужно добавить")
    async def add(self, interaction: discord.Interaction, пользователь: discord.User):
        self.blum_list = self._load_json()
        if пользователь.id in self.blum_list:
            await interaction.response.send_message(f"Пользователь {пользователь.mention} уже в списке Blum.", ephemeral=True)
        else:
            self.blum_list.append(пользователь.id)
            self._save_json()
            await interaction.response.send_message(f"Пользователь {пользователь.mention} успешно добавлен в список Blum.", ephemeral=True)

    @blum.command(name="remove", description="Убрать пользователя из списка Blum.")
    @app_commands.describe(пользователь="Пользователь, которого нужно убрать")
    async def remove(self, interaction: discord.Interaction, пользователь: discord.User):
        self.blum_list = self._load_json()
        if пользователь.id not in self.blum_list:
            await interaction.response.send_message(f"Пользователя {пользователь.mention} нет в списке Blum.", ephemeral=True)
        else:
            self.blum_list.remove(пользователь.id)
            self._save_json()
            await interaction.response.send_message(f"Пользователь {пользователь.mention} успешно убран из списка Blum.", ephemeral=True)

    @blum.command(name="list", description="Показать всех пользователей в списке Blum.")
    async def list(self, interaction: discord.Interaction):
        self.blum_list = self._load_json()
        if not self.blum_list:
            await interaction.response.send_message("Список Blum пуст.", ephemeral=True)
            return

        description = "\n".join(f"- <@{user_id}>" for user_id in self.blum_list)
        embed = discord.Embed(title="Пользователи в списке Blum", description=description, color=discord.Color.purple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @blum.command(name="clear", description="Полностью очистить список Blum.")
    async def clear(self, interaction: discord.Interaction):
        self.blum_list = []
        self._save_json()
        await interaction.response.send_message("Список Blum был полностью очищен.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(BlumCog(bot))

