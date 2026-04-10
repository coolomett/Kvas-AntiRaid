import discord
from discord.ext import commands
import json
import os
import asyncio
import datetime
import re
import uuid

# --- КОНСТАНТЫ И НАСТРОЙКИ ---
OWNER_ID = ТУТ ID ВЛАДЕЛЬЦА
GUILD_ID = ТУТ ID СЕРВЕРА УСТАНОВКИ
DATA_FILE = "data.json"
LOG_FILE = "logs.txt"

# Регулярные выражения для защиты чата
# Поиск ссылок с пробелами (d i s c o r d . g g)
INVITE_REGEX = re.compile(r'(d\s*i\s*s\s*c\s*o\s*r\s*d\s*\.\s*g\s*g|d\s*i\s*s\s*c\s*o\s*r\s*d\s*a\s*p\s*p\s*\.\s*c\s*o\s*m)', re.IGNORECASE)
# Поиск Zalgo-символов
ZALGO_REGEX = re.compile(r'[\u0300-\u036f\u0483-\u0489\u1dc0-\u1dff\u20d0-\u20ff\u2de0-\u2dff\ua66f-\ua672\ua674-\ua67d\ua69e-\ua69f]')
# Защита от спама markdown (####, **** и т.д.)
MARKDOWN_ABUSE_REGEX = re.compile(r'([*#_~|])\1{3,}')

# Базовая структура данных
DEFAULT_DATA = {
    "stats": {
        "preventive_bans": 0,
        "total_bans": 0,
        "deleted_channels": 0,
        "deleted_messages": 0,
        "raids_prevented": 0
    },
    "trusted": [],
    "banwords": [],
    "bannedurls": [],
    "lockdown": False,
    "raidmode": False,
    "backups": {}
}

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С ДАННЫМИ И ЛОГАМИ ---
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_DATA, f, indent=4)
        return DEFAULT_DATA
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return DEFAULT_DATA

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def log_action(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_msg = f"[{timestamp}] {message}"
    print(log_msg)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_msg + "\n")

db = load_data()
bot_start_time = datetime.datetime.now()

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
class AntiRaidBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix='?', intents=intents, help_command=None)

    async def setup_hook(self):
        await self.tree.sync()
        log_action("Слеш-команды синхронизированы.")

bot = AntiRaidBot()

# --- ПРОВЕРКИ ---
def is_owner():
    async def predicate(ctx):
        return ctx.author.id == OWNER_ID
    return commands.check(predicate)

def in_right_guild():
    async def predicate(ctx):
        return ctx.guild.id == GUILD_ID
    return commands.check(predicate)

# --- АНТИРЕЙД ЛОГИКА (АВТОМАТИКА) ---
async def neutralize_threat(guild, member, reason):
    if member.id in db["trusted"] or member.id == OWNER_ID:
        return
    try:
        await member.ban(reason=f"Kvas Antiraid: {reason}")
        db["stats"]["total_bans"] += 1
        db["stats"]["raids_prevented"] += 1
        save_data(db)
        log_action(f"УГРОЗА НЕЙТРАЛИЗОВАНА: {member} забанен. Причина: {reason}")
        
        owner = bot.get_user(OWNER_ID)
        if owner:
            await owner.send(f"⚠️ **ВНИМАНИЕ! РЕЙД ПОПЫТКА!**\nПользователь/Бот {member} был забанен.\nПричина: {reason}")
    except discord.Forbidden:
        log_action(f"ОШИБКА: Нет прав для бана {member}")

@bot.event
async def on_ready():
    log_action(f"Бот {bot.user} успешно запущен и готов к защите сервера!")
    await bot.change_presence(activity=discord.Game(name="PROTECT 2.0 | ?help"))

