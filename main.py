import os
import discord
import keep_alive
import re
import json
import datetime
from discord.ext import commands


intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
intents.presences = True


bot = commands.Bot(command_prefix='!', intents=intents)


created_channels = {}
ticket_history = []  # История тикетов

# ID канала, в котором нужно удалять ссылки
LINKS_FILTER_CHANNEL_ID = '1359604943228633399'  
# ID каналов для системы тикетов
TICKETS_CHANNEL_ID = None  # Канал, где будет кнопка создания тикета
TICKETS_LOG_CHANNEL_ID = None  # Канал для админов, куда будут приходить тикеты
ACCEPTED_ROLE_ID = None  # ID роли, которая будет выдаваться при принятии заявки

# Путь к файлу конфигурации
CONFIG_FILE = 'config.json'

# Функции для работы с конфигурацией
def save_config():
    """Сохраняет конфигурацию в файл"""
    config = {
        'links_filter_channel_id': LINKS_FILTER_CHANNEL_ID,
        'tickets_channel_id': TICKETS_CHANNEL_ID,
        'tickets_log_channel_id': TICKETS_LOG_CHANNEL_ID,
        'accepted_role_id': ACCEPTED_ROLE_ID
    }
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
        print(f'Конфигурация сохранена в {CONFIG_FILE}')
    except Exception as e:
        print(f'Ошибка при сохранении конфигурации: {e}')

def load_config():
    """Загружает конфигурацию из файла"""
    global LINKS_FILTER_CHANNEL_ID, TICKETS_CHANNEL_ID, TICKETS_LOG_CHANNEL_ID, ACCEPTED_ROLE_ID, ticket_history
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                
            LINKS_FILTER_CHANNEL_ID = config.get('links_filter_channel_id', LINKS_FILTER_CHANNEL_ID)
            TICKETS_CHANNEL_ID = config.get('tickets_channel_id', TICKETS_CHANNEL_ID)
            TICKETS_LOG_CHANNEL_ID = config.get('tickets_log_channel_id', TICKETS_LOG_CHANNEL_ID)
            ACCEPTED_ROLE_ID = config.get('accepted_role_id', ACCEPTED_ROLE_ID)
            
            # Загружаем историю тикетов, если она есть
            if 'ticket_history' in config:
                ticket_history = config['ticket_history']
            
            print(f'Конфигурация загружена из {CONFIG_FILE}')
        else:
            print(f'Файл конфигурации {CONFIG_FILE} не найден, используются значения по умолчанию')
    except Exception as e:
        print(f'Ошибка при загрузке конфигурации: {e}')

# Загружаем конфигурацию при запуске
load_config()

URL_PATTERN = re.compile(r'https?://\S+|www\.\S+')
DISCORD_INVITE_PATTERN = re.compile(r'discord(?:\.gg|app\.com/invite|\.com/invite)/\S+')

@bot.event
async def on_message(message):
    
    if message.author.bot or str(message.channel.id) != LINKS_FILTER_CHANNEL_ID:
        
        await bot.process_commands(message)
        return
        
    # Проверяем наличие ссылок
    has_url = URL_PATTERN.search(message.content)
    has_discord_invite = DISCORD_INVITE_PATTERN.search(message.content)
    
    if has_url or has_discord_invite:
        
        await message.delete()
        await message.channel.send(
            f"{message.author.mention}, размещение ссылок в этом канале запрещено!",
            delete_after=5  
        )
    else:
        
        await bot.process_commands(message)

