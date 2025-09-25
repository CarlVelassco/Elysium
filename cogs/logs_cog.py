import discord
from discord import app_commands
from discord.ext import commands
import os
import io
from datetime import datetime, timedelta
import pytz

import json

# --- Вспомогательные классы для UI ---

class DateRangeModal(discord.ui.Modal, title='Укажите диапазон дат'):
    """Модальное окно для ввода диапазона дат."""
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
            # Получаем события из базы данных
            events = self.cog_instance._get_events_from_db(
                self.date_range_input.value, self.log_type, 
                user_id=self.user_id,
                category_name=self.category_name
            )

            if not events:
                await interaction.followup.send("За указанный период не найдено ивентов в базе данных. Попробуйте обновить ее командой /scan.", ephemeral=True)
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
            print(f"Error in modal submission: {e}")
            await interaction.followup.send("Произошла непредвиденная ошибка при создании лога.", ephemeral=True)

class MakserSelect(discord.ui.Select):
    """Выпадающее меню для команды /makser."""
    def __init__(self, cog_instance):
        self.cog = cog_instance
        
        options = []
        try:
            categories_data = self.cog._load_json('categories.json', {})
            categories = list(categories_data.keys())
            
            options.extend([discord.SelectOption(label=name, description=f"Отчет по категории '{name}'") for name in categories])
            
            if "Other" not in categories:
                options.append(discord.SelectOption(label="Other", description="Отчет по ивентам без категории"))
        except Exception as e:
            print(f"Error loading categories for MakserSelect: {e}")
            options = []

        if not options:
            options = [discord.SelectOption(label="Категории не найдены", value="disabled", description="Создайте категории командой /category create")]

        super().__init__(
            placeholder="Выберите категорию для отчета...", 
            min_values=1, 
            max_values=1, 
            options=options,
            disabled=(len(options) > 0 and options[0].value == "disabled")
        )

    async def callback(self, interaction: discord.Interaction):
        category_name = self.values[0]
        modal = DateRangeModal(
            category_name=category_name,
            log_type='makser',
            user_id=None,
            cog_instance=self.cog
        )
        await interaction.response.send_modal(modal)

class MakserView(discord.ui.View):
    def __init__(self, cog_instance):
        super().__init__(timeout=300)
        self.add_item(MakserSelect(cog_instance))


# --- Основной класс кога ---

class LogsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        # Загружаем данные при старте
        self.blum_list = self._load_json('blum_list.json', [])
        self.categories = self._load_json('categories.json', {})
        self.events_db = self._load_json('events_database.json', {})

    def _load_json(self, filename, default_value):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default_value

    def _save_json(self, filename, data):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

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
            end_date = parse_date(end_str) + timedelta(days=1) - timedelta(seconds=1)
        else:
            start_date = parse_date(date_str)
            end_date = start_date + timedelta(days=1) - timedelta(seconds=1)
        return start_date, end_date

    def _get_events_from_db(self, date_range_str: str, log_type: str, user_id: int = None, category_name: str = None):
        """Получает и фильтрует события из загруженной базы данных."""
        start_time, end_time = self.parse_date_range(date_range_str)
        
        all_events = list(self.events_db.values())
        filtered_events = []

        # 1. Фильтрация по дате
        for event in all_events:
            # Преобразуем строку ISO в осведомленный объект datetime
            event_time = datetime.fromisoformat(event['timestamp']).astimezone(self.moscow_tz)
            if start_time <= event_time <= end_time:
                # Добавляем преобразованный datetime для дальнейшей работы
                event['timestamp_dt'] = event_time
                filtered_events.append(event)
        
        # 2. Фильтрация для ночного лога
        if log_type == 'night_log':
            night_events = []
            for event in filtered_events:
                end_time_event = event['timestamp_dt']
                start_time_event = end_time_event - timedelta(minutes=event['points'])
                
                night_start_boundary = end_time_event.replace(hour=3, minute=0, second=0, microsecond=0)
                night_end_boundary = end_time_event.replace(hour=7, minute=0, second=0, microsecond=0)
                
                # Проверяем пересечение интервалов
                if start_time_event < night_end_boundary and end_time_event > night_start_boundary:
                    night_events.append(event)
            filtered_events = night_events

        # 3. Фильтрация по пользователю
        if user_id:
            filtered_events = [e for e in filtered_events if e['user_id'] == user_id]

        # 4. Присвоение категорий
        self.categories = self._load_json('categories.json', {})
        for event in filtered_events:
            event['category'] = 'Other'
            for cat, event_list in self.categories.items():
                if event['event_name'].lower() in [ev.lower() for ev in event_list]:
                    event['category'] = cat
                    break
        
        # 5. Фильтрация по категории
        if category_name:
             filtered_events = [e for e in filtered_events if e['category'] == category_name]

        return sorted(filtered_events, key=lambda x: x['timestamp_dt'])

    async def generate_log_file(self, events: list, date_range_str: str, log_type: str, category_name: str = None):
        buffer = io.StringIO()
        total_points = 0
        if log_type == 'makser':
            buffer.write(f"Суммарный отчет по категории '{category_name}' за {date_range_str}\n\n")
            user_points = {}
            for event in events:
                user_id = event['user_id']
                points = event['points']
                total_points += points
                user_points[user_id] = user_points.get(user_id, 0) + points
            
            sorted_users = sorted(user_points.items(), key=lambda item: item[1], reverse=True)
            for i, (user_id, points) in enumerate(sorted_users, 1):
                buffer.write(f"{i}. {user_id} - {points} баллов\n")
        else:
            for event in events:
                end_time = event['timestamp_dt']
                start_time = end_time - timedelta(minutes=event['points'])
                line = f"{start_time.strftime('%H:%M %d.%m')} | {end_time.strftime('%H:%M %d.%m')} | <@{event['user_id']}> | {event['user_nick']} | "
                current_points = event['points']
                night_bonus_info = ""

                if log_type == 'night_log':
                    night_start = end_time.replace(hour=3, minute=0, second=0, microsecond=0)
                    night_end = end_time.replace(hour=7, minute=0, second=0, microsecond=0)
                    actual_start = max(start_time, night_start)
                    actual_end = min(end_time, night_end)
                    bonus_minutes = 0
                    if actual_end > actual_start:
                        bonus_minutes = round((actual_end - actual_start).total_seconds() / 60)
                    if bonus_minutes > 0:
                        self.blum_list = self._load_json('blum_list.json', [])
                        is_blum = event['user_id'] in self.blum_list
                        multiplier = 2.0 if is_blum else 1.5
                        bonus_points = round(bonus_minutes * (multiplier - 1.0))
                        night_bonus_info = f"({multiplier}x) +{bonus_points} | "
                        total_points += bonus_points
                line += f"{current_points} | {night_bonus_info}{event['event_name']} | {event.get('category', 'Other')}\n"
                buffer.write(line)
                total_points += current_points
        buffer.write(f"\nИтог: {total_points} баллов")
        buffer.seek(0)
        filename = f"log_{log_type}_{date_range_str}.txt"
        return discord.File(buffer, filename=filename)

    # --- Команды ---

    @app_commands.command(name="scan", description="Сканирует историю и обновляет базу данных ивентов.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def scan(self, interaction: discord.Interaction, date_range: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            start_time, end_time = self.parse_date_range(date_range)
        except ValueError as e:
            await interaction.followup.send(f"Ошибка: {e}", ephemeral=True)
            return

        parse_channel_id = int(os.getenv("PARSE_CHANNEL_ID"))
        channel = self.bot.get_channel(parse_channel_id)
        if not channel:
            await interaction.followup.send("Ошибка: Не удалось найти канал для парсинга.", ephemeral=True)
            return
        
        new_events_count = 0
        async for message in channel.history(limit=None, after=start_time, before=end_time):
            if str(message.id) in self.events_db:
                continue # Пропускаем уже известные события
            
            if not message.embeds:
                continue

            for embed in message.embeds:
                if embed.title != "Отчет о проведенном ивенте":
                    continue

                data = {'message_id': str(message.id), 'user_id': None, 'user_nick': 'N/A', 'points': 0, 'event_name': 'Без названия', 'timestamp': message.created_at.isoformat()}
                
                if embed.description:
                    desc_parts = embed.description.split()
                    for i, part in enumerate(desc_parts):
                        if part.startswith('<@') and part.endswith('>'):
                            try:
                                data['user_id'] = int(part.replace('<@', '').replace('>', ''))
                                data['user_nick'] = ' '.join(desc_parts[i+1:]).replace('`', '').strip() or 'N/A'
                                break
                            except (ValueError, IndexError): continue
                
                for field in embed.fields:
                    clean_field_name = field.name.lower().replace('>', '').strip()
                    if clean_field_name == 'получено':
                        try:
                            data['points'] = int(field.value.replace('`', '').split()[0])
                        except (ValueError, IndexError): continue
                    elif clean_field_name == 'ивент':
                        data['event_name'] = field.value.replace('`', '').strip()

                if data['points'] > 0 and data['user_id'] is not None:
                    self.events_db[str(message.id)] = data
                    new_events_count += 1
        
        if new_events_count > 0:
            self._save_json('events_database.json', self.events_db)
        
        await interaction.followup.send(f"Сканирование завершено. Найдено и добавлено {new_events_count} новых ивентов в базу.", ephemeral=True)


    @app_commands.command(name="logs", description="Общий лог за дату или период из базы данных.")
    @app_commands.guild_only()
    async def logs(self, interaction: discord.Interaction):
        modal = DateRangeModal(category_name=None, log_type='general', user_id=None, cog_instance=self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="log", description="Лог категории за дату или период из базы данных.")
    @app_commands.guild_only()
    async def log(self, interaction: discord.Interaction, категория: str):
        self.categories = self._load_json('categories.json', {})
        if категория not in self.categories and категория != 'Other':
            await interaction.response.send_message(f"Ошибка: Категория '{категория}' не найдена.", ephemeral=True)
            return
        modal = DateRangeModal(category_name=категория, log_type='category', user_id=None, cog_instance=self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="night_log", description="Лог ночной активности за период из базы данных.")
    @app_commands.guild_only()
    async def night_log(self, interaction: discord.Interaction):
        modal = DateRangeModal(category_name=None, log_type='night_log', user_id=None, cog_instance=self)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="check", description="Лог активности человека за дату или период из базы данных.")
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

    @app_commands.command(name="clear", description="Очищает историю текущего канала.")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_messages=True)
    async def clear(self, interaction: discord.Interaction, количество: int = 100):
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