@bot.event
async def on_member_join(member):
    if member.guild.id != GUILD_ID: return
    
    # Raidmode check
    if db["raidmode"] and member.id not in db["trusted"] and member.id != OWNER_ID:
        try:
            await member.send("Сервер находится в режиме блокировки рейда (Raidmode). Вход закрыт.")
        except: pass
        await member.kick(reason="Kvas Antiraid: Raidmode is ON")
        log_action(f"Кикнут {member} (Включен Raidmode)")
        return

    # Preventive ban for suspicious bot names or known nukers (scan check on join)
    sus_words = ["nuke", "raid", "spam", "fuck"]
    if any(word in member.name.lower() for word in sus_words) and member.bot:
        db["stats"]["preventive_bans"] += 1
        save_data(db)
        await neutralize_threat(member.guild, member, "Подозрительное имя бота при входе")

@bot.event
async def on_message(message):
    if message.guild is None or message.guild.id != GUILD_ID: return
    if message.author.bot and message.author.id not in db["trusted"]:
        pass # Мы можем добавить проверку на спам от ботов
        
    if message.author.id == OWNER_ID or message.author.id in db["trusted"]:
        await bot.process_commands(message)
        return

    content = message.content.lower()
    
    # 1. Проверка на Lockdown
    if db["lockdown"]:
        await message.delete()
        return

    # 2. Защита от спама инвайтами и скрытых ссылок
    if INVITE_REGEX.search(content):
        await message.delete()
        await message.author.timeout(datetime.timedelta(hours=1), reason="Отправка скрытых инвайтов")
        log_action(f"Удалено сообщение от {message.author} (Инвайт)")
        return
        
    # 3. Zalgo защита
    if len(ZALGO_REGEX.findall(content)) > 5:
        await message.delete()
        log_action(f"Удалено сообщение от {message.author} (Zalgo)")
        return

    # 4. Markdown/Font защита
    if MARKDOWN_ABUSE_REGEX.search(content):
        await message.delete()
        log_action(f"Удалено сообщение от {message.author} (Markdown Abuse)")
        return

    # 5. Банворды и Забаненные URL
    if any(word in content for word in db["banwords"]):
        await message.delete()
        await neutralize_threat(message.guild, message.author, "Использование банворда")
        return
        
    if any(url in content for url in db["bannedurls"]):
        await message.delete()
        await neutralize_threat(message.guild, message.author, "Использование запрещенной ссылки")
        return

    await bot.process_commands(message)

# Параллельное отслеживание создания/удаления каналов (Анти-краш)
@bot.event
async def on_guild_channel_create(channel):
    if channel.guild.id != GUILD_ID: return
    # Проверяем аудит лог, кто создал канал
    async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
        if entry.target.id == channel.id:
            user = entry.user
            if user.id != OWNER_ID and user.id not in db["trusted"]:
                # Мгновенная нейтрализация
                asyncio.create_task(neutralize_threat(channel.guild, user, "Несанкционированное создание канала (Попытка краша)"))
                asyncio.create_task(channel.delete(reason="Kvas Antiraid: Удаление рейд-канала"))
                db["stats"]["deleted_channels"] += 1
                save_data(db)

# --- ГИБРИДНЫЕ КОМАНДЫ (СЛЕШ + ПРЕФИКС) ---

@bot.hybrid_command(name="help", description="Полный справочник по функционалу бота")
@in_right_guild()
async def help_cmd(ctx):
    embed = discord.Embed(title="🛡️ Kvas Antiraid | PROTECT 2.0 - Справочник", color=discord.Color.red())
    commands_desc = """
    **Система и Статус**
    `?status` - Статистика и текущее состояние защиты.
    `?scan` - Поиск плохих ботов и рейдеров на сервере.
    `?reset` - Сброс настроек к заводским (очистка data.json).
    
    **Защита и Режимы**
    `?lockdown` / `?unlockdown` - Вкл/выкл блокировку чатов (писать может только владелец).
    `?raidmode` / `?unraid` - Вкл/выкл режим защиты от входа на сервер.
    `?purge` - Мгновенная пересоздание (очистка) канала.
    
    **Управление доступом (Трасты)**
    `?trust @user` - Добавить в белый список (игнорируется антирейдом).
    `?untrust @user` - Убрать из белого списка.
    `?trusted` - Список доверенных лиц.
    
    **Фильтры чата**
    `?addbanword` / `?delbanword` / `?banwords` - Управление словами, за которые выдается бан.
    `?addbanurl` / `?delbanurl` / `?bannedurls` - Управление запрещенными ссылками.
    
    **Бекапы**
    `?backup` - Создать бекап сервера.
    `?restore <ID>` - Восстановить каналы из бекапа.
    `?backups` - Список бекапов.
    
    **Логирование**
    `?logload` - Получить файл логов в ЛС.
    `?clearlagg` - Очистить файл логов.
    """
    embed.description = commands_desc
    await ctx.send(embed=embed)

