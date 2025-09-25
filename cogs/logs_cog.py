import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import io
from datetime import datetime, timedelta, timezone
import re
from collections import defaultdict

# --- Вспомогательные классы и функции ---

class ParsedEvent:
    """Класс для хранения распарсенных данных об ивенте."""
    def __init__(self, start_time, end_time, user_id, nickname, points, event_name, category):
        self.start_time = start_time
        self.end_time = end_time
        self.user_id = user_id
        self.nickname = nickname
        self.points = points
        self.event_name = event_name
        self.category = category
        self.night_bonus = 0
        self.night_multiplier_str = ""

def parse_date_range(date_str: str):
    """Парсит строку с датой или диапазоном дат. Возвращает (start_date, end_date)."""
    msk_tz = timezone(timedelta(hours=3))
    current_year = datetime.now().year

    if '-' in date_str:
        start_str, end_str = date_str.split('-')
        start_dt_naive = datetime.strptime(start_str, '%d.%m').replace(year=current_year, hour=0, minute=0, second=0)
        end_dt_naive = datetime.strptime(end_str, '%d.%m').replace(year=current_year, hour=0, minute=0, second=0) + timedelta(days=1)
    else:
        start_dt_naive = datetime.strptime(date_str, '%d.%m').replace(year=current_year, hour=0, minute=0, second=0)
        end_dt_naive = start_dt_naive + timedelta(days=1)

    start_date = start_dt_naive.replace(tzinfo=msk_tz)
    end_date = end_dt_naive.replace(tzinfo=msk_tz)

    return start_date, end_date

# --- UI Компоненты для команды /makser ---

