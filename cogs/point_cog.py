import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import uuid
from datetime import datetime
import pytz
import re
import asyncio
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

# --- UI для /point edit (изменение баллов существующего ивента) ---
class EditEventSelect(discord.ui.Select):
    def __init__(self, bot, cog_instance, entries):
        self.bot = bot
        self.cog = cog_instance
        self.events_map = {entry['unique_id']: entry for entry in entries}
        
        options = []
        if not entries:
            options.append(discord.SelectOption(label="Ивенты не найдены.", value="disabled"))
        else:
            for entry in entries:
                end_dt = entry['timestamp_dt']
                label = f"{entry['event_name']} | {entry['points']} баллов"
                if len(label) > 100: label = label[:97] + "..."
                description = f"Время: {end_dt.strftime('%H:%M %d.%m.%Y')}"
                options.append(discord.SelectOption(label=label, value=entry['unique_id'], description=description))

        super().__init__(placeholder="Выберите ивент для редактирования...", options=options, disabled=(not entries))

    async def callback(self, interaction: discord.Interaction):
        # Отключаем select, чтобы избежать повторных нажатий
        self.disabled = True
        await interaction.message.edit(view=self.view)

        selected_event_id = self.values[0]
        event_data = self.events_map[selected_event_id]
        
        # Отправляем ephemeral followup, чтобы убрать "ошибку взаимодействия"
        await interaction.response.send_message("Ожидание ввода...", ephemeral=True, delete_after=1)
        
        prompt_msg = await interaction.channel.send(
            f"{interaction.user.mention}, введите новое количество баллов для ивента **'{event_data['event_name']}'**."
        )

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        try:
            response_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            new_points = int(response_msg.content)

            # Удаляем старую запись
            self.cog.remove_point_entry(event_data['unique_id'])
            
            # Создаем новую запись
            entry = {
                "entry_id": str(uuid.uuid4()),
                "user_id": event_data['user_id'],
                "points": new_points,
                "event_name": event_data['event_name'],
                "end_time_iso": event_data['timestamp_dt'].isoformat(),
                "adder_id": interaction.user.id,
                "adder_name": interaction.user.display_name,
                "source_message_id": event_data.get('message_id')
            }
            self.cog.add_point_entry(entry)

            await interaction.followup.send(f"Баллы для ивента '{event_data['event_name']}' изменены на {new_points}.", ephemeral=True)
            
            # Удаляем сообщения
            try:
                await prompt_msg.delete()
                await response_msg.delete()
            except discord.HTTPException:
                pass # Если сообщения уже удалены, ничего страшного

        except asyncio.TimeoutError:
            await interaction.followup.send("Время на ввод истекло.", ephemeral=True)
            try: await prompt_msg.delete()
            except discord.HTTPException: pass
        except ValueError:
            await interaction.followup.send("Ошибка: Введено не число.", ephemeral=True)
            try: await prompt_msg.delete()
            except discord.HTTPException: pass
        except Exception as e:
            print(f"Ошибка в /point edit callback: {e}")
            await interaction.followup.send("Произошла непредвиденная ошибка.", ephemeral=True)

class EditEventView(discord.ui.View):
    def __init__(self, bot, cog_instance, entries):
        super().__init__(timeout=300)
        self.add_item(EditEventSelect(bot, cog_instance, entries))

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
        self.cog.remove_point_entry(f"manual_{entry_id}")
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
        
    def remove_point_entry(self, unique_id: str):
        if not unique_id.startswith("manual_"): return
        entry_id_to_remove = unique_id.split('_', 1)[1]
        data = self._load_points()
        data = [e for e in data if e.get('entry_id') != entry_id_to_remove]
        self._save_points(data)

    point_group = app_commands.Group(name="point", description="Команды для ручного управления баллами")

    @point_group.command(name="add", description="Начислить баллы пользователю вручную.")
    @app_commands.guild_only()
    @is_admin()
    async def add_points(self, interaction: discord.Interaction):
        modal = PointAddModal(self)
        await interaction.response.send_modal(modal)

    @point_group.command(name="edit", description="Изменить баллы для одного из последних ивентов пользователя.")
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

            user_events = []
            # 1. Собираем мануальные ивенты
            manual_points = self._load_points()
            manual_events_processed_sources = set()
            for entry in manual_points:
                if entry['user_id'] == пользователь.id:
                    user_events.append({
                        'user_id': entry['user_id'], 'points': entry['points'], 'event_name': entry['event_name'],
                        'timestamp_dt': datetime.fromisoformat(entry['end_time_iso']),
                        'unique_id': f"manual_{entry['entry_id']}", 'message_id': entry.get('source_message_id')
                    })
                    if entry.get('source_message_id'):
                        manual_events_processed_sources.add(entry['source_message_id'])

            # 2. Сканируем эмбеды, пропуская те, что уже были обработаны вручную
            async for message in channel.history(limit=1000):
                if not message.embeds or message.id in manual_events_processed_sources: continue
                for embed in message.embeds:
                    user_id_from_embed = None
                    if embed.description and "<@" in embed.description:
                        match = re.search(r'<@(\d+)>', embed.description)
                        if match: user_id_from_embed = int(match.group(1))

                    if user_id_from_embed == пользователь.id:
                        data = {
                            'user_id': user_id_from_embed, 'points': 0, 'event_name': 'Без названия',
                            'timestamp_dt': message.created_at.astimezone(pytz.timezone('Europe/Moscow')),
                            'message_id': message.id, 'unique_id': f"embed_{message.id}"
                        }
                        for field in embed.fields:
                            clean_name = field.name.lower().replace('>', '').strip()
                            if clean_name == 'получено':
                                try: data['points'] = int(re.search(r'\d+', field.value).group())
                                except: pass
                            elif clean_name == 'ивент':
                                data['event_name'] = field.value.replace('`', '').strip() or 'Без названия'
                        user_events.append(data)
                        break

            user_events.sort(key=lambda x: x['timestamp_dt'], reverse=True)
            events_to_show = user_events[:10]

            if not events_to_show:
                await interaction.followup.send(f"Не найдено недавних ивентов для {пользователь.mention}.", ephemeral=True)
                return

            view = EditEventView(self.bot, self, events_to_show)
            await interaction.followup.send(f"Выберите ивент для редактирования (показаны последние 10):", view=view, ephemeral=True)
        except Exception as e:
            print(f"Ошибка в /point edit: {e}")
            await interaction.followup.send(f"Произошла непредвиденная ошибка.", ephemeral=True)

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