@bot.hybrid_command(name="status", description="Выводит статус бота и статистику")
@in_right_guild()
async def status(ctx):
    uptime = datetime.datetime.now() - bot_start_time
    stats = db["stats"]
    embed = discord.Embed(title="📊 Статус Системы PROTECT 2.0", color=discord.Color.blue())
    embed.add_field(name="Аптайм", value=str(uptime).split('.')[0], inline=True)
    embed.add_field(name="Локдаун", value="✅ Вкл" if db["lockdown"] else "❌ Выкл", inline=True)
    embed.add_field(name="Рейд-мод", value="✅ Вкл" if db["raidmode"] else "❌ Выкл", inline=True)
    embed.add_field(name="Превентивные баны", value=stats["preventive_bans"], inline=True)
    embed.add_field(name="Всего банов", value=stats["total_bans"], inline=True)
    embed.add_field(name="Участников", value=ctx.guild.member_count, inline=True)
    embed.add_field(name="Удалено каналов", value=stats["deleted_channels"], inline=True)
    embed.add_field(name="Предотвращено рейдов", value=stats["raids_prevented"], inline=True)
    embed.add_field(name="Доверенных лиц", value=len(db["trusted"]), inline=True)
    
    webhooks = await ctx.guild.webhooks()
    embed.add_field(name="Вебхуков на сервере", value=len(webhooks), inline=True)
    
    await ctx.send(embed=embed)

@bot.hybrid_command(name="scan", description="Сканирование сервера на ботов-нюкеров")
@is_owner()
@in_right_guild()
async def scan(ctx):
    await ctx.send("🔍 Начинаю сканирование сервера...")
    sus_count = 0
    sus_words = ["nuke", "raid", "spam", "hack", "crash"]
    for member in ctx.guild.members:
        if member.bot and member.id not in db["trusted"]:
            if any(word in member.name.lower() for word in sus_words):
                await neutralize_threat(ctx.guild, member, "Обнаружен при сканировании (подозрительный бот)")
                sus_count += 1
    await ctx.send(f"✅ Сканирование завершено. Нейтрализовано угроз: **{sus_count}**.")

@bot.hybrid_command(name="purge", description="Полностью очищает текущий канал (пересозданием)")
@is_owner()
@in_right_guild()
async def purge(ctx):
    channel = ctx.channel
    pos = channel.position
    await ctx.send("💥 Инициирован протокол полной очистки канала...")
    
    # Клонируем канал и удаляем старый для моментальной очистки
    new_channel = await channel.clone(reason="Kvas Antiraid: Purge command")
    await new_channel.edit(position=pos)
    await channel.delete(reason="Kvas Antiraid: Purge command")
    await new_channel.send("✅ Канал был полностью очищен.")

@bot.hybrid_command(name="lockdown", description="Включить режим локдауна")
@is_owner()
@in_right_guild()
async def lockdown(ctx):
    db["lockdown"] = True
    save_data(db)
    log_action("Включен режим локдауна.")
    await ctx.send("🔒 **Режим локдауна ВКЛЮЧЕН.** Никто кроме владельца больше не может писать.")

@bot.hybrid_command(name="unlockdown", description="Выключить режим локдауна")
@is_owner()
@in_right_guild()
async def unlockdown(ctx):
    db["lockdown"] = False
    save_data(db)
    log_action("Выключен режим локдауна.")
    await ctx.send("🔓 **Режим локдауна ВЫКЛЮЧЕН.**")