class DateRangeModal(ui.Modal, title='Введите диапазон дат'):
    def __init__(self, category: str, bot, log_cog):
        super().__init__()
        self.category = category
        self.bot = bot
        self.log_cog = log_cog

    dates = ui.TextInput(
        label='Дата или диапазон (ДД.ММ или ДД.ММ-ДД.ММ)',
        placeholder='Например: 21.09 или 21.09-22.09',
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            start_date, end_date = parse_date_range(self.dates.value)
        except ValueError:
            await interaction.followup.send("Неверный формат даты.", ephemeral=True)
            return

        all_events = await self.log_cog.parse_channel_history(start_date, end_date)
        if all_events is None:
            await interaction.followup.send("Не удалось найти канал для парсинга.", ephemeral=True)
            return
        
        # Для /makser мы должны учитывать ночные бонусы в подсчетах
        processed_events = self.log_cog.process_night_events(all_events)
        category_events = [event for event in processed_events if event.category.lower() == self.category.lower()]
        
        if not category_events:
            await interaction.followup.send(f"В категории `{self.category}` за указанный период не найдено ивентов.", ephemeral=True)
            return

        log_file = await self.log_cog.generate_summary_log_file(category_events, filename=f"summary_{self.category}_{self.dates.value}.txt")
        
        log_channel = self.bot.get_channel(self.bot.log_channel_id)
        if log_channel:
            await log_channel.send(f"📊 Суммарный лог по категории `{self.category}` за {self.dates.value}", file=log_file)
            await interaction.followup.send(f"Суммарный лог успешно отправлен в {log_channel.mention}.", ephemeral=True)
        else:
            await interaction.followup.send("Не удалось найти канал для логов.", ephemeral=True)

class MakserView(ui.View):
    def __init__(self, bot, log_cog):
        super().__init__(timeout=None)
        self.bot = bot
        self.log_cog = log_cog
        with open('categories.json', 'r', encoding='utf-8') as f:
            categories = json.load(f)
        
        for category_name in categories:
            self.add_item(ui.Button(label=category_name, custom_id=f"makser_cat_{category_name}", style=discord.ButtonStyle.secondary))
        
        self.add_item(ui.Button(label="Other", custom_id="makser_cat_Other", style=discord.ButtonStyle.secondary))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data and interaction.data.get("custom_id"):
            custom_id = interaction.data["custom_id"]
            if custom_id.startswith("makser_cat_"):
                category_name = custom_id.replace("makser_cat_", "")
                modal = DateRangeModal(category=category_name, bot=self.bot, log_cog=self.log_cog)
                await interaction.response.send_modal(modal)
                return False
        return True


# --- Основной Ког ---

class LogsCog(commands.Cog):
    """Ког для парсинга истории и генерации логов."""
    def __init__(self, bot):
        self.bot = bot
        self.msk_tz = timezone(timedelta(hours=3))

    def get_category_for_event(self, event_name):
        with open('categories.json', 'r', encoding='utf-8') as f:
            categories = json.load(f)
        for category, events in categories.items():
            if event_name in events:
                return category
        return "Other"

    async def parse_channel_history(self, after_date, before_date):
        """Асинхронно парсит историю канала и возвращает список объектов ParsedEvent."""
        channel = self.bot.get_channel(self.bot.parse_channel_id)
        if not channel: return None
        all_events = []
        async for message in channel.history(limit=None, after=after_date, before=before_date):
            if not message.embeds or message.embeds[0].title is None or message.embeds[0].title.strip() != "Отчет о проведенном ивенте":
                continue
            try:
                embed = message.embeds[0]
                iventer_field = embed.description.split('\n')[0]
                user_id_match = re.search(r'<@!?(\d+)>', iventer_field)
                user_id = int(user_id_match.group(1)) if user_id_match else None
                nickname_match = re.search(r'<@!?\d+>\s+(.+)', iventer_field)
                nickname = nickname_match.group(1).strip().replace('`', '') if nickname_match else "Не найден"
                if not user_id: continue
                points = 0
                event_name = "Без названия"
                for field in embed.fields:
                    field_name_lower = field.name.lower().strip()
                    if "получено" in field_name_lower:
                        points_match = re.search(r'\d+', field.value)
                        if points_match: points = int(points_match.group(0))
                    elif "ивент" in field_name_lower and "время активности" not in field_name_lower:
                        event_name = field.value.strip().replace('`', '')
                if points == 0: continue
                end_time = message.created_at.astimezone(self.msk_tz)
                start_time = end_time - timedelta(minutes=points)
                category = self.get_category_for_event(event_name)
                all_events.append(ParsedEvent(start_time, end_time, user_id, nickname, points, event_name, category))
            except Exception as e:
                print(f"!!! ОШИБКА при парсинге сообщения {message.id}: {e}")
        return all_events

    def process_night_events(self, events):
        """Обрабатывает список ивентов, добавляя ночные бонусы."""
        with open('blum_list.json', 'r', encoding='utf-8') as f:
            blum_list = json.load(f)
        
        for event in events:
            night_start_hour, night_end_hour = 3, 7
            current_time = event.start_time
            total_night_minutes = 0
            while current_time < event.end_time:
                if night_start_hour <= current_time.hour < night_end_hour: total_night_minutes += 1
                current_time += timedelta(minutes=1)

            if total_night_minutes > 0:
                is_blum = event.user_id in blum_list
                multiplier = 2.0 if is_blum else 1.5
                bonus_points = round(total_night_minutes * (multiplier - 1.0))
                event.night_bonus = bonus_points
                event.night_multiplier_str = "(x2)" if is_blum else "(x1.5)"
        return events

    async def generate_log_file(self, events, filename="log.txt", night_log=False):
        if not events: return None
        events.sort(key=lambda x: x.start_time)
        buffer = io.StringIO()
        total_points = 0
        for event in events:
            # Для итога всегда считаем баллы + бонус
            total_points += event.points + event.night_bonus
            
            start_str = event.start_time.strftime("%H:%M %d.%m")
            end_str = event.end_time.strftime("%H:%M %d.%m")
            if night_log:
                # Основное число - event.points (чистые баллы)
                points_str = f"{event.points} | {event.night_multiplier_str} {event.night_bonus}"
                buffer.write(f"{start_str} | {end_str} | <@{event.user_id}> | {event.nickname} | {points_str} | {event.event_name} | {event.category}\n")
            else:
                buffer.write(f"{start_str} | {end_str} | <@{event.user_id}> | {event.nickname} | {event.points} | {event.event_name} | {event.category}\n")
        
        buffer.write(f"\nИтог: {total_points} баллов")
        buffer.seek(0)
        return discord.File(buffer, filename=filename)

    async def generate_summary_log_file(self, events, filename="summary.txt"):
        if not events: return None
        user_points = defaultdict(int)
        for event in events:
            # В суммарном логе также учитываем бонус
            user_points[event.user_id] += event.points + event.night_bonus
        sorted_users = sorted(user_points.items(), key=lambda item: item[1], reverse=True)
        buffer = io.StringIO()
        total_points = sum(user_points.values())
        for i, (user_id, points) in enumerate(sorted_users):
            buffer.write(f"{i+1}. {user_id} - {points} баллов\n")
        buffer.write(f"\nИтог: {total_points} баллов")
        buffer.seek(0)
        return discord.File(buffer, filename=filename)

    # --- Команды ---
    @app_commands.command(name="logs", description="Общий лог активности за указанный период.")
    @app_commands.describe(dates="Дата или диапазон дат в формате ДД.ММ или ДД.ММ-ДД.ММ")
    async def logs(self, interaction: discord.Interaction, dates: str):
        await interaction.response.defer(ephemeral=True)
        try: start_date, end_date = parse_date_range(dates)
        except ValueError: await interaction.followup.send("Неверный формат даты.", ephemeral=True); return
        events = await self.parse_channel_history(start_date, end_date)
        if not events: await interaction.followup.send("За указанный период не найдено ивентов.", ephemeral=True); return
        log_file = await self.generate_log_file(events, filename=f"general_log_{dates}.txt")
        log_channel = self.bot.get_channel(self.bot.log_channel_id)
        if log_channel:
            await log_channel.send(f"📄 Общий лог за {dates}", file=log_file)
            await interaction.followup.send(f"Лог успешно отправлен в {log_channel.mention}.", ephemeral=True)

    @app_commands.command(name="log", description="Лог активности для конкретной категории.")
    @app_commands.describe(category="Название категории", dates="Дата или диапазон дат")
    async def category_log(self, interaction: discord.Interaction, category: str, dates: str):
        await interaction.response.defer(ephemeral=True)
        try: start_date, end_date = parse_date_range(dates)
        except ValueError: await interaction.followup.send("Неверный формат даты.", ephemeral=True); return
        all_events = await self.parse_channel_history(start_date, end_date)
        category_events = [event for event in all_events if event.category.lower() == category.lower()]
        if not category_events: await interaction.followup.send(f"В категории `{category}` не найдено ивентов.", ephemeral=True); return
        log_file = await self.generate_log_file(category_events, filename=f"log_{category}_{dates}.txt")
        log_channel = self.bot.get_channel(self.bot.log_channel_id)
        if log_channel:
            await log_channel.send(f"📄 Лог по категории `{category}` за {dates}", file=log_file)
            await interaction.followup.send(f"Лог отправлен в {log_channel.mention}.", ephemeral=True)
    
    @category_log.autocomplete('category')
    async def category_log_autocomplete(self, interaction: discord.Interaction, current: str):
        with open('categories.json', 'r', encoding='utf-8') as f: categories = json.load(f)
        return [ app_commands.Choice(name=cat, value=cat) for cat in categories if current.lower() in cat.lower() ]

    @app_commands.command(name="check", description="Лог активности конкретного пользователя.")
    @app_commands.describe(user="Пользователь для проверки", dates="Дата или диапазон дат")
    async def check_user(self, interaction: discord.Interaction, user: discord.User, dates: str):
        await interaction.response.defer(ephemeral=True)
        try: start_date, end_date = parse_date_range(dates)
        except ValueError: await interaction.followup.send("Неверный формат даты.", ephemeral=True); return
        all_events = await self.parse_channel_history(start_date, end_date)
        user_events = [event for event in all_events if event.user_id == user.id]
        if not user_events: await interaction.followup.send(f"Не найдено ивентов для {user.mention}.", ephemeral=True); return
        log_file = await self.generate_log_file(user_events, filename=f"log_{user.name}_{dates}.txt")
        log_channel = self.bot.get_channel(self.bot.log_channel_id)
        if log_channel:
            await log_channel.send(f"📄 Лог активности для {user.mention} за {dates}", file=log_file)
            await interaction.followup.send(f"Лог отправлен в {log_channel.mention}.", ephemeral=True)

    @app_commands.command(name="night_log", description="Лог ночной активности с бонусами.")
    @app_commands.describe(dates="Диапазон дат в формате ДД.ММ-ДД.ММ")
    async def night_log(self, interaction: discord.Interaction, dates: str):
        await interaction.response.defer(ephemeral=True)
        try: start_date, end_date = parse_date_range(dates)
        except ValueError: await interaction.followup.send("Неверный формат даты.", ephemeral=True); return
        all_events = await self.parse_channel_history(start_date, end_date)
        night_events_processed = self.process_night_events(all_events)
        night_events = [e for e in night_events_processed if e.night_bonus > 0]
        if not night_events: await interaction.followup.send("Ночной активности не найдено.", ephemeral=True); return
        log_file = await self.generate_log_file(night_events, filename=f"night_log_{dates}.txt", night_log=True)
        log_channel = self.bot.get_channel(self.bot.log_channel_id)
        if log_channel:
            await log_channel.send(f"🌙 Лог ночной активности за {dates}", file=log_file)
            await interaction.followup.send(f"Лог отправлен в {log_channel.mention}.", ephemeral=True)

    @app_commands.command(name="makser", description="Вызывает панель для создания суммарного лога по категориям.")
    async def makser(self, interaction: discord.Interaction):
        view = MakserView(self.bot, self)
        await interaction.response.send_message("Выберите категорию для создания лога:", view=view, ephemeral=True)

    @app_commands.command(name="clear", description="Очищает историю текущего канала (только для администраторов).")
    @app_commands.checks.has_permissions(administrator=True)
    async def clear_channel(self, interaction: discord.Interaction):
        """Очищает канал, в котором была вызвана команда."""
        await interaction.response.defer(ephemeral=True)
        
        # Цель - канал, где была вызвана команда
        channel_to_clear = interaction.channel

        if not channel_to_clear:
             # Эта проверка избыточна, т.к. interaction всегда имеет канал, но для надежности
            await interaction.followup.send("Не удалось определить текущий канал.", ephemeral=True)
            return

        try:
            deleted_messages = await channel_to_clear.purge()
            await interaction.followup.send(f"Канал {channel_to_clear.mention} был очищен. Удалено сообщений: {len(deleted_messages)}.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(f"У меня нет прав на удаление сообщений в канале {channel_to_clear.mention}.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Произошла ошибка при очистке канала: {e}", ephemeral=True)

    @clear_channel.error
    async def clear_channel_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("У вас нет прав для использования этой команды.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Произошла непредвиденная ошибка: {error}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(LogsCog(bot))

