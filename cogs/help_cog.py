import discord
from discord import app_commands
from discord.ext import commands
import os

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Показывает список всех доступных команд.")
    @app_commands.guild_only()
    async def help_command(self, interaction: discord.Interaction):
        # Получаем ID роли администратора из переменных окружения
        admin_role_id = int(os.getenv('ADMIN_ROLE_ID'))
        admin_role = interaction.guild.get_role(admin_role_id)

        # Создаем эмбед для вывода
        embed = discord.Embed(
            title="Справка по командам бота",
            description="Ниже перечислены все доступные команды и их описание.",
            color=discord.Color.blue()
        )

        # --- Общедоступные команды ---
        embed.add_field(
            name="📜 Общедоступные команды",
            value=(
                "`/logs` - Общий лог активности за указанный период.\n"
                "`/log <категория>` - Лог активности для конкретной категории.\n"
                "`/night_log` - Лог ночной активности с бонусами.\n"
                "`/check <пользователь>` - Лог активности для указанного пользователя.\n"
                "`/makser` - Панель для создания суммарного отчета по баллам.\n"
                "`/eventstats` - Статистика по количеству и баллам проведенных ивентов.\n"
                "`/help` - Показывает это справочное сообщение."
            ),
            inline=False
        )
        
        # --- Команды для администраторов ---
        # Показываем упоминание роли, если она найдена
        role_mention = f" (требуется роль {admin_role.mention})" if admin_role else ""
        embed.add_field(
            name=f"⚙️ Команды для администраторов{role_mention}",
            value=(
                "**Категории:**\n"
                "`/category create <название>` - Создать новую категорию.\n"
                "`/category delete <название>` - Удалить существующую категорию.\n"
                "`/category add <название> <ивент>` - Добавить ивент в категорию.\n"
                "`/category remove <название> <ивент>` - Удалить ивент из категории.\n"
                "`/category list` - Показать список всех категорий и их ивентов.\n\n"
                "**Список Blum:**\n"
                "`/blum add <пользователь>` - Добавить пользователя в список Blum.\n"
                "`/blum remove <пользователь>` - Убрать пользователя из списка Blum.\n"
                "`/blum list` - Показать всех пользователей в списке Blum.\n"
                "`/blum clear` - Полностью очистить список Blum.\n\n"
                "**Прочее:**\n"
                "`/clear [количество]` - Очистить сообщения в текущем канале."
            ),
            inline=False
        )

        embed.set_footer(text="Бот для парсинга логов")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