@bot.event
async def on_ready():
    """Событие срабатывает при успешном запуске бота"""
    print(f'Бот {bot.user} успешно запущен!')

    # Синхронизируем команды с Discord
    try:
        synced = await bot.tree.sync()
        print(f'Синхронизировано {len(synced)} команд')
    except Exception as e:
        print(f'Ошибка синхронизации команд: {e}')
    
    # Восстанавливаем кнопки для тикетов, если настроены каналы
    if TICKETS_CHANNEL_ID:
        try:
            # Получаем канал для тикетов
            tickets_channel = bot.get_channel(int(TICKETS_CHANNEL_ID))
            if tickets_channel:
                # Проверяем, нет ли уже сообщения с кнопкой
                async for message in tickets_channel.history(limit=50):
                    if message.author == bot.user and message.components:
                        # Если нашли сообщение бота с компонентами, значит кнопка уже есть
                        print(f'Кнопка заявок уже существует в канале {tickets_channel.name}')
                        return
                
                # Если не нашли сообщение с кнопкой, создаем новое
                print(f'Создаем новую кнопку заявок в канале {tickets_channel.name}')
                embed = discord.Embed(
                    title="Подать заявку на вступление на сервер",
                    description="Нажмите на кнопку ниже, чтобы заполнить анкету для вступления на сервер.",
                    color=discord.Color.green()
                )
                view = TicketView()
                await tickets_channel.send(embed=embed, view=view)
        except Exception as e:
            print(f'Ошибка при восстановлении кнопки заявок: {e}')


@bot.event
async def on_voice_state_update(member, before, after):
    """Событие срабатывает при изменении голосового состояния пользователя"""
   
    TRIGGER_CHANNEL_ID = '1359605706289844445'  

    # Если пользователь зашел в канал-триггер
    if after.channel and str(after.channel.id) == TRIGGER_CHANNEL_ID:
        guild = member.guild

        
        channel = await guild.create_voice_channel(
            name=f'🔊 {member.display_name}\'s канал',
            category=after.channel.category,
            overwrites={
                guild.default_role:
                discord.PermissionOverwrite(view_channel=False),
                member:
                discord.PermissionOverwrite(view_channel=True,
                                            connect=True,
                                            speak=True,
                                            stream=True,
                                            use_voice_activation=True,
                                            move_members=True,
                                            manage_channels=True)
            })

        
        await member.move_to(channel)

        
        created_channels[channel.id] = {'owner': member.id, 'channel': channel}

        
        view = PrivateChannelView(channel.id)

        
        message = await channel.send('Управление каналом:', view=view)

        
        created_channels[channel.id]['message_id'] = message.id

    
    if before.channel and before.channel.id in created_channels:
        channel_data = created_channels[before.channel.id]
        channel = channel_data['channel']

       
        if len(channel.members) == 0:
            await channel.delete()
            del created_channels[before.channel.id]


# НАЧАЛО НОВОЙ СИСТЕМЫ ТИКЕТОВ
class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Подать заявку", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TicketModal())

