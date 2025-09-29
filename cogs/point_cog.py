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

class PointAddModal(discord.ui.Modal, title='Начисление баллов'):
    def __init__(self, cog_instance):
        super().__init__()
        self.cog = cog_instance

    end_time = discord.ui.TextInput(
        label="Время конца (ЧЧ:ММ ДД.ММ)",
        placeholder="Пример: 23:59 28.09",
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
            
            # Парсинг времени с использованием текущего года
            current_year = datetime.now().year
            moscow_tz = pytz.timezone('Europe/Moscow')
            end_dt = moscow_tz.localize(datetime.strptime(f"{self.end_time.value}.{current_year}", '%H:%M %d.%m.%Y'))

            entry = {
                "entry_id": str(uuid.uuid4()),
                "user_id": uid,
                "points": pts,
                "event_name": self.event_name.value,
                "end_time_iso": end_dt.isoformat(),
                "adder_id": interaction.user.id,
                "adder_name": interaction.user.display_name
            }

            self.cog.add_point_entry(entry)
            await interaction.response.send_message(
                f"Баллы успешно начислены пользователю <@{uid}>.\n"
                f"**Ивент:** {self.event_name.value}\n"
                f"**Баллы:** {pts}\n"
                f"**Добавил:** {interaction.user.mention}",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message("Ошибка: ID и баллы должны быть числами, а время в формате ЧЧ:ММ ДД.ММ.", ephemeral=True)
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

class PointEditModal(discord.ui.Modal, title='Изменить баллы за ивент'):
    def __init__(self, cog_instance, event_data, original_view):
        super().__init__()
        self.cog = cog_instance
        self.event_data = event_data
        self.original_view = original_view

        self.points_input = discord.ui.TextInput(
            label="Новое количество баллов",
            placeholder="Введите целое число",
            default=str(event_data.get('points', '0')),
            required=True
        )
        self.add_item(self.points_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_points = int(self.points_input.value)
            event_id = self.event_data['id']
            
            data = self.cog._load_points()

            if event_id.startswith('manual_'):
                entry_id = event_id.split('_', 1)[1]
                for entry in data:
                    if entry.get('entry_id') == entry_id:
                        entry['points'] = new_points
                        entry['editor_id'] = interaction.user.id
                        entry['editor_name'] = interaction.user.display_name
                        break
                self.cog._save_points(data)
                await interaction.response.send_message(f"Баллы для записи `{entry_id}` успешно изменены на {new_points}.", ephemeral=True)

            elif event_id.startswith('parsed_'):
                message_id = int(event_id.split('_', 1)[1])
                existing_entry = next((e for e in data if e.get('original_message_id') == message_id), None)

                if existing_entry:
                    existing_entry['points'] = new_points
                    existing_entry['editor_id'] = interaction.user.id
                    existing_entry['editor_name'] = interaction.user.display_name
                else:
                    new_entry = {
                        "entry_id": str(uuid.uuid4()),
                        "user_id": self.event_data['user_id'],
                        "points": new_points,
                        "event_name": self.event_data['event_name'], # <--- ИЗМЕНЕНИЕ ЗДЕСЬ
                        "end_time_iso": self.event_data['timestamp_dt'].isoformat(),
                        "adder_id": interaction.user.id,
                        "adder_name": interaction.user.display_name,
                        "original_message_id": message_id
                    }
                    data.append(new_entry)

                self.cog._save_points(data)
                await interaction.response.send_message(f"Баллы для ивента '{self.event_data['event_name']}' изменены на {new_points}. Создана/обновлена ручная запись.", ephemeral=True)
            
            for item in self.original_view.children:
                item.disabled = True
            await interaction.message.edit(view=self.original_view)

        except ValueError:
            await interaction.response.send_message("Ошибка: Баллы должны быть целым числом.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Произошла непредвиденная ошибка: {e}", ephemeral=True)

class PointEditSelect(discord.ui.Select):
    def __init__(self, cog_instance, events):
        self.cog = cog_instance
        self.events_map = {event['id']: event for event in events}
        
        options = []
        if not events:
            options.append(discord.SelectOption(label="Не найдено недавних ивентов для этого пользователя.", value="disabled"))
        else:
            for event in events:
                timestamp = event['timestamp_dt']
                label = f"{event['points']}б | {event['event_name']}"
                description = f"Дата: {timestamp.strftime('%d.%m.%Y %H:%M')}"
                options.append(discord.SelectOption(label=label, value=event['id'], description=description))

        super().__init__(
            placeholder="Выберите ивент для редактирования...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=(not events)
        )

    async def callback(self, interaction: discord.Interaction):
        selected_id = self.values[0]
        event_data = self.events_map.get(selected_id)
        
        if not event_data:
            await interaction.response.send_message("Не удалось найти данные для выбранного ивента.", ephemeral=True)
            return

        modal = PointEditModal(self.cog, event_data, self.view)
        await interaction.response.send_modal(modal)

class PointEditView(discord.ui.View):
    def __init__(self, cog_instance, events):
        super().__init__(timeout=300)
        self.add_item(PointEditSelect(cog_instance, events))


class PointCog(commands.Cog, name="Points"):
    def __init__(self, bot):
        self.bot = bot
        self.data_path = getattr(self.bot, 'data_path', '.')
        self.points_file = os.path.join(self.data_path, 'manual_points.json')
        self.moscow_tz = pytz.timezone('Europe/Moscow')

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

    async def _get_user_recent_events(self, interaction: discord.Interaction, user_id: int, count: int = 10):
        all_manual_points = self._load_points()
        user_manual_events = [
            {
                'id': f"manual_{e['entry_id']}",
                'user_id': e['user_id'],
                'points': e['points'],
                'event_name': e['event_name'],
                'timestamp_dt': datetime.fromisoformat(e['end_time_iso']),
                'source': 'manual',
                'original_message_id': e.get('original_message_id')
            } for e in all_manual_points if e['user_id'] == user_id
        ]
        
        edited_message_ids = {e['original_message_id'] for e in user_manual_events if e['original_message_id']}

        user_parsed_events = []
        parse_channel_id = int(os.getenv("PARSE_CHANNEL_ID"))
        channel = self.bot.get_channel(parse_channel_id)
        if not channel:
            return []

        async for message in channel.history(limit=500):
            if message.id in edited_message_ids:
                continue

            if not message.embeds: continue
            for embed in message.embeds:
                if embed.title != "Отчет о проведенном ивенте": continue
                
                if embed.description:
                    match = re.search(r'<@(\d+)>', embed.description)
                    if not match or int(match.group(1)) != user_id:
                        continue
                else:
                    continue

                data = {
                    'id': f"parsed_{message.id}",
                    'user_id': user_id,
                    'points': 0,
                    'event_name': 'Без названия',
                    'timestamp_dt': message.created_at.astimezone(self.moscow_tz),
                    'source': 'parsed',
                    'message_id': message.id
                }

                for field in embed.fields:
                    clean_field_name = field.name.lower().replace('>', '').strip()
                    if clean_field_name == 'получено':
                        try:
                            data['points'] = int(re.search(r'\d+', field.value).group())
                        except:
                            data['points'] = 0
                    elif clean_field_name == 'ивент':
                        data['event_name'] = field.value.replace('`', '').strip()
                
                user_parsed_events.append(data)
        
        all_events = user_manual_events + user_parsed_events
        all_events.sort(key=lambda x: x['timestamp_dt'], reverse=True)
        
        return all_events[:count]

    point_group = app_commands.Group(name="point", description="Команды для ручного управления баллами")

    @point_group.command(name="add", description="Начислить баллы пользователю вручную.")
    @app_commands.guild_only()
    @is_admin()
    async def add_points(self, interaction: discord.Interaction):
        modal = PointAddModal(self)
        await interaction.response.send_modal(modal)

    @point_group.command(name="edit", description="Изменить баллы за один из последних 10 ивентов пользователя.")
    @app_commands.describe(пользователь="Пользователь, чьи ивенты нужно показать.")
    @app_commands.guild_only()
    @is_admin()
    async def edit_points(self, interaction: discord.Interaction, пользователь: discord.User):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            recent_events = await self._get_user_recent_events(interaction, пользователь.id, count=10)
            
            if not recent_events:
                await interaction.followup.send(f"Не найдено недавних ивентов для пользователя {пользователь.mention}.", ephemeral=True)
                return

            view = PointEditView(self, recent_events)
            await interaction.followup.send(f"Выберите ивент для редактирования баллов пользователя {пользователь.mention} (показаны последние 10):", view=view, ephemeral=True)

        except Exception as e:
            print(f"Error in /point edit: {e}")
            await interaction.followup.send(f"Произошла непредвиденная ошибка: {e}", ephemeral=True)

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
                if current_user_id is not None and user_entries_str:
                    embed.add_field(name=f"Пользователь: <@{current_user_id}>", value=user_entries_str, inline=False)
                current_user_id = entry['user_id']
                user_entries_str = ""

            end_dt = datetime.fromisoformat(entry['end_time_iso'])
            
            adder_info = ""
            if 'editor_id' in entry:
                adder_info = f"Изменил: <@{entry['editor_id']}>"
            elif 'adder_id' in entry:
                 adder_info = f"Добавил: <@{entry['adder_id']}>"
            else:
                adder_info = f"Добавил: {entry.get('adder_name', 'Неизвестно')}"
            
            user_entries_str += (f"- **{entry['points']} баллов** | `{entry['event_name']}` "
                                 f"| {end_dt.strftime('%H:%M %d.%m.%Y')} | {adder_info}\n")
        
        if current_user_id is not None and user_entries_str:
            embed.add_field(name=f"Пользователь: <@{current_user_id}>", value=user_entries_str, inline=False)

        if not embed.fields:
             await interaction.response.send_message("Список вручную начисленных баллов пуст.", ephemeral=True)
             return

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    cog = PointCog(bot)
    bot.tree.add_command(cog.point_group)