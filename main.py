import os
import discord
import keep_alive
import re
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


# Запускаем веб-сервер для поддержания работы бота
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


keep_alive.keep_alive()
bot.run(os.environ["Token"])