class TicketModal(discord.ui.Modal, title="Заявка на вступление на сервер"):
    nickname = discord.ui.TextInput(
        label="Ник",
        placeholder="Введите ваш никнейм в Minecraft",
        required=True,
        max_length=32
    )
    
    age = discord.ui.TextInput(
        label="Возраст",
        placeholder="Укажите ваш возраст",
        required=True,
        max_length=3
    )
    
    experience = discord.ui.TextInput(
        label="Играли ли вы на подобных серверах?",
        placeholder="Да/Нет, укажите подробности",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=200
    )
    
    adequacy = discord.ui.TextInput(
        label="Оценка адекватности от 1 до 10",
        placeholder="Оцените свою адекватность по шкале от 1 до 10",
        required=True,
        max_length=2
    )
    
    plans = discord.ui.TextInput(
        label="Планы на сервере",
        placeholder="Чем планируете заниматься на нашем сервере?",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=300
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        # Сохраняем данные из первой формы во временном хранилище
        if not hasattr(interaction.client, 'ticket_data'):
            interaction.client.ticket_data = {}
            
        # Сохраняем данные первой формы
        interaction.client.ticket_data[interaction.user.id] = {
            "nickname": self.nickname.value,
            "age": self.age.value,
            "experience": self.experience.value,
            "adequacy": self.adequacy.value,
            "plans": self.plans.value
        }
        
        # Открываем вторую форму для дополнительных полей
        await interaction.response.send_modal(TicketModalPart2())

class TicketModalPart2(discord.ui.Modal, title="Заявка на вступление (продолжение)"):
    griefing = discord.ui.TextInput(
        label="Отношение к грифу",
        placeholder="Как вы относитесь к гриферству?",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=200
    )
    
    source = discord.ui.TextInput(
        label="Откуда узнали о сервере",
        placeholder="Укажите, откуда вы узнали о нашем сервере",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=200
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Ваша заявка принята на рассмотрение! Ожидайте решения администрации.", ephemeral=True)
        
        # Убедимся, что данные из первой формы существуют
        if not hasattr(interaction.client, 'ticket_data') or interaction.user.id not in interaction.client.ticket_data:
            return await interaction.followup.send("Произошла ошибка при обработке заявки. Попробуйте заново.", ephemeral=True)
        
        # Получаем данные из первой формы
        ticket_data = interaction.client.ticket_data[interaction.user.id]
        
        # Получаем канал для логов тикетов
        tickets_log_channel = interaction.client.get_channel(int(TICKETS_LOG_CHANNEL_ID) if TICKETS_LOG_CHANNEL_ID else None)
        
        if not tickets_log_channel:
            return await interaction.followup.send("Ошибка: канал для тикетов не настроен. Обратитесь к администратору.", ephemeral=True)
        
        # Создаем эмбед с информацией из тикета
        embed = discord.Embed(
            title=f"Заявка от {interaction.user.display_name}",
            description=f"Пользователь: {interaction.user.mention} (ID: {interaction.user.id})",
            color=discord.Color.blue()
        )
        
        # Добавляем все поля из формы
        embed.add_field(name="Ник", value=ticket_data["nickname"], inline=True)
        embed.add_field(name="Возраст", value=ticket_data["age"], inline=True)
        embed.add_field(name="Опыт на подобных серверах", value=ticket_data["experience"], inline=False)
        embed.add_field(name="Самооценка адекватности", value=ticket_data["adequacy"], inline=True)
        embed.add_field(name="Планы на сервере", value=ticket_data["plans"], inline=False)
        embed.add_field(name="Отношение к грифу", value=self.griefing.value, inline=False)
        embed.add_field(name="Откуда узнал о сервере", value=self.source.value, inline=False)
        
        # Создаем кнопки для принятия/отклонения заявки
        view = TicketResponseView(interaction.user.id)
        
        # Отправляем в канал для тикетов
        await tickets_log_channel.send(embed=embed, view=view)
        
        # Очищаем временные данные
        del interaction.client.ticket_data[interaction.user.id]

class TicketResponseView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        
    @discord.ui.button(label="Принять", style=discord.ButtonStyle.success, custom_id="accept_ticket")
    async def accept_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверяем, есть ли у пользователя права администратора
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("У вас нет прав для принятия заявок!", ephemeral=True)
        
        # Получаем пользователя и выдаем роль
        guild = interaction.guild
        member = guild.get_member(self.user_id)
        
        if not member:
            return await interaction.response.send_message("Пользователь не найден на сервере!", ephemeral=True)
        
        # Получаем роль из глобальной переменной
        role_id = ACCEPTED_ROLE_ID
        
        if role_id:
            role = guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role)
                    await interaction.response.send_message(f"Заявка принята! Роль {role.name} выдана пользователю {member.display_name}.")
                except discord.Forbidden:
                    await interaction.response.send_message("Не удалось выдать роль. Недостаточно прав.", ephemeral=True)
            else:
                await interaction.response.send_message("Роль не найдена. Заявка принята, но роль не выдана.", ephemeral=True)
        else:
            await interaction.response.send_message(f"Заявка принята! Пользователю {member.display_name} нужно выдать роль вручную.", ephemeral=False)
        
        # Отключаем все кнопки
        for child in self.children:
            child.disabled = True
        
        await interaction.message.edit(view=self)
        
        # Добавляем запись в историю тикетов
        # Получаем имя из эмбеда
        embed = interaction.message.embeds[0]
        nickname = ""
        age = ""
        for field in embed.fields:
            if field.name == "Ник":
                nickname = field.value
            elif field.name == "Возраст":
                age = field.value
        
        add_ticket_history(self.user_id, nickname, age, 'accepted', interaction.user.id)
        
        # Оповещаем пользователя
        try:
            await member.send(f"Ваша заявка на сервере {guild.name} была одобрена! Добро пожаловать!")
        except:
            pass
    
    @discord.ui.button(label="Отклонить", style=discord.ButtonStyle.danger, custom_id="reject_ticket")
    async def reject_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Проверяем, есть ли у пользователя права администратора
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("У вас нет прав для отклонения заявок!", ephemeral=True)
        
        # Отклоняем заявку
        await interaction.response.send_message(f"Заявка от <@{self.user_id}> отклонена.")
        
        # Отключаем все кнопки
        for child in self.children:
            child.disabled = True
        
        await interaction.message.edit(view=self)
        
        # Добавляем запись в историю тикетов
        # Получаем имя из эмбеда
        embed = interaction.message.embeds[0]
        nickname = ""
        age = ""
        for field in embed.fields:
            if field.name == "Ник":
                nickname = field.value
            elif field.name == "Возраст":
                age = field.value
        
        add_ticket_history(self.user_id, nickname, age, 'rejected', interaction.user.id)
        
        # Оповещаем пользователя
        member = interaction.guild.get_member(self.user_id)
        if member:
            try:
                await member.send(f"Ваша заявка на сервере {interaction.guild.name} была отклонена.")
            except:
                pass

# Команда для создания сообщения с кнопкой тикета
@bot.tree.command(name="setup_tickets", description="Настроить систему заявок (только для администраторов)")
async def setup_tickets(interaction: discord.Interaction, tickets_channel: discord.TextChannel, logs_channel: discord.TextChannel, role: discord.Role = None):
    # Проверяем права администратора
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("У вас нет прав на выполнение этой команды!", ephemeral=True)
    
    global TICKETS_CHANNEL_ID, TICKETS_LOG_CHANNEL_ID, ACCEPTED_ROLE_ID
    
    # Сохраняем ID каналов
    TICKETS_CHANNEL_ID = str(tickets_channel.id)
    TICKETS_LOG_CHANNEL_ID = str(logs_channel.id)
    if role:
        ACCEPTED_ROLE_ID = str(role.id)
    
    # Сохраняем конфигурацию
    save_config()
    
    # Создаем сообщение с кнопкой
    embed = discord.Embed(
        title="Подать заявку на вступление на сервер",
        description="Нажмите на кнопку ниже, чтобы заполнить анкету для вступления на сервер.",
        color=discord.Color.green()
    )
    
    view = TicketView()
    
    await tickets_channel.send(embed=embed, view=view)
    await interaction.response.send_message(f"Система заявок успешно настроена!\nКанал заявок: {tickets_channel.mention}\nКанал логов: {logs_channel.mention}\nРоль для принятых: {role.mention if role else 'Не указана'}", ephemeral=True)

# КОНЕЦ НОВОЙ СИСТЕМЫ ТИКЕТОВ

class PrivateChannelView(discord.ui.View):

    def __init__(self, channel_id):
        super().__init__(timeout=None)
        self.channel_id = channel_id

        # Добавляем кнопки и выпадающие меню
        self.add_item(LockChannelButton())
        self.add_item(UnlockChannelButton())
        self.add_item(LimitButton())
        self.add_item(DeleteButton())
        self.add_item(RenameSelect())
        self.add_item(MemberActionSelect())



class LockChannelButton(discord.ui.Button):

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary,
                         label='Закрыть канал',
                         custom_id='lock_channel')

    async def callback(self, interaction: discord.Interaction):
        channel_id = self.view.channel_id

        if channel_id not in created_channels:
            return await interaction.response.send_message('Канал не найден!',
                                                           ephemeral=True)

        channel_data = created_channels[channel_id]

        if interaction.user.id != channel_data['owner']:
            return await interaction.response.send_message(
                'Только владелец канала может управлять им!', ephemeral=True)

        channel = channel_data['channel']
        await channel.set_permissions(interaction.guild.default_role,
                                      view_channel=True,
                                      connect=False)
        await interaction.response.send_message(
            'Канал закрыт! Теперь никто не сможет в него войти.',
            ephemeral=True)


