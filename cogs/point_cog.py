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

    @point_group.command(name="add", description="Начислить баллы ивенту с 0 баллов по ID его сообщения.")
    @app_commands.describe(id_сообщения="ID сообщения с отчетом об ивенте")
    @app_commands.guild_only()
    @is_admin()
    async def add_points(self, interaction: discord.Interaction, id_сообщения: str):
        try:
            message_id = int(id_сообщения)
        except ValueError:
            await interaction.response.send_message("Ошибка: ID сообщения должен быть числом.", ephemeral=True)
            return

        try:
            parse_channel_id = int(os.getenv("PARSE_CHANNEL_ID"))
            channel = self.bot.get_channel(parse_channel_id)
            if not channel:
                await interaction.response.send_message("Ошибка: Не удалось найти канал для парсинга логов.", ephemeral=True)
                return

            message = await channel.fetch_message(message_id)

            # Проверка, не был ли этот ивент уже обработан
            manual_points = self._load_points()
            processed_message_ids = {entry.get('source_message_id') for entry in manual_points if entry.get('source_message_id')}
            if message.id in processed_message_ids:
                await interaction.response.send_message("Этот ивент уже был обработан и ему были начислены баллы.", ephemeral=True)
                return

            if not message.embeds:
                await interaction.response.send_message("В этом сообщении нет эмбедов.", ephemeral=True)
                return

            found_event = False
            for embed in message.embeds:
                if embed.title != "Отчет о проведенном ивенте":
                    continue

                points = -1
                for field in embed.fields:
                    if 'получено' in field.name.lower():
                        try: points = int(re.search(r'\d+', field.value).group())
                        except: points = 0
                        break
                
                if points != 0:
                    await interaction.response.send_message(f"Этот ивент имеет {points} баллов, а не 0. Начисление не требуется.", ephemeral=True)
                    return

                # Если баллы = 0, парсим данные
                event_data = {
                    'message_id': message.id,
                    'user_id': None,
                    'user_nick': 'N/A',
                    'event_name': 'Без названия',
                    'timestamp_dt': message.created_at.astimezone(pytz.timezone('Europe/Moscow'))
                }
                if embed.description:
                    match = re.search(r'<@(\d+)>', embed.description)
                    if match:
                        event_data['user_id'] = int(match.group(1))
                        nick_part = embed.description[match.end():].strip()
                        event_data['user_nick'] = nick_part.replace('`', '').strip() or 'N/A'
                
                for field in embed.fields:
                    if 'ивент' in field.name.lower():
                        event_data['event_name'] = field.value.replace('`', '').strip()

                if not event_data['user_id']:
                    await interaction.response.send_message("Не удалось определить ID ивентера в этом отчете.", ephemeral=True)
                    return
                
                # Показываем модальное окно
                modal = AddPointsToEventModal(self, event_data)
                await interaction.response.send_modal(modal)
                found_event = True
                break

            if not found_event:
                await interaction.response.send_message("Не найдено подходящего отчета об ивенте в этом сообщении.", ephemeral=True)

        except discord.NotFound:
            await interaction.response.send_message("Сообщение с таким ID не найдено в канале для парсинга.", ephemeral=True)
        except Exception as e:
            print(f"Ошибка в /point add (id): {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Произошла непредвиденная ошибка: {e}", ephemeral=True)
    
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

