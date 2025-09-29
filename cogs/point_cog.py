import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import uuid
from datetime import datetime
import pytz
import re
from main import is_admin

# --- UI для /point add (создание новой записи) ---
class PointAddModal(discord.ui.Modal, title='Начисление баллов'):
    def __init__(self, cog_instance):
        super().__init__()
        self.cog = cog_instance

    end_time = discord.ui.TextInput(label="Время конца (ЧЧ:ММ ДД.ММ)", placeholder="Пример: 23:59 28.09", required=True)
    user_id = discord.ui.TextInput(label="ID пользователя", placeholder="Пример: 426045378907865119", required=True)
    points = discord.ui.TextInput(label="Баллы (целое число)", placeholder="Пример: 50", required=True)
    event_name = discord.ui.TextInput(label="Название ивента", placeholder="Пример: Ручное начисление", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(self.user_id.value)
            pts = int(self.points.value)
            current_year = datetime.now().year
            moscow_tz = pytz.timezone('Europe/Moscow')
            end_dt = moscow_tz.localize(datetime.strptime(f"{self.end_time.value}.{current_year}", '%H:%M %d.%m.%Y'))

            entry = {
                "entry_id": str(uuid.uuid4()), "user_id": uid, "points": pts, "event_name": self.event_name.value,
                "end_time_iso": end_dt.isoformat(), "adder_id": interaction.user.id, "adder_name": interaction.user.display_name
            }

            self.cog.add_point_entry(entry)
            await interaction.response.send_message(
                f"Баллы успешно начислены пользователю <@{uid}>.\n"
                f"**Ивент:** {self.event_name.value}\n**Баллы:** {pts}\n"
                f"**Добавил:** {interaction.user.mention}", ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message("Ошибка: ID и баллы должны быть числами, а время в формате ЧЧ:ММ ДД.ММ.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Произошла непредвиденная ошибка: {e}", ephemeral=True)

# --- UI для /point edit (присвоение баллов ивенту с 0 баллов) ---
class EditZeroPointEventModal(discord.ui.Modal):
    def __init__(self, cog_instance, event_data):
        title = f"Баллы для: {event_data['event_name']}"
        if len(title) > 45: title = title[:42] + "..."
        super().__init__(title=title)
        
        self.cog = cog_instance
        self.event_data = event_data

        self.event_name_display = discord.ui.TextInput(label="Ивент", default=event_data['event_name'], disabled=True)
        self.add_item(self.event_name_display)

        self.points_input = discord.ui.TextInput(label="Количество баллов для начисления", placeholder="Введите целое число", required=True)
        self.add_item(self.points_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_points = int(self.points_input.value)
            if new_points <= 0:
                await interaction.response.send_message("Ошибка: Количество баллов должно быть положительным.", ephemeral=True)
                return

            entry = {
                "entry_id": str(uuid.uuid4()), "user_id": self.event_data['user_id'], "points": new_points,
                "event_name": self.event_data['event_name'], "end_time_iso": self.event_data['timestamp_dt'].isoformat(),
                "adder_id": interaction.user.id, "adder_name": interaction.user.display_name,
                "source_message_id": self.event_data['message_id']
            }
            self.cog.add_point_entry(entry)
            await interaction.response.send_message(f"Баллы ({new_points}) успешно начислены за ивент '{self.event_data['event_name']}'.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Ошибка: Баллы должны быть целым числом.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Произошла ошибка: {e}", ephemeral=True)

class EditZeroPointEventSelect(discord.ui.Select):
    def __init__(self, cog_instance, entries):
        self.cog = cog_instance
        self.events_map = {str(entry['message_id']): entry for entry in entries}
        
        options = []
        if not entries:
            options.append(discord.SelectOption(label="Ивенты с 0 баллов не найдены.", value="disabled"))
        else:
            for entry in entries:
                end_dt = entry['timestamp_dt']
                label = f"{entry['event_name']}"
                if len(label) > 100: label = label[:97] + "..."
                description = f"Время: {end_dt.strftime('%H:%M %d.%m.%Y')}"
                options.append(discord.SelectOption(label=label, value=str(entry['message_id']), description=description))

        super().__init__(placeholder="Выберите ивент для начисления баллов...", options=options, disabled=(not entries))

    async def callback(self, interaction: discord.Interaction):
        entry = self.events_map[self.values[0]]
        modal = EditZeroPointEventModal(self.cog, entry)
        await interaction.response.send_modal(modal)

class EditZeroPointEventView(discord.ui.View):
    def __init__(self, cog_instance, entries):
        super().__init__(timeout=300)
        self.add_item(EditZeroPointEventSelect(cog_instance, entries))

# --- UI для /point remove ---
class PointRemoveSelect(discord.ui.Select):
    def __init__(self, cog_instance, entries):
        self.cog = cog_instance
        options = []
        if not entries:
            options.append(discord.SelectOption(label="Записей для удаления нет.", value="disabled"))
        else:
            for entry in entries[:25]:
                end_dt = datetime.fromisoformat(entry['end_time_iso'])
                label = f"ID: {entry['user_id']} | {entry['points']}б | {entry['event_name']}"
                description = f"Время: {end_dt.strftime('%H:%M %d.%m.%Y')}"
                options.append(discord.SelectOption(label=label, value=entry['entry_id'], description=description))
        super().__init__(placeholder="Выберите запись для удаления...", options=options, disabled=(not entries))

    async def callback(self, interaction: discord.Interaction):
        entry_id = self.values[0]
        self.cog.remove_point_entry(entry_id)
        await interaction.response.send_message(f"Запись с ID `{entry_id}` была успешно удалена.", ephemeral=True)
        self.disabled = True
        await interaction.message.edit(view=self.view)

class PointRemoveView(discord.ui.View):
    def __init__(self, cog_instance, entries):
        super().__init__(timeout=300)
        self.add_item(PointRemoveSelect(cog_instance, entries))

# --- Основной класс кога ---
class PointCog(commands.Cog, name="Points"):
    def __init__(self, bot):
        self.bot = bot
        self.data_path = getattr(self.bot, 'data_path', '.')
        self.points_file = os.path.join(self.data_path, 'manual_points.json')

    def _load_points(self):
        try:
            with open(self.points_file, 'r', encoding='utf-8') as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): return []

    def _save_points(self, data):
        with open(self.points_file, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

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

    @point_group.command(name="edit", description="Присвоить баллы одному из ивентов пользователя с 0 баллов.")
    @app_commands.describe(пользователь="Пользователь, чьи ивенты нужно найти")
    @app_commands.guild_only()
    @is_admin()
    async def edit_points(self, interaction: discord.Interaction, пользователь: discord.User):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            parse_channel_id = int(os.getenv("PARSE_CHANNEL_ID"))
            channel = self.bot.get_channel(parse_channel_id)
            if not channel:
                await interaction.followup.send("Ошибка: Не удалось найти канал для парсинга.", ephemeral=True)
                return

            manual_points = self._load_points()
            processed_message_ids = {entry.get('source_message_id') for entry in manual_points if entry.get('source_message_id')}

            zero_point_events = []
            async for message in channel.history(limit=1000):
                if not message.embeds or message.id in processed_message_ids: continue
                for embed in message.embeds:
                    if embed.title != "Отчет о проведенном ивенте": continue
                    
                    user_id_from_embed = None
                    if embed.description and "<@" in embed.description:
                        match = re.search(r'<@(\d+)>', embed.description)
                        if match: user_id_from_embed = int(match.group(1))

                    if user_id_from_embed == пользователь.id:
                        points = -1
                        for field in embed.fields:
                            clean_name = field.name.lower().replace('>', '').strip()
                            if clean_name == 'получено':
                                try: points = int(re.search(r'\d+', field.value).group())
                                except: points = 0
                                break
                        
                        if points == 0:
                            data = {
                                'message_id': message.id, 'user_id': user_id_from_embed, 'event_name': 'Без названия',
                                'timestamp_dt': message.created_at.astimezone(pytz.timezone('Europe/Moscow'))
                            }
                            for field in embed.fields:
                                clean_name = field.name.lower().replace('>', '').strip()
                                if clean_name == 'ивент':
                                    data['event_name'] = field.value.replace('`', '').strip() or 'Без названия'
                                    break
                            zero_point_events.append(data)
                            break
            
            zero_point_events.sort(key=lambda x: x['timestamp_dt'], reverse=True)
            events_to_show = zero_point_events[:10]

            if not events_to_show:
                await interaction.followup.send(f"Не найдено необработанных ивентов с 0 баллов для {пользователь.mention}.", ephemeral=True)
                return

            view = EditZeroPointEventView(self, events_to_show)
            await interaction.followup.send(f"Выберите ивент для начисления баллов (показаны последние 10):", view=view, ephemeral=True)
        except Exception as e:
            print(f"Ошибка в /point edit: {e}")
            await interaction.followup.send("Произошла непредвиденная ошибка.", ephemeral=True)

    @point_group.command(name="remove", description="Удалить вручную начисленные баллы.")
    @app_commands.guild_only()
    @is_admin()
    async def remove_points(self, interaction: discord.Interaction):
        entries = self._load_points()
        entries.sort(key=lambda x: x['end_time_iso'], reverse=True)
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
            adder_id = entry.get('adder_id')
            adder_info = f"<@{adder_id}>" if adder_id else entry.get('adder_name', 'Неизвестно')
            
            user_entries_str += (f"- **{entry['points']} баллов** | `{entry['event_name']}` "
                                 f"| {end_dt.strftime('%H:%M %d.%m.%Y')} | Добавил: {adder_info}\n")
        
        if current_user_id is not None:
            embed.add_field(name=f"Пользователь: <@{current_user_id}>", value=user_entries_str, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    cog = PointCog(bot)
    bot.tree.add_command(cog.point_group)