class UnlockChannelButton(discord.ui.Button):

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.success,
                         label='Открыть канал',
                         custom_id='unlock_channel')

    async def callback(self, interaction: discord.Interaction):
        channel_id = self.view.channel_id

        if channel_id not in created_channels:
            return await interaction.response.send_message('Канал не найден!',
                                                           ephemeral=True)

        channel_data = created_channels[channel_id]

        if interaction.user.id != channel_data['owner']:
            return await interaction.response.send_message(
                'Только владелец канала может управлять им!', ephemeral=True)

        channel = channel_data['channel']
        await channel.set_permissions(interaction.guild.default_role,
                                      view_channel=True,
                                      connect=True)
        await interaction.response.send_message(
            'Канал открыт! Теперь все могут войти.', ephemeral=True)


class LimitButton(discord.ui.Button):

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary,
                         label='Лимит',
                         custom_id='limit')

    async def callback(self, interaction: discord.Interaction):
        try:
            channel_id = self.view.channel_id

            if channel_id not in created_channels:
                return await interaction.response.send_message('Канал не найден!',
                                                               ephemeral=True)

            channel_data = created_channels[channel_id]

            if interaction.user.id != channel_data['owner']:
                return await interaction.response.send_message(
                    'Только владелец канала может управлять им!', ephemeral=True)

            # Создаем модальное окно для ввода лимита
            modal = LimitModal(self.view.channel_id)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"Ошибка при обработке кнопки лимита: {e}")
            try:
                await interaction.response.send_message(
                    'Произошла ошибка при обработке кнопки. Попробуйте позже.',
                    ephemeral=True)
            except:
                # Если первый ответ уже был отправлен, используем followup
                await interaction.followup.send(
                    'Произошла ошибка при обработке кнопки. Попробуйте позже.',
                    ephemeral=True)


