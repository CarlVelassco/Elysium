import discord
from discord import app_commands
from discord.ext import commands

class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help", description="Показывает список и описание всех команд.")
    @app_commands.guild_only()
    async def help_command(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Справка по командам бота",
            description="Вот список всех доступных команд и их описание.",
            color=discord.Color.blue()
        )

        # Открытые команды
        embed.add_field(
            name="Основные команды (для всех)",
            value=(
                "`/help` - Показывает это сообщение.\n"
                "`/logs` - Создает общий лог активности за указанный период.\n"
                "`/log <категория>` - Создает лог активности для конкретной категории.\n"
                "`/night_log` - Создает лог ночной активности.\n"
                "`/check <пользователь>` - Показывает лог активности для конкретного пользователя.\n"
                "`/makser` - Открывает меню для создания сводного отчета по баллам.\n"
                "`/eventstats` - Показывает статистику по количеству и длительности ивентов."
            ),
            inline=False
        )

        # Команды администратора
        embed.add_field(
            name="Команды администратора (требуется специальная роль)",
            value=(
                "`/category create <название>` - Создать новую категорию.\n"
                "`/category delete <название>` - Удалить категорию.\n"
                "`/category add <категория> <ивент>` - Добавить ивент в категорию.\n"
                "`/category remove <категория> <ивент>` - Удалить ивент из категории.\n"
                "`/category list` - Показать все категории и их ивенты.\n"
                "`/blum add <пользователь>` - Добавить пользователя в список Blum (ночной бонус x2).\n"
                "`/blum remove <пользователь>` - Убрать пользователя из списка Blum.\n"
                "`/blum list` - Показать список Blum.\n"
                "`/blum clear` - Очистить список Blum.\n"
                "`/point add` - Открыть форму для ручного начисления баллов.\n"
                "`/point edit <пользователь>` - Назначить баллы для ивента с 0 баллов.\n"
                "`/point remove` - Удалить вручную начисленные баллы.\n"
                "`/point list` - Показать список вручную начисленных баллов.\n"
                "`/clear [количество]` - Очищает сообщения в текущем канале."
            ),
            inline=False
        )
        
        embed.set_footer(text="Для команд с датами, после их вызова появится окно для ввода периода.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))