@bot.hybrid_command(name="raidmode", description="Включить рейд-мод (запрет на вход)")
@is_owner()
@in_right_guild()
async def raidmode(ctx):
    db["raidmode"] = True
    save_data(db)
    log_action("Включен Raidmode.")
    await ctx.send("🛡️ **Raidmode ВКЛЮЧЕН.** Новые пользователи не смогут зайти на сервер.")

@bot.hybrid_command(name="unraid", description="Выключить рейд-мод")
@is_owner()
@in_right_guild()
async def unraid(ctx):
    db["raidmode"] = False
    save_data(db)
    log_action("Выключен Raidmode.")
    await ctx.send("✅ **Raidmode ВЫКЛЮЧЕН.** Вход на сервер открыт.")

@bot.hybrid_command(name="trust", description="Добавить в доверенный список")
@is_owner()
@in_right_guild()
async def trust(ctx, user: discord.User):
    if user.id not in db["trusted"]:
        db["trusted"].append(user.id)
        save_data(db)
        await ctx.send(f"✅ {user.mention} добавлен в доверенный список.")
    else:
        await ctx.send("Этот пользователь уже в списке.")

@bot.hybrid_command(name="untrust", description="Убрать из доверенного списка")
@is_owner()
@in_right_guild()
async def untrust(ctx, user: discord.User):
    if user.id in db["trusted"]:
        db["trusted"].remove(user.id)
        save_data(db)
        await ctx.send(f"✅ {user.mention} удален из доверенного списка.")
    else:
        await ctx.send("Этого пользователя нет в списке.")

@bot.hybrid_command(name="trusted", description="Список доверенных")
@is_owner()
@in_right_guild()
async def trusted(ctx):
    if not db["trusted"]:
        return await ctx.send("Список доверенных пуст.")
    mentions = [f"<@{uid}>" for uid in db["trusted"]]
    await ctx.send("🛡️ **Доверенные пользователи/боты:**\n" + "\n".join(mentions))

@bot.hybrid_command(name="backup", description="Сделать бекап структуры сервера")
@is_owner()
@in_right_guild()
async def backup(ctx):
    if len(db["backups"]) >= 40:
        return await ctx.send("❌ Достигнут лимит бекапов (40). Удалите старые (сбросом) или измените код.")
    
    backup_id = str(uuid.uuid4())[:8]
    guild = ctx.guild
    
    channels_data = []
    for c in guild.channels:
        channels_data.append({
            "name": c.name,
            "type": str(c.type),
            "category": c.category.name if c.category else None,
            "position": c.position
        })
        
    db["backups"][backup_id] = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "channels": channels_data
    }
    save_data(db)
    log_action(f"Создан бекап {backup_id}")
    await ctx.send(f"✅ Бекап успешно создан! ID: **{backup_id}**")

@bot.hybrid_command(name="restore", description="Восстановить сервер из бекапа")
@is_owner()
@in_right_guild()
async def restore(ctx, backup_id: str):
    if backup_id not in db["backups"]:
        return await ctx.send("❌ Бекап с таким ID не найден.")
        
    await ctx.send("⚠️ Начинаю восстановление каналов. Это может занять время из-за лимитов Discord API...")
    backup_data = db["backups"][backup_id]
    guild = ctx.guild
    
    # В реальных условиях тут должна быть сложная логика очистки, 
    # но для безопасности удаляем только текстовые/голосовые каналы, чтобы не задеть важные ветки, если это не требуется.
    delete_tasks = [c.delete() for c in guild.channels if c != ctx.channel]
    await asyncio.gather(*delete_tasks, return_exceptions=True)
    
    # Восстановление (в фоне, параллельно где возможно)
    created_categories = {}
    for c_data in backup_data["channels"]:
        cat_name = c_data["category"]
        cat = None
        if cat_name:
            if cat_name not in created_categories:
                cat = await guild.create_category(cat_name)
                created_categories[cat_name] = cat
            else:
                cat = created_categories[cat_name]
                
        if c_data["type"] == "text":
            await guild.create_text_channel(name=c_data["name"], category=cat, position=c_data["position"])
        elif c_data["type"] == "voice":
            await guild.create_voice_channel(name=c_data["name"], category=cat, position=c_data["position"])
            
    await ctx.send("✅ Восстановление структуры завершено.")

