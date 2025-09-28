import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import uuid
from datetime import datetime, timedelta
import pytz
import re
from main import is_admin

# --- UI компонент для добавления баллов к конкретному ивенту ---

class AddPointsToEventModal(discord.ui.Modal, title='Добавить баллы к ивенту'):
    """Модальное окно, запрашивающее только количество баллов для выбранного ивента."""
    def __init__(self, cog_instance, event_data):
        super().__init__()
        self.cog = cog_instance
        self.event_data = event_data
        
        # Поле для отображения названия ивента (не для редактирования)
        self.event_name_display = discord.ui.TextInput(
            label="Ивент",
            default=self.event_data['event_name'],
            disabled=True,
            style=discord.TextStyle.short
        )
        self.add_item(self.event_name_display)

        # Поле для ввода баллов
        self.points = discord.ui.TextInput(
            label="Баллы (целое число)",
            placeholder="Введите количество баллов для начисления",
            required=True
        )
        self.add_item(self.points)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            pts = int(self.points.value)
            if pts <= 0:
                await interaction.response.send_message("Ошибка: Количество баллов должно быть положительным числом.", ephemeral=True)
                return

            end_dt = self.event_data['timestamp_dt']

            entry = {
                "entry_id": str(uuid.uuid4()),
                "user_id": self.event_data['user_id'],
                "points": pts,
                "event_name": self.event_data['event_name'],
                "end_time_iso": end_dt.isoformat(),
                "adder_id": interaction.user.id,
                "adder_name": interaction.user.display_name,
                "source_message_id": self.event_data['message_id'] # Ссылка на исходное сообщение
            }

            self.cog.add_point_entry(entry)
            await interaction.response.send_message(
                f"Баллы ({pts}) успешно начислены за ивент '{self.event_data['event_name']}' пользователю <@{self.event_data['user_id']}>.",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message("Ошибка: Баллы должны быть целым числом.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Произошла непредвиденная ошибка: {e}", ephemeral=True)
        
# --- UI компоненты для выбора ивента с 0 баллов ---

class ZeroPointEventSelect(discord.ui.Select):
    """Выпадающий список для выбора ивента с 0 баллов."""
    def __init__(self, cog_instance, zero_point_events):
        self.cog = cog_instance
        # Создаем словарь для быстрого доступа к данным ивента по ID сообщения
        self.events_map = {str(event['message_id']): event for event in zero_point_events}
        
        options = []
        if not zero_point_events:
            options.append(discord.SelectOption(label="Ивенты с 0 баллов не найдены.", value="disabled"))
        else:
            for event in zero_point_events: # Уже отфильтровано до 10
                end_dt = event['timestamp_dt']
                label = f"{event['event_name']}"
                description = f"Время: {end_dt.strftime('%H:%M %d.%m.%Y')}"
                options.append(discord.SelectOption(label=label, value=str(event['message_id']), description=description))

        super().__init__(
            placeholder="Выберите ивент для начисления баллов...",
            min_values=1,
            max_values=1,
            options=options,
            disabled=(not zero_point_events)
        )

    async def callback(self, interaction: discord.Interaction):
        selected_event_id = self.values[0]
        event_data = self.events_map[selected_event_id]
        
        modal = AddPointsToEventModal(self.cog, event_data)
        await interaction.response.send_modal(modal)

class ZeroPointEventView(discord.ui.View):
    """Контейнер для выпадающего списка."""
    def __init__(self, cog_instance, zero_point_events):
        super().__init__(timeout=600)
        self.add_item(ZeroPointEventSelect(cog_instance, zero_point_events))
        
# --- UI компоненты для удаления записей ---

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
        super().__init__(
            placeholder="Выберите запись для удаления...", min_values=1, max_values=1, options=options, disabled=(not entries)
        )

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

    @point_group.command(name="add", description="Найти последние 10 ивентов пользователя с 0 баллов для начисления.")
    @app_commands.describe(пользователь="Пользователь, чьи ивенты нужно найти")
    @app_commands.guild_only()
    @is_admin()
    async def add_points(self, interaction: discord.Interaction, пользователь: discord.User):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            parse_channel_id = int(os.getenv("PARSE_CHANNEL_ID"))
            channel = self.bot.get_channel(parse_channel_id)
            if not channel:
                await interaction.followup.send("Ошибка: Не удалось найти канал для парсинга логов.", ephemeral=True)
                return

            manual_points = self._load_points()
            processed_message_ids = {entry.get('source_message_id') for entry in manual_points if entry.get('source_message_id')}

            user_zero_point_events = []
            # Сканируем последние 1000 сообщений, этого должно быть достаточно
            async for message in channel.history(limit=1000):
                if not message.embeds or message.id in processed_message_ids:
                    continue
                
                for embed in message.embeds:
                    if embed.title != "Отчет о проведенном ивенте":
                        continue
                    
                    # Проверяем ID пользователя в первую очередь
                    user_id_from_embed = None
                    user_info_source = None
                    if embed.description and "<@" in embed.description:
                        user_info_source = embed.description
                    else:
                        for field in embed.fields:
                            if "<@" in field.value:
                                user_info_source = field.value
                                break
                    if user_info_source:
                        match = re.search(r'<@(\d+)>', user_info_source)
                        if match:
                            user_id_from_embed = int(match.group(1))

                    if user_id_from_embed != пользователь.id:
                        continue

                    # Проверяем баллы
                    points = -1 
                    for field in embed.fields:
                        if 'получено' in field.name.lower():
                            try: points = int(re.search(r'\d+', field.value).group())
                            except: points = 0
                            break
                    
                    if points == 0:
                        data = {
                            'message_id': message.id,
                            'user_id': user_id_from_embed,
                            'user_nick': 'N/A',
                            'event_name': 'Без названия',
                            'timestamp_dt': message.created_at.astimezone(pytz.timezone('Europe/Moscow'))
                        }
                        if user_info_source:
                            nick_part = user_info_source[match.end():].strip()
                            data['user_nick'] = nick_part.replace('`', '').strip() or 'N/A'
                        
                        for field in embed.fields:
                            if 'ивент' in field.name.lower():
                                data['event_name'] = field.value.replace('`', '').strip()
                        
                        user_zero_point_events.append(data)
                        break # Переходим к следующему сообщению

            # Сортируем по дате и берем последние 10
            user_zero_point_events.sort(key=lambda x: x['timestamp_dt'], reverse=True)
            events_to_show = user_zero_point_events[:10]

            if not events_to_show:
                await interaction.followup.send(f"Не найдено необработанных ивентов с 0 баллов для {пользователь.mention} за последнее время.", ephemeral=True)
                return

            view = ZeroPointEventView(self, events_to_show)
            await interaction.followup.send(f"Найдены ивенты с 0 баллов для {пользователь.mention} (показаны последние 10). Выберите один:", view=view, ephemeral=True)

        except Exception as e:
            print(f"Ошибка в /point add (user): {e}")
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
                if current_user_id is not None:
                    embed.add_field(name=f"Пользователь: <@{current_user_id}>", value=user_entries_str, inline=False)
                current_user_id = entry['user_id']
                user_entries_str = ""

            end_dt = datetime.fromisoformat(entry['end_time_iso'])
            adder_id = entry.get('adder_id')
            if adder_id: adder_info = f"<@{adder_id}>"
            else: adder_info = entry.get('adder_name', 'Неизвестно')
            
            user_entries_str += (f"- **{entry['points']} баллов** | `{entry['event_name']}` "
                                 f"| {end_dt.strftime('%H:%M %d.%m.%Y')} | Добавил: {adder_info}\n")
        
        if current_user_id is not None:
            embed.add_field(name=f"Пользователь: <@{current_user_id}>", value=user_entries_str, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    cog = PointCog(bot)
    bot.tree.add_command(cog.point_group)