class DeleteButton(discord.ui.Button):

    def __init__(self):
        super().__init__(style=discord.ButtonStyle.danger,
                         label='Удалить',
                         custom_id='delete')

    async def callback(self, interaction: discord.Interaction):
        channel_id = self.view.channel_id

        if channel_id not in created_channels:
            return await interaction.response.send_message('Канал не найден!',
                                                           ephemeral=True)

        channel_data = created_channels[channel_id]

        if interaction.user.id != channel_data['owner']:
            return await interaction.response.send_message(
                'Только владелец канала может управлять им!', ephemeral=True)

        channel = channel_data['channel']
        await channel.delete()
        del created_channels[channel_id]


# Выпадающие меню
class RenameSelect(discord.ui.Select):

    def __init__(self):
        options = [
            discord.SelectOption(label='Стандартное',
                                 value='default',
                                 description='Вернуть стандартное название'),
            discord.SelectOption(label='Игровой',
                                 value='gaming',
                                 description='Название для игр'),
            discord.SelectOption(label='Музыкальный',
                                 value='music',
                                 description='Название для музыки'),
            discord.SelectOption(label='Своё название',
                                 value='custom',
                                 description='Задать своё название каналу')
        ]
        super().__init__(placeholder='Изменить название',
                         min_values=1,
                         max_values=1,
                         options=options,
                         custom_id='rename')

    async def callback(self, interaction: discord.Interaction):
        channel_id = self.view.channel_id

        if channel_id not in created_channels:
            return await interaction.response.send_message('Канал не найден!',
                                                           ephemeral=True)

        channel_data = created_channels[channel_id]

        if interaction.user.id != channel_data['owner']:
            return await interaction.response.send_message(
                'Только владелец канала может управлять им!', ephemeral=True)

        channel = channel_data['channel']
        new_name_type = self.values[0]

        if new_name_type == 'custom':
            # Создаем модальное окно для ввода своего названия
            modal = CustomNameModal(self.view.channel_id)
            await interaction.response.send_modal(modal)
        else:
            channel_name = ''
            if new_name_type == 'default':
                channel_name = f'🔊 {interaction.user.display_name}\'s канал'
            elif new_name_type == 'gaming':
                channel_name = f'🎮 {interaction.user.display_name}\'s игровой'
            elif new_name_type == 'music':
                channel_name = f'🎵 {interaction.user.display_name}\'s музыкальный'

            await channel.edit(name=channel_name)
            await interaction.response.send_message(
                f'Название канала изменено на "{channel_name}"!',
                ephemeral=True)


