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
    def __init__(self, category_name: str, log_type: str, cog_instance):
        super().__init__()
        self.category_name = category_name
        self.log_type = log_type
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
                interaction, self.date_range_input.value, self.log_type, category_name=self.category_name
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
                await interaction.followup.send(f"Лог успешно создан и отправлен в канал {log_channel.mention}.", ephemeral=True)
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
        
        try:
            with open('categories.json', 'r', encoding='utf-8') as f:
                categories = list(json.load(f).keys())
        except (FileNotFoundError, json.JSONDecodeError):
            categories = []

        options = [discord.SelectOption(label=name, description=f"Отчет по категории '{name}'") for name in categories]
        options.append(discord.SelectOption(label="Other", description="Отчет по ивентам без категории"))
        
        if not options:
            options.append(discord.SelectOption(label="No categories found", value="disabled", default=True))

        super().__init__(
            placeholder="Выберите категорию для отчета...", 
            min_values=1, 
            max_values=1, 
            options=options,
            disabled=(len(options) == 1 and options[0].value == "disabled")
        )

    async def callback(self, interaction: discord.Interaction):
        category_name = self.values[0]
        modal = DateRangeModal(
            category_name=category_name,
            log_type='makser',
            cog_instance=self.cog
        )
        await interaction.response.send_modal(modal)

class MakserView(discord.ui.View):
    """View, содержащий выпадающее меню для /makser."""
    def __init__(self, cog_instance):
        super().__init__(timeout=300)
        self.add_item(MakserSelect(cog_instance))


# --- Основной класс кога ---

class LogsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.moscow_tz = pytz.timezone('Europe/Moscow')
        self.blum_list = self._load_json('blum_list.json', [])
        self.categories = self._load_json('categories.json', {})

    def _load_json(self, filename, default_value):
        """Загружает данные из JSON файла."""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return default_value

    def _save_json(self, filename, data):
        """Сохраняет данные в JSON файл."""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    def parse_date_range(self, date_str: str):
        """Парсит строку с датой или диапазоном в объекты datetime."""
        current_year = datetime.now().year
        
        def parse_date(d_str):
            try:
                # Добавляем год к строке и парсим
                dt_obj = datetime.strptime(f"{d_str.strip()}.{current_year}", '%d.%m.%Y')
                # Локализуем в московское время
                return self.moscow_tz.localize(dt_obj)
            except ValueError:
                raise ValueError(f"Неверный формат даты: '{d_str}'. Используйте ДД.ММ.")

        if '-' in date_str:
            start_str, end_str = date_str.split('-')
            start_date = parse_date(start_str)
            # Конечная дата - это конец дня (23:59:59), поэтому берем следующий день и отнимаем секунду
            end_date = parse_date(end_str) + timedelta(days=1) - timedelta(seconds=1)
        else:
            start_date = parse_date(date_str)
            end_date = start_date + timedelta(days=1) - timedelta(seconds=1)
        
        return start_date, end_date

    async def _get_events_in_range(self, interaction: discord.Interaction, date_range_str: str, log_type: str, user_id: int = None, category_name: str = None):
        """Основная функция для получения ивентов из истории канала."""
        print("--- Начало сканирования истории ---")
        parse_channel_id = int(os.getenv("PARSE_CHANNEL_ID"))
        channel = self.bot.get_channel(parse_channel_id)
        if not channel:
            await interaction.followup.send("Ошибка: Не удалось найти канал для парсинга. Проверьте PARSE_CHANNEL_ID.", ephemeral=True)
            return []

        start_time, end_time = self.parse_date_range(date_range_str)
        
        print(f"Канал: #{channel.name} ({channel.id})")
        print(f"Ищем сообщения с {start_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')} по {end_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')}")

        events = []
        message_count = 0
        
        # Инвертируем after и before, т.к. now() > than yesterday()
        async for message in channel.history(limit=None, after=start_time, before=end_time):
            message_count += 1
            print(f"\n[#{message_count}] Проверяем сообщение ID: {message.id} от {message.author.name}")

            if not message.embeds:
                print(" -> Нет эмбедов, пропускаем.")
                continue

            for embed in message.embeds:
                print(f" -> Найден эмбед с заголовком: '{embed.title}'")
                if embed.title != "Отчет о проведенном ивенте":
                    continue

                print(" -> ЗАГОЛОВОК СОВПАЛ! Начинаю парсинг данных...")
                
                data = {'user_id': None, 'user_nick': 'N/A', 'points': 0, 'event_name': 'Без названия', 'timestamp': message.created_at}
                
                # Парсинг Ивентера
                if embed.description:
                    desc_parts = embed.description.split()
                    if desc_parts:
                        try:
                            # Упоминание всегда первое, вида <@ID>
                            user_id_str = desc_parts[0].replace('<@', '').replace('>', '')
                            data['user_id'] = int(user_id_str)
                            # Ник - все остальное после упоминания
                            nick = ' '.join(desc_parts[1:]).replace('`', '').strip()
                            data['user_nick'] = nick if nick else 'N/A'
                        except (ValueError, IndexError):
                            print(" -> Ошибка парсинга ID/Ника ивентера.")
                
                # Парсинг полей
                for field in embed.fields:
                    field_name = field.name.lower()
                    print(f"   -> Поле: '{field.name}' | Значение: '{field.value}'")
                    if 'получено' in field_name:
                        try:
                            data['points'] = int(field.value.split()[0])
                        except (ValueError, IndexError):
                            print("   -> Ошибка парсинга баллов.")
                    elif 'ивент' in field_name:
                        data['event_name'] = field.value.replace('`', '').strip()

                print(f" -> Распарсенные данные: {data}")

                if data['points'] == 0:
                    print(f" -> Баллы равны 0. Пропускаем ивент '{data['event_name']}'.")
                    continue
                
                events.append(data)
        
        print(f"--- Сканирование завершено. Проверено сообщений: {message_count}. Найдено ивентов: {len(events)} ---")

        # Фильтрация после сбора
        if user_id:
            events = [e for e in events if e['user_id'] == user_id]

        self.categories = self._load_json('categories.json', {})
        
        # Присваиваем категории
        for event in events:
            event['category'] = 'Other'
            for cat, event_list in self.categories.items():
                if event['event_name'].lower() in [ev.lower() for ev in event_list]:
                    event['category'] = cat
                    break
        
        if category_name:
             events = [e for e in events if e['category'] == category_name]

        return sorted(events, key=lambda x: x['timestamp'])

    async def generate_log_file(self, events: list, date_range_str: str, log_type: str, category_name: str = None):
        """Генерирует текстовый файл лога."""
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
        
        else: # Общий, ночной, по категории, персональный
            for event in events:
                end_time = event['timestamp'].astimezone(self.moscow_tz)
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

    @app_commands.command(name="logs", description="Общий лог за дату или период.")
    @app_commands.guild_only()
    async def logs(self, interaction: discord.Interaction, date_range: str):
        modal = DateRangeModal(category_name=None, log_type='general', cog_instance=self)
        modal.date_range_input.default = date_range
        await interaction.response.send_modal(modal)

    @app_commands.command(name="log", description="Лог определенной категории за дату или период.")
    @app_commands.guild_only()
    async def log(self, interaction: discord.Interaction, категория: str, date_range: str):
        self.categories = self._load_json('categories.json', {})
        if категория not in self.categories and категория != 'Other':
            await interaction.response.send_message(f"Ошибка: Категория '{категория}' не найдена.", ephemeral=True)
            return
        
        modal = DateRangeModal(category_name=категория, log_type='category', cog_instance=self)
        modal.date_range_input.default = date_range
        await interaction.response.send_modal(modal)

    @app_commands.command(name="night_log", description="Лог ночной активности за период.")
    @app_commands.guild_only()
    async def night_log(self, interaction: discord.Interaction, date_range: str):
        modal = DateRangeModal(category_name=None, log_type='night_log', cog_instance=self)
        modal.date_range_input.default = date_range
        await interaction.response.send_modal(modal)

    @app_commands.command(name="check", description="Лог активности определенного человека за дату или период.")
    @app_commands.guild_only()
    async def check(self, interaction: discord.Interaction, пользователь: discord.User, date_range: str):
        await interaction.response.defer(thinking=True, ephemeral=True)
        events = await self._get_events_in_range(interaction, date_range, 'check', user_id=пользователь.id)
        
        if not events:
            await interaction.followup.send(f"Не найдено ивентов для пользователя {пользователь.mention} за указанный период.", ephemeral=True)
            return
            
        log_file = await self.generate_log_file(events, date_range, 'check')
        log_channel_id = int(os.getenv("LOG_CHANNEL_ID"))
        log_channel = self.bot.get_channel(log_channel_id)
        
        if log_channel:
            await log_channel.send(file=log_file)
            await interaction.followup.send(f"Лог для {пользователь.mention} успешно создан и отправлен в {log_channel.mention}.", ephemeral=True)
        else:
            await interaction.followup.send("Ошибка: Не удалось найти канал для логов.", ephemeral=True)
    
    @app_commands.command(name="makser", description="Показывает панель для создания суммарного отчета по категориям.")
    @app_commands.guild_only()
    async def makser(self, interaction: discord.Interaction):
        """Shows a panel to create a summary report by category."""
        # `self` is the cog instance
        view = MakserView(self)
        await interaction.response.send_message("Выберите категорию для отчета:", view=view, ephemeral=True)

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