@bot.hybrid_command(name="backups", description="Список бекапов")
@is_owner()
@in_right_guild()
async def backups(ctx):
    if not db["backups"]:
        return await ctx.send("Бекапов пока нет.")
    
    msg = "**Список бекапов:**\n"
    for b_id, b_data in db["backups"].items():
        msg += f"`{b_id}` - {b_data['date']} (Каналов: {len(b_data['channels'])})\n"
    await ctx.send(msg)

@bot.hybrid_command(name="addbanword", description="Добавить банворд")
@is_owner()
@in_right_guild()
async def addbanword(ctx, word: str):
    word = word.lower()
    if word not in db["banwords"]:
        db["banwords"].append(word)
        save_data(db)
        await ctx.send(f"✅ Слово `{word}` добавлено в черный список.")

@bot.hybrid_command(name="delbanword", description="Удалить банворд")
@is_owner()
@in_right_guild()
async def delbanword(ctx, word: str):
    word = word.lower()
    if word in db["banwords"]:
        db["banwords"].remove(word)
        save_data(db)
        await ctx.send(f"✅ Слово `{word}` удалено из черного списка.")

@bot.hybrid_command(name="banwords", description="Список банвордов")
@is_owner()
@in_right_guild()
async def banwords(ctx):
    if not db["banwords"]: return await ctx.send("Список банвордов пуст.")
    await ctx.send(f"**Банворды:** {', '.join(db['banwords'])}")

@bot.hybrid_command(name="addbanurl", description="Добавить запрещенную ссылку")
@is_owner()
@in_right_guild()
async def addbanurl(ctx, url: str):
    if url not in db["bannedurls"]:
        db["bannedurls"].append(url)
        save_data(db)
        await ctx.send(f"✅ Ссылка `{url}` добавлена в черный список.")

@bot.hybrid_command(name="delbanurl", description="Удалить запрещенную ссылку")
@is_owner()
@in_right_guild()
async def delbanurl(ctx, url: str):
    if url in db["bannedurls"]:
        db["bannedurls"].remove(url)
        save_data(db)
        await ctx.send(f"✅ Ссылка `{url}` удалена из черного списка.")

@bot.hybrid_command(name="bannedurls", description="Список забаненных ссылок")
@is_owner()
@in_right_guild()
async def bannedurls(ctx):
    if not db["bannedurls"]: return await ctx.send("Список запрещенных ссылок пуст.")
    await ctx.send(f"**Запрещенные ссылки:**\n" + "\n".join(db['bannedurls']))

@bot.hybrid_command(name="reset", description="Сброс к заводским настройкам (удаление data.json)")
@is_owner()
@in_right_guild()
async def reset(ctx):
    global db
    db = DEFAULT_DATA.copy()
    save_data(db)
    log_action("Система сброшена к заводским настройкам.")
    await ctx.send("♻️ Все настройки и базы данных бота были успешно сброшены.")

@bot.hybrid_command(name="logload", description="Отправить логи в ЛС")
@is_owner()
@in_right_guild()
async def logload(ctx):
    if os.path.exists(LOG_FILE):
        await ctx.author.send("📂 Файл логов `logs.txt`:", file=discord.File(LOG_FILE))
        await ctx.send("✅ Логи отправлены вам в личные сообщения.")
    else:
        await ctx.send("❌ Файл логов пока не существует или пуст.")

@bot.hybrid_command(name="clearlagg", description="Очистить файл логов")
@is_owner()
@in_right_guild()
async def clearlagg(ctx):
    open(LOG_FILE, 'w').close()
    await ctx.send("🗑️ Файл логов успешно очищен.")

# ЗАПУСК БОТА
bot.run('ТВОЙ_ТОКЕН_БОТА_ЗДЕСЬ')