class MemberActionSelect(discord.ui.Select):

    def __init__(self):
        options = [
            discord.SelectOption(label='Кикнуть игрока',
                                 value='kick',
                                 description='Выгнать игрока из канала'),
            discord.SelectOption(label='Забанить игрока',
                                 value='ban',
                                 description='Запретить игроку вход в канал')
        ]
        super().__init__(placeholder='Управление участниками',
                         min_values=1,
                         max_values=1,
                         options=options,
                         custom_id='member_action')

    async def callback(self, interaction: discord.Interaction):
        channel_id = self.view.channel_id

        if channel_id not in created_channels:
            return await interaction.response.send_message('Канал не найден!',
                                                           ephemeral=True)

        channel_data = created_channels[channel_id]

        if interaction.user.id != channel_data['owner']:
            return await interaction.response.send_message(
                'Только владелец канала может управлять им!', ephemeral=True)

        channel = channel_data['channel']
        action = self.values[0]

        # Получаем список участников канала (кроме владельца)
        members = [m for m in channel.members if m.id != channel_data['owner']]

        if not members:
            return await interaction.response.send_message(
                'В канале нет других участников!', ephemeral=True)

        # Создаем выпадающее меню для выбора участника
        view = discord.ui.View()
        select = MemberSelect(members, action, channel_id)
        view.add_item(select)

        await interaction.response.send_message(
            'Выберите игрока для ' +
            ('кика:' if action == 'kick' else 'бана:'),
            view=view,
            ephemeral=True)


class MemberSelect(discord.ui.Select):

    def __init__(self, members, action, channel_id):
        self.action = action
        self.channel_id = channel_id

        options = []
        for member in members:
            options.append(
                discord.SelectOption(label=member.display_name,
                                     value=f"{action}_{member.id}",
                                     description=str(member)))

        super().__init__(placeholder='Выберите участника',
                         min_values=1,
                         max_values=1,
                         options=options,
                         custom_id='member_select')

    async def callback(self, interaction: discord.Interaction):
        if self.channel_id not in created_channels:
            return await interaction.response.send_message('Канал не найден!',
                                                           ephemeral=True)

        channel_data = created_channels[self.channel_id]

        if interaction.user.id != channel_data['owner']:
            return await interaction.response.send_message(
                'Только владелец канала может управлять им!', ephemeral=True)

        channel = channel_data['channel']
        action, user_id = self.values[0].split('_')
        member = interaction.guild.get_member(int(user_id))

        if not member:
            return await interaction.response.send_message(
                'Участник не найден!', ephemeral=True)

        if action == 'kick':
            if member.voice and member.voice.channel and member.voice.channel.id == channel.id:
                await member.move_to(None)
            await interaction.response.send_message(
                f'{member.display_name} кикнут из канала!', ephemeral=True)
        elif action == 'ban':
            await channel.set_permissions(member,
                                          view_channel=False,
                                          connect=False)
            if member.voice and member.voice.channel and member.voice.channel.id == channel.id:
                await member.move_to(None)
            await interaction.response.send_message(
                f'{member.display_name} забанен в канале!', ephemeral=True)


# Модальные окна
class CustomNameModal(discord.ui.Modal, title='Введите название канала'):

    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    channel_name = discord.ui.TextInput(
        label='Новое название',
        placeholder='Введите новое название канала',
        min_length=1,
        max_length=30,
        required=True)

    async def on_submit(self, interaction: discord.Interaction):
        if self.channel_id not in created_channels:
            return await interaction.response.send_message('Канал не найден!',
                                                           ephemeral=True)

        channel_data = created_channels[self.channel_id]

        if interaction.user.id != channel_data['owner']:
            return await interaction.response.send_message(
                'Только владелец канала может управлять им!', ephemeral=True)

        channel = channel_data['channel']
        await channel.edit(name=self.channel_name.value)
        await interaction.response.send_message(
            f'Название канала изменено на "{self.channel_name.value}"!',
            ephemeral=True)


