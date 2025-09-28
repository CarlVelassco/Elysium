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

# --- UI для /point add (добавление баллов к существующему ивенту) ---

class AddPointsToExistingModal(discord.ui.Modal, title="Добавить баллы к ивенту"):
    def __init__(self, cog_instance, event_data):
        super().__init__()
        
        self.cog = cog_instance
        self.event_data = event_data
        
        self.event_name_display = discord.ui.TextInput(
            label="Ивент", default=self.event_data['event_name'], disabled=True
        )
        self.add_item(self.event_name_display)

        self.points_to_add = discord.ui.TextInput(
            label="Баллы для добавления", placeholder="Введите количество баллов", required=True
        )
        self.add_item(self.points_to_add)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            pts = int(self.points_to_add.value)
            if pts <= 0:
                await interaction.response.send_message("Ошибка: Количество баллов должно быть > 0.", ephemeral=True)
                return

            entry = {
                "entry_id": str(uuid.uuid4()),
                "user_id": self.event_data['user_id'],
                "points": pts,
                "event_name": f"Доп. баллы: {self.event_data['event_name']}",
                "end_time_iso": self.event_data['timestamp_dt'].isoformat(),
                "adder_id": interaction.user.id,
                "adder_name": interaction.user.display_name,
                "source_message_id": self.event_data.get('message_id')
            }
            self.cog.add_point_entry(entry)
            await interaction.response.send_message(f"Добавлено {pts} баллов к ивенту '{self.event_data['event_name']}'.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Ошибка: Баллы должны быть числом.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Произошла ошибка: {e}", ephemeral=True)

class SelectUserEventSelect(discord.ui.Select):
    def __init__(self, cog_instance, user_events):
        self.cog = cog_instance
        self.events_map = {event['unique_id']: event for event in user_events}
        
        options = []
        if not user_events:
            options.append(discord.SelectOption(label="Ивенты не найдены.", value="disabled"))
        else:
            for event in user_events:
                label = event['event_name']
                if len(label) > 100: label = label[:97] + "..."
                description = f"Время: {event['timestamp_dt'].strftime('%H:%M %d.%m.%Y')}"
                options.append(discord.SelectOption(label=label, value=event['unique_id'], description=description))

        super().__init__(placeholder="Выберите ивент для добавления баллов...", options=options, disabled=(not user_events))

    async def callback(self, interaction: discord.Interaction):
        if self.view.is_finished():
            try:
                await interaction.response.send_message("Время для выбора истекло.", ephemeral=True, delete_after=5)
            except discord.errors.InteractionResponded:
                pass 
            return
            
        try:
            event_data = self.events_map[self.values[0]]
            modal = AddPointsToExistingModal(self.cog, event_data)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"Ошибка в колбэке SelectUserEventSelect: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("Произошла ошибка при обработке вашего выбора.", ephemeral=True)

class SelectUserEventView(discord.ui.View):
    def __init__(self, cog_instance, user_events):
        super().__init__(timeout=600)
        self.message = None
        self.add_item(SelectUserEventSelect(cog_instance, user_events))
        
    async def on_timeout(self):
        if self.message:
            for item in self.children: item.disabled = True
            try: await self.message.edit(content="Время для выбора истекло. Вызовите команду заново.", view=self)
            except: pass

# --- UI для /point add_extra (создание ивента с нуля) ---

