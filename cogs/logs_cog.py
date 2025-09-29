import discord
from discord import app_commands
from discord.ext import commands
import os
import io
from datetime import datetime, timedelta
import pytz
import json
import re
from main import is_admin

# --- Вспомогательные классы для UI (без изменений) ---

class DateRangeModal(discord.ui.Modal, title='Укажите диапазон дат'):
    def __init__(self, category_name: str, log_type: str, user_id: int, cog_instance):
        super().__init__()
        self.category_name = category_name
        self.log_type = log_type
        self.user_id = user_id
        self.cog_instance = cog_instance

    date_range_input = discord.ui.TextInput(
        label="Дата или диапазон (ДД.ММ или ДД.ММ-ДД.ММ)",
        placeholder="Пример: 21.09 или 21.09-22.09",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            events = await self.cog_instance._get_events_in_range(
                interaction, self.date_range_input.value, self.log_type, 
                user_id=self.user_id, category_name=self.category_name
            )
            if not events:
                await interaction.followup.send("За указанный период не найдено ивентов.", ephemeral=True)
                return

            log_file = await self.cog_instance.generate_log_file(
                events, self.date_range_input.value, self.log_type, category_name=self.category_name
            )
            
            log_channel_id = int(os.getenv("LOG_CHANNEL_ID"))
            log_channel = self.cog_instance.bot.get_channel(log_channel_id)

            if log_channel:
                await log_channel.send(file=log_file)
                user_mention = f" для <@{self.user_id}>" if self.user_id else ""
                await interaction.followup.send(f"Лог{user_mention} успешно создан и отправлен в канал {log_channel.mention}.", ephemeral=True)
            else:
                await interaction.followup.send("Ошибка: Не удалось найти канал для логов. Проверьте LOG_CHANNEL_ID.", ephemeral=True)

        except ValueError as e:
            await interaction.followup.send(f"Ошибка: {e}", ephemeral=True)
        except Exception as e:
            print(f"Критическая ошибка в модальном окне: {e}")
            await interaction.followup.send(f"Произошла непредвиденная ошибка при создании лога: {e}", ephemeral=True)

class MakserSelect(discord.ui.Select):
    def __init__(self, cog_instance):
        self.cog = cog_instance
        options = []
        
        options.append(discord.SelectOption(
            label="Общий", 
            value="__all__", 
            description="Суммарный отчет по всем категориям"
        ))

        try:
            categories_data = self.cog._load_json(self.cog.categories_file, {})
            categories = list(categories_data.keys())
            
            options.extend([discord.SelectOption(label=name, description=f"Отчет по категории '{name}'") for name in categories])
            
            if "Other" not in categories:
                options.append(discord.SelectOption(label="Other", description="Отчет по ивентам без категории"))
        except Exception as e:
            print(f"Ошибка загрузки категорий для MakserSelect: {e}")

        if len(options) == 1:
             options.append(discord.SelectOption(label="Категории не найдены", value="disabled", description="Создайте категории командой /category create"))


        super().__init__(
            placeholder="Выберите категорию для отчета...", min_values=1, max_values=1, options=options,
            disabled=(len(options) > 0 and options[0].value == "disabled")
        )

    async def callback(self, interaction: discord.Interaction):
        category_name = self.values[0]
        modal = DateRangeModal(category_name=category_name, log_type='makser', user_id=None, cog_instance=self.cog)
        await interaction.response.send_modal(modal)

class MakserView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=300)
        self.add_item(MakserSelect(cog_instance))

class LogsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        self.data_path = getattr(self.bot, 'data_path', '.')
        self.categories_file = os.path.join(self.data_path, 'categories.json')
        self.blum_file = os.path.join(self.data_path, 'blum_list.json')
        self.points_file = os.path.join(self.data_path, 'manual_points.json')

    def _load_json(self, filename, default_value):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default_value

    def parse_date_range(self, date_str: str):
        current_year = datetime.now().year
        def parse_date(d_str):
            try:
                dt_obj = datetime.strptime(f"{d_str.strip()}.{current_year}", '%d.%m.%Y')
                return self.moscow_tz.localize(dt_obj)
            except ValueError:
                raise ValueError(f"Неверный формат даты: '{d_str}'. Используйте ДД.ММ.")

        if '-' in date_str:
            start_str, end_str = date_str.split('-')
            start_date = parse_date(start_str)
            end_date = parse_date(end_str) + timedelta(days=1)
        else:
            start_date = parse_date(date_str)
            end_date = start_date + timedelta(days=1)
        return start_date, end_date

    async def _get_events_in_range(self, interaction: discord.Interaction, date_range_str: str, log_type: str, user_id: int = None, category_name: str = None):
        start_time, end_time = self.parse_date_range(date_range_str)
        
        all_events = []
        
        manual_points = self._load_json(self.points_file, [])
        edited_message_ids = {entry['original_message_id'] for entry in manual_points if 'original_message_id' in entry}
        
        original_nick_cache = {}
        historical_nick_cache = {}
        
        parse_channel_id = int(os.getenv("PARSE_CHANNEL_ID"))
        channel = self.bot.get_channel(parse_channel_id)
        if not channel:
            await interaction.followup.send("Ошибка: Не удалось найти канал для парсинга.", ephemeral=True)
            return []

        async for message in channel.history(limit=None, after=start_time, before=end_time):
            if not message.embeds: continue
            for embed in message.embeds:
                if embed.title != "Отчет о проведенном ивенте": continue
                
                parsed_data = {'user_id': None, 'user_nick': 'N/A', 'points': 0, 'event_name': 'Без названия', 'timestamp_dt': message.created_at.astimezone(self.moscow_tz)}
                if embed.description:
                    match = re.search(r'<@(\d+)>', embed.description)
                    if match:
                        parsed_data['user_id'] = int(match.group(1))
                        nick_part = embed.description[match.end():].strip()
                        parsed_data['user_nick'] = nick_part.replace('`', '').strip() or 'N/A'
                for field in embed.fields:
                    clean_field_name = field.name.lower().replace('>', '').strip()
                    if clean_field_name == 'получено':
                        try: parsed_data['points'] = int(re.search(r'\d+', field.value).group())
                        except: continue
                    elif clean_field_name == 'ивент':
                        parsed_data['event_name'] = field.value.replace('`', '').strip()
                
                if parsed_data['user_id']:
                    original_nick_cache[message.id] = parsed_data['user_nick']
                    if parsed_data['user_id'] not in historical_nick_cache:
                        historical_nick_cache[parsed_data['user_id']] = parsed_data['user_nick']

                if message.id not in edited_message_ids:
                    if parsed_data['points'] > 0 and parsed_data['user_id'] is not None:
                        all_events.append(parsed_data)

        # --- НОВЫЙ БЛОК: Поиск ников для ручных записей за пределами диапазона ---
        manual_entries_in_range = [e for e in manual_points if start_time <= datetime.fromisoformat(e['end_time_iso']) < end_time]
        users_needing_full_search = {
            e['user_id'] for e in manual_entries_in_range 
            if not e.get('original_message_id') and e['user_id'] not in historical_nick_cache
        }

        if users_needing_full_search:
            async for message in channel.history(limit=None): 
                if not users_needing_full_search: break
                if not message.embeds: continue
                for embed in message.embeds:
                    if embed.title != "Отчет о проведенном ивенте": continue
                    if embed.description:
                        match = re.search(r'<@(\d+)>', embed.description)
                        if match:
                            uid = int(match.group(1))
                            if uid in users_needing_full_search:
                                nick_part = embed.description[match.end():].strip()
                                user_nick = nick_part.replace('`', '').strip() or 'N/A'
                                historical_nick_cache[uid] = user_nick
                                users_needing_full_search.remove(uid)

        # --- ОБРАБОТКА РУЧНЫХ ЗАПИСЕЙ ---
        current_nick_cache = {}
        for entry in manual_entries_in_range:
            user_nick = 'N/A'
            original_message_id = entry.get('original_message_id')
            uid = entry['user_id']
            
            if original_message_id and original_message_id in original_nick_cache:
                user_nick = original_nick_cache[original_message_id]
            elif uid in historical_nick_cache:
                user_nick = historical_nick_cache[uid]
            else:
                if uid not in current_nick_cache:
                    try:
                        member = await interaction.guild.fetch_member(uid)
                        current_nick_cache[uid] = member.display_name if member else f"ID {uid}"
                    except discord.NotFound:
                        current_nick_cache[uid] = f"ID {uid}"
                user_nick = current_nick_cache[uid]
            
            all_events.append({
                'user_id': uid, 'user_nick': user_nick, 'points': entry['points'],
                'event_name': entry['event_name'], 'timestamp_dt': datetime.fromisoformat(entry['end_time_iso'])
            })
        
        # --- ФИЛЬТРАЦИЯ ---
        filtered_events = all_events
        if log_type == 'night_log':
            night_events = []
            for event in filtered_events:
                if event['points'] <= 0: continue
                end_time_event = event['timestamp_dt']
                start_time_event = end_time_event - timedelta(minutes=event['points'])
                night_start_boundary = end_time_event.replace(hour=2, minute=0, second=0, microsecond=0)
                night_end_boundary = end_time_event.replace(hour=8, minute=0, second=0, microsecond=0)
                if start_time_event < night_end_boundary and end_time_event > night_start_boundary:
                    night_events.append(event)
            filtered_events = night_events

        if user_id:
            filtered_events = [e for e in filtered_events if e['user_id'] == user_id]
        
        categories = self._load_json(self.categories_file, {})
        for event in filtered_events:
            event['category'] = 'Other'
            for cat, event_list in categories.items():
                if event['event_name'].lower() in [ev.lower() for ev in event_list]:
                    event['category'] = cat
                    break
        
        if category_name and category_name != "__all__":
             filtered_events = [e for e in filtered_events if e['category'] == category_name]

        return sorted(filtered_events, key=lambda x: x['timestamp_dt'])

    async def generate_log_file(self, events: list, date_range_str: str, log_type: str, category_name: str = None):
        buffer = io.StringIO()
        total_points = 0
        if log_type == 'makser':
            if category_name == "__all__":
                buffer.write(f"Общий суммарный отчет за {date_range_str}\n\n")
            else:
                buffer.write(f"Суммарный отчет по категории '{category_name}' за {date_range_str}\n\n")
                
            user_points = {}
            for event in events:
                user_id = event['user_id']
                points = event['points']
                total_points += points
                user_points[user_id] = user_points.get(user_id, 0) + points
            
            sorted_users = sorted(user_points.items(), key=lambda item: item[1], reverse=True)
            for i, (user_id, points) in enumerate(sorted_users, 1):
                buffer.write(f"{i}. <@{user_id}> - {points} баллов\n")
        
        elif log_type == 'eventstats':
            buffer.write(f"Статистика по ивентам за {date_range_str}\n\n")
            
            event_stats = {}
            for event in events:
                name = event['event_name']
                points = event['points']
                category = event['category']
                if name not in event_stats:
                    event_stats[name] = {'count': 0, 'points': 0, 'category': category}
                event_stats[name]['count'] += 1
                event_stats[name]['points'] += points

            stats_by_category = {}
            for name, data in event_stats.items():
                category = data['category']
                if category not in stats_by_category:
                    stats_by_category[category] = []
                stats_by_category[category].append({'name': name, 'count': data['count'], 'points': data['points']})

            sorted_categories = sorted(stats_by_category.keys())
            for category in sorted_categories:
                buffer.write(f"--- Категория: {category} ---\n")
                sorted_events = sorted(stats_by_category[category], key=lambda x: x['name'])
                for event_data in sorted_events:
                    buffer.write(f"{event_data['name']} | {event_data['count']} | {event_data['points']}\n")
                buffer.write("\n")
        else:
            blum_list = self._load_json(self.blum_file, [])
            for event in events:
                if event['points'] <= 0: continue
                end_time = event['timestamp_dt']
                start_time = end_time - timedelta(minutes=event['points'])
                line = f"{start_time.strftime('%H:%M %d.%m.%Y')} | {end_time.strftime('%H:%M %d.%m.%Y')} | <@{event['user_id']}> | {event['user_nick']} | "
                current_points = event['points']
                night_bonus_info = ""

                if log_type == 'night_log':
                    is_blum = event['user_id'] in blum_list
                    
                    if is_blum:
                        night_start = end_time.replace(hour=2, minute=0, second=0, microsecond=0)
                        night_end = end_time.replace(hour=8, minute=0, second=0, microsecond=0)
                        multiplier = 2.0
                    else:
                        night_start = end_time.replace(hour=3, minute=0, second=0, microsecond=0)
                        night_end = end_time.replace(hour=7, minute=0, second=0, microsecond=0)
                        multiplier = 1.5

                    actual_start = max(start_time, night_start)
                    actual_end = min(end_time, night_end)
                    bonus_minutes = 0
                    if actual_end > actual_start:
                        bonus_minutes = round((actual_end - actual_start).total_seconds() / 60)
                    
                    if bonus_minutes > 0:
                        bonus_points = round(bonus_minutes * (multiplier - 1.0))
                        night_bonus_info = f"({multiplier}x) +{bonus_points} | "
                        total_points += bonus_points
                
                line += f"{current_points} | {night_bonus_info}{event['event_name']} | {event.get('category', 'Other')}\n"
                buffer.write(line)
                total_points += current_points
        
        if log_type != 'eventstats':
            buffer.write(f"\nИтог: {total_points} баллов")

        buffer.seek(0)
        safe_date_range = re.sub(r'[<>:"/\\|?*]', '_', date_range_str)
        filename = f"log_{log_type}_{safe_date_range}.txt"
        return discord.File(buffer, filename=filename)

    # --- Команды ---
    @app_commands.command(name="logs", description="Общий лог за дату или период.")
    @app_commands.guild_only()
    async def logs(self, interaction: discord.Interaction):
        modal = DateRangeModal(category_name=None, log_type='general', user_id=None, cog_instance=self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="log", description="Лог категории за дату или период.")
    @app_commands.guild_only()
    async def log(self, interaction: discord.Interaction, категория: str):
        categories = self._load_json(self.categories_file, {})
        if категория not in categories and категория != 'Other':
            await interaction.response.send_message(f"Ошибка: Категория '{категория}' не найдена.", ephemeral=True)
            return
        modal = DateRangeModal(category_name=категория, log_type='category', user_id=None, cog_instance=self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="night_log", description="Лог ночной активности за период.")
    @app_commands.guild_only()
    async def night_log(self, interaction: discord.Interaction):
        modal = DateRangeModal(category_name=None, log_type='night_log', user_id=None, cog_instance=self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="check", description="Лог активности человека за дату или период.")
    @app_commands.guild_only()
    async def check(self, interaction: discord.Interaction, пользователь: discord.User):
        modal = DateRangeModal(category_name=None, log_type='check', user_id=пользователь.id, cog_instance=self)
        await interaction.response.send_modal(modal)
    
    @app_commands.command(name="makser", description="Показывает панель для создания суммарного отчета по категориям.")
    @app_commands.guild_only()
    async def makser(self, interaction: discord.Interaction):
        try:
            view = MakserView(self)
            await interaction.response.send_message("Выберите категорию для отчета:", view=view, ephemeral=True)
        except Exception as e:
            print(f"Критическая ошибка при создании вида для команды /makser: {e}")
            await interaction.response.send_message("Произошла ошибка при отображении панели.", ephemeral=True)

    @app_commands.command(name="eventstats", description="Статистика по ивентам за период.")
    @app_commands.guild_only()
    async def eventstats(self, interaction: discord.Interaction):
        modal = DateRangeModal(category_name=None, log_type='eventstats', user_id=None, cog_instance=self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="clear", description="Очищает историю текущего канала (только для администраторов).")
    @app_commands.guild_only()
    @is_admin()
    async def clear(self, interaction: discord.Interaction, количество: discord.app_commands.Range[int, 1, 100] = 100):
        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await interaction.channel.purge(limit=количество)
            await interaction.followup.send(f"Удалено {len(deleted)} сообщений.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Ошибка: У меня нет прав для удаления сообщений в этом канале.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"Произошла ошибка при удалении сообщений: {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(LogsCog(bot))