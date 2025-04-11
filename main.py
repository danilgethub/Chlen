# Основной файл для запуска бота
import os
import discord
import keep_alive
import re
from discord.ext import commands
from datetime import timedelta

# Настройка интентов (разрешений) для бота
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True
intents.presences = True

# Создаем бота
bot = commands.Bot(command_prefix='!', intents=intents)

# Хранилище созданных каналов
created_channels = {}

# Настройки модерации
auto_role_id = None  # ID роли для автовыдачи
allowed_link_roles = set()  # Роли с разрешением на ссылки
mod_enabled = True  # Включена ли модерация ссылок

# Шаблон для поиска ссылок
link_pattern = re.compile(r'(https?://\S+|discord\.gg/\S+|discordapp\.com/invite/\S+)')


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


@bot.event
async def on_member_join(member):
    """Событие срабатывает, когда новый участник присоединяется к серверу"""
    if auto_role_id:
        try:
            # Получаем объект роли по ID
            role = member.guild.get_role(auto_role_id)
            if role:
                await member.add_roles(role)
                print(f"Выдана роль {role.name} участнику {member.display_name}")
        except Exception as e:
            print(f"Ошибка при выдаче роли: {e}")


@bot.event
async def on_message(message):
    """Событие срабатывает при получении нового сообщения"""
    # Игнорируем сообщения от ботов
    if message.author.bot:
        return

    # Проверяем наличие ссылок в сообщении
    if mod_enabled and link_pattern.search(message.content):
        # Проверяем, есть ли у пользователя разрешенная роль
        has_allowed_role = False
        for role in message.author.roles:
            if role.id in allowed_link_roles:
                has_allowed_role = True
                break
        
        # Если нет разрешенной роли - модерируем
        if not has_allowed_role:
            # Удаляем сообщение
            await message.delete()
            
            # Выдаем тайм-аут на 10 минут
            try:
                await message.author.timeout(timedelta(minutes=10), reason="Отправка запрещенных ссылок")
                # Отправляем уведомление
                await message.channel.send(
                    f"{message.author.mention}, отправка ссылок запрещена. Вы получили тайм-аут на 10 минут.",
                    delete_after=10
                )
            except discord.errors.Forbidden:
                # Если у бота не хватает прав для тайм-аута
                await message.channel.send(
                    f"{message.author.mention}, отправка ссылок запрещена.",
                    delete_after=10
                )
    
    # Обрабатываем команды бота
    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member, before, after):
    """Событие срабатывает при изменении голосового состояния пользователя"""
    # ID канала-триггера для создания приватных каналов
    TRIGGER_CHANNEL_ID = '1359162482215616742'  # Замените на ID голосового канала

    # Если пользователь зашел в канал-триггер
    if after.channel and str(after.channel.id) == TRIGGER_CHANNEL_ID:
        guild = member.guild

        # Создаем новый канал
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

        # Перемещаем пользователя в новый канал
        await member.move_to(channel)

        # Сохраняем информацию о канале
        created_channels[channel.id] = {'owner': member.id, 'channel': channel}

        # Создаем View с кнопками и выпадающими меню
        view = PrivateChannelView(channel.id)

        # Отправляем сообщение с кнопками и выпадающими списками
        message = await channel.send('Управление каналом:', view=view)

        # Сохраняем ID сообщения
        created_channels[channel.id]['message_id'] = message.id

    # Если пользователь покинул канал
    if before.channel and before.channel.id in created_channels:
        channel_data = created_channels[before.channel.id]
        channel = channel_data['channel']

        # Если канал пустой, удаляем его
        if len(channel.members) == 0:
            await channel.delete()
            del created_channels[before.channel.id]


# Команды для настройки модерации
@bot.command()
@commands.has_permissions(administrator=True)
async def сет_роль(ctx, role_id: int):
    """Устанавливает роль для автовыдачи новым участникам"""
    global auto_role_id
    
    # Проверяем существование роли
    role = ctx.guild.get_role(role_id)
    if not role:
        return await ctx.send("Роль с указанным ID не найдена!")
    
    auto_role_id = role_id
    await ctx.send(f"Установлена роль для автовыдачи: {role.name}")


@bot.command()
@commands.has_permissions(administrator=True)
async def разрешить_ссылки(ctx, role_id: int):
    """Добавляет роль в список разрешенных для отправки ссылок"""
    global allowed_link_roles
    
    # Проверяем существование роли
    role = ctx.guild.get_role(role_id)
    if not role:
        return await ctx.send("Роль с указанным ID не найдена!")
    
    allowed_link_roles.add(role_id)
    await ctx.send(f"Роль {role.name} добавлена в список разрешенных для отправки ссылок")


@bot.command()
@commands.has_permissions(administrator=True)
async def запретить_ссылки(ctx, role_id: int):
    """Удаляет роль из списка разрешенных для отправки ссылок"""
    global allowed_link_roles
    
    # Проверяем существование роли
    role = ctx.guild.get_role(role_id)
    if not role:
        return await ctx.send("Роль с указанным ID не найдена!")
    
    if role_id in allowed_link_roles:
        allowed_link_roles.remove(role_id)
        await ctx.send(f"Роль {role.name} удалена из списка разрешенных для отправки ссылок")
    else:
        await ctx.send(f"Роль {role.name} не была в списке разрешенных")


@bot.command()
@commands.has_permissions(administrator=True)
async def список_разрешенных(ctx):
    """Показывает список ролей, разрешенных для отправки ссылок"""
    if not allowed_link_roles:
        return await ctx.send("Список разрешенных ролей пуст")
    
    roles_text = ""
    for role_id in allowed_link_roles:
        role = ctx.guild.get_role(role_id)
        role_name = role.name if role else f"(ID: {role_id})"
        roles_text += f"• {role_name}\n"
    
    await ctx.send(f"Роли с разрешением на отправку ссылок:\n{roles_text}")


@bot.command()
@commands.has_permissions(administrator=True)
async def модерация(ctx, state: str):
    """Включает или выключает модерацию ссылок (вкл/выкл)"""
    global mod_enabled
    
    if state.lower() in ['вкл', 'включить', 'on', 'true', 'yes', '1']:
        mod_enabled = True
        await ctx.send("Модерация ссылок включена")
    elif state.lower() in ['выкл', 'выключить', 'off', 'false', 'no', '0']:
        mod_enabled = False
        await ctx.send("Модерация ссылок выключена")
    else:
        await ctx.send("Неверный аргумент. Используйте 'вкл' или 'выкл'")


# Классы View для интерактивных компонентов
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


# Кнопки управления
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


# Запускаем веб-сервер для поддержания работы бота
keep_alive.keep_alive()
bot.run(os.environ["Token"])
