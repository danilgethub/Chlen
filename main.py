import os
import discord
import keep_alive
import re
import datetime
import json
from discord.ext import commands


intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
intents.presences = True


bot = commands.Bot(command_prefix='!', intents=intents)


created_channels = {}

# ID канала, в котором нужно удалять ссылки
LINKS_FILTER_CHANNEL_ID = '1359604943228633399'  

# ID каналов для системы тикетов
TICKET_CHANNEL_ID = None  # ID канала для создания тикетов
TICKET_LOGS_CHANNEL_ID = None  # ID канала для обработки тикетов админами
TICKET_ROLE_ID = None  # ID роли, которая выдается при принятии тикета

# Сохраняем отправленные тикеты
active_tickets = {}

# Функция для сохранения настроек тикетов
def save_ticket_config():
    config = {
        "ticket_channel": TICKET_CHANNEL_ID,
        "logs_channel": TICKET_LOGS_CHANNEL_ID,
        "role_id": TICKET_ROLE_ID
    }
    
    try:
        with open("ticket_config.json", "w") as f:
            json.dump(config, f)
    except Exception as e:
        print(f"Ошибка при сохранении конфигурации тикетов: {e}")

# Функция для загрузки настроек тикетов
def load_ticket_config():
    global TICKET_CHANNEL_ID, TICKET_LOGS_CHANNEL_ID, TICKET_ROLE_ID
    
    try:
        if os.path.exists("ticket_config.json"):
            with open("ticket_config.json", "r") as f:
                config = json.load(f)
                
                TICKET_CHANNEL_ID = config.get("ticket_channel")
                TICKET_LOGS_CHANNEL_ID = config.get("logs_channel")
                TICKET_ROLE_ID = config.get("role_id")
                
                print(f"Загружена конфигурация тикетов: канал заявок: {TICKET_CHANNEL_ID}, канал логов: {TICKET_LOGS_CHANNEL_ID}, роль: {TICKET_ROLE_ID}")
    except Exception as e:
        print(f"Ошибка при загрузке конфигурации тикетов: {e}")

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

    # Загружаем конфигурацию тикетов
    load_ticket_config()

    # Регистрируем постоянные представления для работы с кнопками
    bot.add_view(TicketButtonView())
    
    # Для каждого активного тикета регистрируем представления
    for user_id, ticket_data in active_tickets.items():
        bot.add_view(TicketActionView(user_id))
    
    # Синхронизируем команды с Discord
    try:
        synced = await bot.tree.sync()
        print(f'Синхронизировано {len(synced)} команд')
    except Exception as e:
        print(f'Ошибка синхронизации команд: {e}')


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


# Команды для настройки системы тикетов
@bot.tree.command(name="setup_ticket", description="Настроить систему тикетов (только для администраторов)")
async def setup_ticket(interaction: discord.Interaction, ticket_channel: discord.TextChannel, logs_channel: discord.TextChannel, role: discord.Role):
    """Настраивает систему тикетов"""
    # Проверяем права администратора
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("У вас нет прав на использование этой команды!", ephemeral=True)
    
    global TICKET_CHANNEL_ID, TICKET_LOGS_CHANNEL_ID, TICKET_ROLE_ID
    
    TICKET_CHANNEL_ID = str(ticket_channel.id)
    TICKET_LOGS_CHANNEL_ID = str(logs_channel.id)
    TICKET_ROLE_ID = str(role.id)
    
    # Сохраняем конфигурацию
    save_ticket_config()
    
    await interaction.response.send_message(f"Система тикетов настроена!\nКанал для заявок: {ticket_channel.mention}\nКанал для обработки: {logs_channel.mention}\nРоль при принятии: {role.mention}", ephemeral=True)


@bot.tree.command(name="send_ticket_button", description="Отправить сообщение с кнопкой подачи заявки (только для администраторов)")
async def send_ticket_button(interaction: discord.Interaction, channel: discord.TextChannel = None):
    """Отправляет сообщение с кнопкой для создания тикета"""
    # Проверяем права администратора
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("У вас нет прав на использование этой команды!", ephemeral=True)
    
    global TICKET_CHANNEL_ID
    
    # Если канал не указан, используем текущий
    if not channel:
        channel = interaction.channel
    
    # Обновляем TICKET_CHANNEL_ID
    TICKET_CHANNEL_ID = str(channel.id)
    
    # Сохраняем обновленную конфигурацию
    save_ticket_config()
    
    # Создаем кнопку для создания тикета
    view = TicketButtonView()
    
    # Отправляем сообщение с кнопкой в канал для тикетов
    embed = discord.Embed(
        title="📝 Подать заявку на сервер",
        description="Нажмите на кнопку ниже, чтобы подать заявку на присоединение к серверу.",
        color=discord.Color.blue()
    )
    
    await channel.send(embed=embed, view=view)
    
    await interaction.response.send_message(f"Сообщение с кнопкой для подачи заявки отправлено в канал {channel.mention}!", ephemeral=True)