class LimitModal(discord.ui.Modal, title='Установить лимит участников'):

    def __init__(self, channel_id):
        super().__init__()
        self.channel_id = channel_id

    limit = discord.ui.TextInput(label='Количество участников',
                                 placeholder='Введите число от 1 до 99',
                                 min_length=1,
                                 max_length=2,
                                 required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if self.channel_id not in created_channels:
                return await interaction.response.send_message('Канал не найден!',
                                                               ephemeral=True)

            channel_data = created_channels[self.channel_id]

            if interaction.user.id != channel_data['owner']:
                return await interaction.response.send_message(
                    'Только владелец канала может управлять им!', ephemeral=True)

            channel = channel_data['channel']

            try:
                limit = int(self.limit.value)
                if limit < 1 or limit > 99:
                    return await interaction.response.send_message(
                        'Пожалуйста, введите число от 1 до 99!', ephemeral=True)

                await channel.edit(user_limit=limit)
                await interaction.response.send_message(
                    f'Лимит участников установлен: {limit}', ephemeral=True)
            except ValueError:
                await interaction.response.send_message(
                    'Пожалуйста, введите число от 1 до 99!', ephemeral=True)
        except Exception as e:
            print(f"Ошибка при установке лимита: {e}")
            await interaction.response.send_message(
                'Произошла ошибка при установке лимита. Попробуйте позже.',
                ephemeral=True)


# Функция для добавления записи в историю тикетов
def add_ticket_history(user_id, nickname, age, decision, decider_id):
    """Добавляет запись в историю тикетов"""
    ticket_record = {
        'user_id': user_id,
        'nickname': nickname,
        'age': age,
        'decision': decision,  # 'accepted' или 'rejected'
        'decider_id': decider_id,
        'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    
    ticket_history.append(ticket_record)
    
    # Сохраняем обновленную историю
    config = {}
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        
        config['ticket_history'] = ticket_history
        
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        print(f'Ошибка при сохранении истории тикетов: {e}')

# Команда для просмотра истории тикетов
@bot.tree.command(name="tickets_history", description="Просмотр истории заявок (только для администраторов)")
async def tickets_history(interaction: discord.Interaction, status: str = None):
    """
    Команда для просмотра истории заявок
    
    Параметры:
    status: Статус заявок для отображения (all, accepted, rejected)
    """
    # Проверяем права администратора
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("У вас нет прав на выполнение этой команды!", ephemeral=True)
    
    # Проверяем указанный статус
    if status and status.lower() not in ['all', 'accepted', 'rejected']:
        return await interaction.response.send_message("Неверный статус. Используйте all, accepted или rejected.", ephemeral=True)
    
    # Если статус не указан, показываем все заявки
    if not status:
        status = 'all'
    
    # Фильтруем историю по статусу
    filtered_history = []
    if status.lower() == 'all':
        filtered_history = ticket_history
    elif status.lower() == 'accepted':
        filtered_history = [ticket for ticket in ticket_history if ticket['decision'] == 'accepted']
    elif status.lower() == 'rejected':
        filtered_history = [ticket for ticket in ticket_history if ticket['decision'] == 'rejected']
    
    # Если история пуста
    if not filtered_history:
        return await interaction.response.send_message(f"История заявок ({status}) пуста.", ephemeral=True)
    
    # Создаем эмбед для отображения истории
    embed = discord.Embed(
        title=f"История заявок ({status})",
        description=f"Всего заявок: {len(filtered_history)}",
        color=discord.Color.blue()
    )
    
    # Отображаем только последние 10 записей
    for i, ticket in enumerate(filtered_history[-10:]):
        user_id = ticket['user_id']
        nickname = ticket['nickname']
        age = ticket['age']
        decision = "Принята" if ticket['decision'] == 'accepted' else "Отклонена"
        decider_id = ticket['decider_id']
        timestamp = ticket['timestamp']
        
        embed.add_field(
            name=f"{i+1}. {nickname} ({age} лет)",
            value=f"Статус: {decision}\nКем: <@{decider_id}>\nКогда: {timestamp}",
            inline=False
        )
    
    # Если записей больше 10, добавляем примечание
    if len(filtered_history) > 10:
        embed.set_footer(text=f"Показаны последние 10 из {len(filtered_history)} записей")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

keep_alive.keep_alive()
# Используем токен напрямую
bot.run("MTM1OTE1MzEyMjI3ODI0ODY0NA.GiMsry.Zt9_Rw7qQ8W0PvwXuNoizRiiNR0duJhS3Be8Yw")
