import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import uuid
from datetime import datetime
import pytz
from main import is_admin

class PointAddModal(discord.ui.Modal, title='Начисление баллов'):
    def __init__(self, cog_instance):
        super().__init__()
        self.cog = cog_instance

    end_time = discord.ui.TextInput(
        label="Время конца (ЧЧ:ММ ДД.ММ.ГГГГ)",
        placeholder=f"Пример: 23:59 28.09.{datetime.now().year}",
        required=True
    )
    user_id = discord.ui.TextInput(
        label="ID пользователя",
        placeholder="Пример: 426045378907865119",
        required=True
    )
    points = discord.ui.TextInput(
        label="Баллы (целое число)",
        placeholder="Пример: 50",
        required=True
    )
    event_name = discord.ui.TextInput(
        label="Название ивента",
        placeholder="Пример: Ручное начисление",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Валидация данных
            uid = int(self.user_id.value)
            pts = int(self.points.value)
            
            # Парсинг времени с годом
            moscow_tz = pytz.timezone('Europe/Moscow')
            end_dt = moscow_tz.localize(datetime.strptime(self.end_time.value, '%H:%M %d.%m.%Y'))

            entry = {
                "entry_id": str(uuid.uuid4()),
                "user_id": uid,
                "points": pts,
                "event_name": self.event_name.value,
                "end_time_iso": end_dt.isoformat()
            }

            self.cog.add_point_entry(entry)
            await interaction.response.send_message(
                f"Баллы успешно начислены пользователю <@{uid}>.\n"
                f"**Ивент:** {self.event_name.value}\n"
                f"**Баллы:** {pts}",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message("Ошибка: ID и баллы должны быть числами, а время в формате ЧЧ:ММ ДД.ММ.ГГГГ.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Произошла непредвиденная ошибка: {e}", ephemeral=True)

class PointRemoveSelect(discord.ui.Select):
    def __init__(self, cog_instance, entries):
        self.cog = cog_instance
        
        options = []
        if not entries:
            options.append(discord.SelectOption(label="Записей для удаления нет.", value="disabled"))
        else:
            # Ограничиваем количество опций до 25 (максимум для Select)
            for entry in entries[:25]:
                end_dt = datetime.fromisoformat(entry['end_time_iso'])
                label = f"ID: {entry['user_id']} | {entry['points']}б | {entry['event_name']}"
                description = f"Время: {end_dt.strftime('%H:%M %d.%m.%Y')}"
                options.append(discord.SelectOption(label=label, value=entry['entry_id'], description=description))

        super().__init__(
            placeholder="Выберите запись для удаления...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=(not entries)
        )

    async def callback(self, interaction: discord.Interaction):
        entry_id = self.values[0]
        self.cog.remove_point_entry(entry_id)
        await interaction.response.send_message(f"Запись с ID `{entry_id}` была успешно удалена.", ephemeral=True)
        # Отключаем select после использования
        self.disabled = True
        await interaction.message.edit(view=self.view)

class PointRemoveView(discord.ui.View):
    def __init__(self, cog_instance, entries):
        super().__init__(timeout=300)
        self.add_item(PointRemoveSelect(cog_instance, entries))

class PointCog(commands.Cog, name="Points"):
    def __init__(self, bot):
        self.bot = bot
        # Используем централизованный путь к данным, который указывает на постоянное хранилище
        self.data_path = getattr(self.bot, 'data_path', '.')
        self.points_file = os.path.join(self.data_path, 'manual_points.json')

    def _load_points(self):
        try:
            with open(self.points_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_points(self, data):
        with open(self.points_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def add_point_entry(self, entry):
        data = self._load_points()
        data.append(entry)
        self._save_points(data)
        
    def remove_point_entry(self, entry_id):
        data = self._load_points()
        data = [e for e in data if e.get('entry_id') != entry_id]
        self._save_points(data)

    point_group = app_commands.Group(name="point", description="Команды для ручного управления баллами")

    @point_group.command(name="add", description="Начислить баллы пользователю вручную.")
    @app_commands.guild_only()
    @is_admin()
    async def add_points(self, interaction: discord.Interaction):
        modal = PointAddModal(self)
        await interaction.response.send_modal(modal)
    
    @point_group.command(name="remove", description="Удалить вручную начисленные баллы.")
    @app_commands.guild_only()
    @is_admin()
    async def remove_points(self, interaction: discord.Interaction):
        entries = self._load_points()
        entries.sort(key=lambda x: x['end_time_iso'], reverse=True) # Сортируем, чтобы показать самые свежие
        view = PointRemoveView(self, entries)
        await interaction.response.send_message("Выберите запись для удаления (показаны последние 25):", view=view, ephemeral=True)

    @point_group.command(name="list", description="Показать список всех вручную начисленных баллов.")
    @app_commands.guild_only()
    @is_admin()
    async def list_points(self, interaction: discord.Interaction):
        entries = self._load_points()
        if not entries:
            await interaction.response.send_message("Список вручную начисленных баллов пуст.", ephemeral=True)
            return
        
        entries.sort(key=lambda x: (x['user_id'], x['end_time_iso']))

        embed = discord.Embed(title="Вручную начисленные баллы", color=discord.Color.orange())
        
        current_user_id = None
        user_entries_str = ""
        
        for entry in entries:
            if entry['user_id'] != current_user_id:
                if current_user_id is not None:
                    embed.add_field(name=f"Пользователь: <@{current_user_id}>", value=user_entries_str, inline=False)
                current_user_id = entry['user_id']
                user_entries_str = ""

            end_dt = datetime.fromisoformat(entry['end_time_iso'])
            user_entries_str += (f"- **{entry['points']} баллов** | `{entry['event_name']}` "
                                 f"| {end_dt.strftime('%H:%M %d.%m.%Y')} | ID: `{entry['entry_id']}`\n")
        
        if current_user_id is not None:
            embed.add_field(name=f"Пользователь: <@{current_user_id}>", value=user_entries_str, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    cog = PointCog(bot)
    bot.tree.add_command(cog.point_group)