# Кнопка для создания тикета
class TicketButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Подать заявку", style=discord.ButtonStyle.primary, custom_id="create_ticket")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Открываем модальное окно для заполнения заявки
        await interaction.response.send_modal(TicketModal())


# Модальное окно для заполнения заявки
class TicketModal(discord.ui.Modal, title="Заявка на сервер"):
    username = discord.ui.TextInput(
        label="Ник",
        placeholder="Введите ваш игровой ник",
        required=True
    )
    
    age = discord.ui.TextInput(
        label="Возраст",
        placeholder="Укажите ваш возраст",
        required=True
    )
    
    experience = discord.ui.TextInput(
        label="Опыт игры",
        placeholder="Играли вы на подобных серверах или нет?",
        style=discord.TextStyle.paragraph,
        required=True
    )
    
    adequacy = discord.ui.TextInput(
        label="Адекватность",
        placeholder="Оцените свою адекватность от 1 до 10",
        required=True
    )
    
    plans = discord.ui.TextInput(
        label="Планы на сервере",
        placeholder="Чем планируете заниматься на нашем сервере?",
        style=discord.TextStyle.paragraph,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        global active_tickets, TICKET_LOGS_CHANNEL_ID
        
        if not TICKET_LOGS_CHANNEL_ID:
            return await interaction.response.send_message("Система тикетов не настроена. Обратитесь к администрации.", ephemeral=True)
        
        # Получаем канал для логов
        logs_channel = interaction.guild.get_channel(int(TICKET_LOGS_CHANNEL_ID))
        if not logs_channel:
            return await interaction.response.send_message("Ошибка конфигурации системы тикетов. Обратитесь к администрации.", ephemeral=True)
        
        # Создаем эмбед с информацией о заявке
        embed = discord.Embed(
            title=f"📝 Заявка от {interaction.user.display_name}",
            description=f"**Время подачи:** {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}",
            color=discord.Color.gold()
        )
        
        embed.add_field(name="Ник", value=self.username.value, inline=True)
        embed.add_field(name="Возраст", value=self.age.value, inline=True)
        embed.add_field(name="Адекватность", value=self.adequacy.value, inline=True)
        embed.add_field(name="Опыт игры", value=self.experience.value, inline=False)
        embed.add_field(name="Планы на сервере", value=self.plans.value, inline=False)
        
        # Спрашиваем дополнительные вопросы
        await interaction.response.send_message("Заполните дополнительную информацию:", view=AdditionalQuestionsView(), ephemeral=True)
        
        # Сохраняем данные первой части заявки
        active_tickets[interaction.user.id] = {
            "user": interaction.user,
            "embed": embed,
            "ticket_data": {
                "username": self.username.value,
                "age": self.age.value,
                "experience": self.experience.value,
                "adequacy": self.adequacy.value,
                "plans": self.plans.value
            }
        }


# Вторая часть вопросов
class AdditionalQuestionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)  # Таймаут 5 минут
    
    @discord.ui.button(label="Продолжить", style=discord.ButtonStyle.primary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdditionalQuestionsModal())