class AddExtraPointModal(discord.ui.Modal, title="Создать запись о баллах"):
    def __init__(self, cog_instance, user: discord.User):
        super().__init__()
        self.cog = cog_instance
        self.user = user

    end_time = discord.ui.TextInput(label="Время конца (ЧЧ:ММ ДД.ММ)", placeholder="Пример: 23:59 28.09", required=True)
    points = discord.ui.TextInput(label="Баллы", placeholder="Пример: 50", required=True)
    event_name = discord.ui.TextInput(label="Название ивента", placeholder="Пример: Особый ивент", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            pts = int(self.points.value)
            current_year = datetime.now().year
            moscow_tz = pytz.timezone('Europe/Moscow')
            end_dt = moscow_tz.localize(datetime.strptime(f"{self.end_time.value}.{current_year}", '%H:%M %d.%m.%Y'))
            
            # Очищаем название ивента перед сохранением
            sanitized_name = re.sub(r'[`\n\r]+', ' ', self.event_name.value).strip() or "Без названия"

            entry = {
                "entry_id": str(uuid.uuid4()),
                "user_id": self.user.id,
                "points": pts,
                "event_name": sanitized_name,
                "end_time_iso": end_dt.isoformat(),
                "adder_id": interaction.user.id,
                "adder_name": interaction.user.display_name,
            }
            self.cog.add_point_entry(entry)
            await interaction.response.send_message(f"Баллы ({pts}) успешно начислены <@{self.user.id}> за '{sanitized_name}'.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Ошибка формата данных.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Произошла ошибка: {e}", ephemeral=True)

# --- UI для /point remove ---

class PointRemoveSelect(discord.ui.Select):
    # ... (код без изменений) ...
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
        super().__init__(placeholder="Выберите запись для удаления...", min_values=1, max_values=1, options=options, disabled=(not entries))

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

    @point_group.command(name="add", description="Добавить баллы к одному из последних 10 ивентов пользователя.")
    @app_commands.describe(пользователь="Пользователь, чьи ивенты нужно найти")
    @app_commands.guild_only()
    @is_admin()
    async def add_points(self, interaction: discord.Interaction, пользователь: discord.User):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            # 1. Сканируем эмбеды
            parse_channel_id = int(os.getenv("PARSE_CHANNEL_ID"))
            channel = self.bot.get_channel(parse_channel_id)
            if not channel:
                await interaction.followup.send("Ошибка: Не удалось найти канал для парсинга.", ephemeral=True)
                return

            user_events = []
            async for message in channel.history(limit=1000):
                if not message.embeds: continue
                for embed in message.embeds:
                    # ... (логика парсинга эмбеда для поиска user_id)
                    user_id_from_embed = None
                    user_info_source = None
                    if embed.description and "<@" in embed.description: user_info_source = embed.description
                    else:
                        for field in embed.fields:
                            if "<@" in field.value: user_info_source = field.value; break
                    if user_info_source:
                        match = re.search(r'<@(\d+)>', user_info_source)
                        if match: user_id_from_embed = int(match.group(1))

                    if user_id_from_embed == пользователь.id:
                        data = {'user_id': user_id_from_embed, 'event_name': 'Без названия', 'timestamp_dt': message.created_at.astimezone(pytz.timezone('Europe/Moscow')), 'message_id': message.id, 'unique_id': f"embed_{message.id}"}
                        for field in embed.fields:
                            clean_name = field.name.lower().replace('>', '').strip()
                            if clean_name == 'ивент':
                                # Улучшенная очистка названия ивента
                                sanitized_name = re.sub(r'[`\n\r]+', ' ', field.value).strip()
                                data['event_name'] = sanitized_name or 'Без названия'
                                break
                        user_events.append(data)

            # 2. Собираем мануальные ивенты
            manual_points = self._load_points()
            for entry in manual_points:
                if entry['user_id'] == пользователь.id:
                    # Очищаем название ивента и здесь для консистентности
                    sanitized_name = re.sub(r'[`\n\r]+', ' ', entry['event_name']).strip() or "Без названия"
                    user_events.append({
                        'user_id': entry['user_id'],
                        'event_name': sanitized_name,
                        'timestamp_dt': datetime.fromisoformat(entry['end_time_iso']),
                        'unique_id': f"manual_{entry['entry_id']}"
                    })

            # 3. Сортируем и выбираем последние 10
            user_events.sort(key=lambda x: x['timestamp_dt'], reverse=True)
            events_to_show = user_events[:10]

            if not events_to_show:
                await interaction.followup.send(f"Не найдено недавних ивентов для {пользователь.mention}.", ephemeral=True)
                return

            view = SelectUserEventView(self, events_to_show)
            message = await interaction.followup.send(f"Выберите один из последних 10 ивентов для {пользователь.mention}:", view=view, ephemeral=True)
            view.message = message

        except Exception as e:
            print(f"Ошибка в /point add: {e}")
            await interaction.followup.send(f"Произошла ошибка: {e}", ephemeral=True)

    @point_group.command(name="add_extra", description="Создать запись о начислении баллов с нуля.")
    @app_commands.describe(пользователь="Пользователь, которому начисляются баллы")
    @app_commands.guild_only()
    @is_admin()
    async def add_extra_points(self, interaction: discord.Interaction, пользователь: discord.User):
        modal = AddExtraPointModal(self, пользователь)
        await interaction.response.send_modal(modal)

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