class AdditionalQuestionsModal(discord.ui.Modal, title="Дополнительная информация"):
    grief = discord.ui.TextInput(
        label="Отношение к грифу",
        placeholder="Как вы относитесь к грифу?",
        style=discord.TextStyle.paragraph,
        required=True
    )
    
    source = discord.ui.TextInput(
        label="Источник",
        placeholder="Откуда узнали о сервере?",
        style=discord.TextStyle.paragraph,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        global active_tickets, TICKET_LOGS_CHANNEL_ID
        
        if interaction.user.id not in active_tickets:
            return await interaction.response.send_message("Ваша заявка устарела. Пожалуйста, отправьте заявку заново.", ephemeral=True)
        
        # Получаем данные заявки
        ticket_data = active_tickets[interaction.user.id]
        embed = ticket_data["embed"]
        
        # Добавляем дополнительные поля
        embed.add_field(name="Отношение к грифу", value=self.grief.value, inline=False)
        embed.add_field(name="Откуда узнали о сервере", value=self.source.value, inline=False)
        
        # Добавляем информацию о пользователе
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        embed.set_footer(text=f"ID пользователя: {interaction.user.id}")
        
        # Получаем канал для логов
        logs_channel = interaction.guild.get_channel(int(TICKET_LOGS_CHANNEL_ID))
        
        # Создаем кнопки для принятия/отклонения заявки
        view = TicketActionView(interaction.user.id)
        
        # Отправляем заявку в канал для логов
        ticket_message = await logs_channel.send(embed=embed, view=view)
        
        # Сохраняем ID сообщения для дальнейшего управления
        active_tickets[interaction.user.id]["message_id"] = ticket_message.id
        
        await interaction.response.send_message("Ваша заявка успешно отправлена! Ожидайте решения администрации.", ephemeral=True)


# Кнопки для принятия/отклонения заявки
class TicketActionView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id
        
        # Добавляем кнопки с уникальными ID
        accept_button = discord.ui.Button(
            label="Принять", 
            style=discord.ButtonStyle.success, 
            custom_id=f"accept_ticket_{user_id}"
        )
        accept_button.callback = self.accept_ticket
        self.add_item(accept_button)
        
        reject_button = discord.ui.Button(
            label="Отклонить", 
            style=discord.ButtonStyle.danger, 
            custom_id=f"reject_ticket_{user_id}"
        )
        reject_button.callback = self.reject_ticket
        self.add_item(reject_button)
    
    async def accept_ticket(self, interaction: discord.Interaction):
        # Проверяем права администратора
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("У вас нет прав на использование этой команды!", ephemeral=True)
        
        global active_tickets, TICKET_ROLE_ID
        
        if self.user_id not in active_tickets:
            return await interaction.response.send_message("Заявка устарела или уже обработана.", ephemeral=True)
        
        # Получаем пользователя
        user = active_tickets[self.user_id]["user"]
        member = interaction.guild.get_member(user.id)
        
        if not member:
            return await interaction.response.send_message("Пользователь покинул сервер.", ephemeral=True)
        
        # Выдаем роль, если она настроена
        if TICKET_ROLE_ID:
            try:
                role = interaction.guild.get_role(int(TICKET_ROLE_ID))
                if role:
                    await member.add_roles(role)
            except:
                await interaction.response.send_message("Не удалось выдать роль пользователю.", ephemeral=True)
                return
        
        # Обновляем сообщение
        embed = active_tickets[self.user_id]["embed"]
        embed.color = discord.Color.green()
        embed.title = f"✅ Заявка от {user.display_name} (ПРИНЯТА)"
        embed.add_field(name="Принята администратором", value=f"{interaction.user.mention} ({interaction.user.display_name})", inline=False)
        
        # Отключаем кнопки
        for child in self.children:
            child.disabled = True
        
        await interaction.message.edit(embed=embed, view=self)
        
        # Уведомляем пользователя о принятии заявки
        try:
            dm_embed = discord.Embed(
                title="✅ Ваша заявка принята!",
                description="Поздравляем! Ваша заявка на сервер была принята администрацией.",
                color=discord.Color.green()
            )
            await user.send(embed=dm_embed)
        except:
            pass
        
        await interaction.response.send_message(f"Заявка пользователя {user.mention} принята!", ephemeral=True)
        
        # Удаляем заявку из активных
        del active_tickets[self.user_id]
    
    async def reject_ticket(self, interaction: discord.Interaction):
        # Проверяем права администратора
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("У вас нет прав на использование этой команды!", ephemeral=True)
        
        # Открываем модальное окно для указания причины отказа
        await interaction.response.send_modal(RejectReasonModal(self.user_id))


# Модальное окно для указания причины отказа
class RejectReasonModal(discord.ui.Modal, title="Причина отказа"):
    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id
    
    reason = discord.ui.TextInput(
        label="Причина",
        placeholder="Укажите причину отказа",
        style=discord.TextStyle.paragraph,
        required=True
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        global active_tickets
        
        if self.user_id not in active_tickets:
            return await interaction.response.send_message("Заявка устарела или уже обработана.", ephemeral=True)
        
        # Получаем пользователя
        user = active_tickets[self.user_id]["user"]
        
        # Обновляем сообщение
        embed = active_tickets[self.user_id]["embed"]
        embed.color = discord.Color.red()
        embed.title = f"❌ Заявка от {user.display_name} (ОТКЛОНЕНА)"
        embed.add_field(name="Отклонена администратором", value=f"{interaction.user.mention} ({interaction.user.display_name})", inline=False)
        embed.add_field(name="Причина", value=self.reason.value, inline=False)
        
        # Отключаем кнопки
        view = TicketActionView(self.user_id)
        for child in view.children:
            child.disabled = True
        
        await interaction.message.edit(embed=embed, view=view)
        
        # Уведомляем пользователя об отказе
        try:
            dm_embed = discord.Embed(
                title="❌ Ваша заявка отклонена",
                description=f"К сожалению, ваша заявка на сервер была отклонена администрацией.\n\n**Причина:** {self.reason.value}",
                color=discord.Color.red()
            )
            await user.send(embed=dm_embed)
        except:
            pass
        
        await interaction.response.send_message(f"Заявка пользователя {user.mention} отклонена!", ephemeral=True)
        
        # Удаляем заявку из активных
        del active_tickets[self.user_id]


keep_alive.keep_alive()
bot.run(os.environ["Token"])

# Закомментировано, так как, похоже, это дублирование запуска с неверным токеном
# bot.run(os.getenv('1359162482215616742'))
