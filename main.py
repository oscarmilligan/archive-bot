import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import json
import asyncio
import datetime
import time

# TODO: Add voice channel archive setting
# TODO: Add exempt text channels from archive
# TODO: Add exempt text channels from gaming
# TODO: Add user archiving
# TODO: Add a permission role
# TODO: change delimiter command



server_settings = {}  # {guild_id: {"prefix": "!", "welcome": "Hi!"}}
scheduled_tasks = {}
last_message_time = {}

def save_settings():
    global server_settings
    with open("settings.json", "w") as f:
        json.dump(server_settings, f, indent=4)

def save_times():
    global last_message_time
    with open("last_message_time.json", "w") as f:
        # convert to iso string so datetime can be stored in json
        json.dump({k: v.isoformat() for k, v in last_message_time.items()}, f, indent=4)

def load_settings():
    global server_settings
    try:
        with open("settings.json", "r") as f:
            server_settings = json.load(f)
    except FileNotFoundError:
        print("settings not found")
        server_settings = {}

def load_times():
    global last_message_time
    try:
        with open("last_message_time.json", "r") as f:
            data = json.load(f)
            print("loading times:",data.items())
            # convert iso strings back to datetime
            last_message_time = {int(k): datetime.datetime.fromisoformat(v) for k, v in data.items()}
            print("successfully loaded last_message_time")
    except FileNotFoundError:
        last_message_time = {}

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

DEFAULT_INACTIVE_ROLE = "dead"
DEFAULT_MISC = True
DEFAULT_GRAVEYARD = "graveyard"
DEFAULT_INACTIVE_TIME = 60*60*24*7
DEFAULT_DO_USER_ARCHIVE = False
DEFAULT_DO_VOICE_ARCHIVE = False
DEFAULT_DO_TEXT_ARCHIVE = True
DEFAULT_BOT_ALERT_CHANNEL = ["Alerts"]
DEFAULT_ADMIN_ROLES = ["Moderator"]

load_settings()

@bot.event
async def on_ready():
    load_settings()
    load_times()
    print("getting bot ready...")
    # do not run if new server
    for guild in bot.guilds:
        guild_id = str(guild.id) 

        if guild_id not in server_settings.keys():
            print(f"Guild {guild_id} not in keys")
            guild_id = str(guild.id)  # keys must be str for JSON
            server_settings[guild_id] = {"misc": DEFAULT_MISC,
                                        "bot_alert_channel": DEFAULT_BOT_ALERT_CHANNEL,
                                        "inactive_role": DEFAULT_INACTIVE_ROLE,
                                        "graveyard": DEFAULT_GRAVEYARD,
                                        "inactive_time": DEFAULT_INACTIVE_TIME,
                                        "do_user_archive": DEFAULT_DO_USER_ARCHIVE,
                                        "do_voice_archive": DEFAULT_DO_VOICE_ARCHIVE,
                                        "do_text_archive": DEFAULT_DO_TEXT_ARCHIVE,
                                        "admin_roles": DEFAULT_ADMIN_ROLES}
            save_settings()
        
        do_text_archive = server_settings[guild_id]["do_text_archive"]
        do_user_archive = server_settings[guild_id]["do_user_archive"]
        do_voice_archive = server_settings[guild_id]["do_voice_archive"]
        graveyard = server_settings[guild_id]["graveyard"]

        print("Creating saved channel tasks")
        category = discord.utils.get(guild.categories, name=graveyard)
        for channel_id, last_time in last_message_time.items():
            print(channel_id)
            channel = bot.get_channel(channel_id)
        
            if channel:
                if channel.type == discord.ChannelType.text:
                    if not do_text_archive:
                        continue
                    # skip graveyard channels
                    if channel.category == category:
                        continue
                    await load_channel_task(channel,last_time)
                if channel.type == discord.ChannelType.voice:
                    if not do_voice_archive:
                        continue
                    # skip graveyard channels
                    if channel.category == category:
                        continue
                    await load_channel_task(channel,last_time)
        print(f"Bot is ready and tasks rescheduled for {len(scheduled_tasks)} channels in {guild.name}.")

@bot.event
async def on_guild_join(guild):
    guild_id = str(guild.id)  # keys must be str for JSON
    if guild_id not in server_settings:
        server_settings[guild_id] = {"misc": DEFAULT_MISC,
                                     "bot_alert_channel": DEFAULT_BOT_ALERT_CHANNEL,
                                     "inactive_role": DEFAULT_INACTIVE_ROLE,
                                     "graveyard": DEFAULT_GRAVEYARD,
                                     "inactive_time": DEFAULT_INACTIVE_TIME,
                                     "do_user_archive": DEFAULT_DO_USER_ARCHIVE,
                                     "do_voice_archive": DEFAULT_DO_VOICE_ARCHIVE,
                                     "do_text_archive": DEFAULT_DO_TEXT_ARCHIVE,
                                     "admin_roles": DEFAULT_ADMIN_ROLES}
        save_settings()

@bot.event
async def on_message(message):
    guild_id = str(message.guild.id)
    channel_id = message.channel.id
    inactive_time = server_settings[guild_id]["inactive_time"]
    do_text_archive = server_settings[guild_id]["do_text_archive"]
    do_user_archive = server_settings[guild_id]["do_user_archive"]

    if message.author == bot.user:
        return
    
    if do_text_archive:
        # store message time
        last_message_time[channel_id] = message.created_at
        save_times()
        print("Message sent at:",message.created_at)
        # Cancel previous task if it exists
        if channel_id in scheduled_tasks:
            scheduled_tasks[channel_id].cancel()

        # Schedule a new task
        scheduled_tasks[channel_id] = asyncio.create_task(schedule_archive(archive_channel, message.channel, inactive_time))

    # misc features
    if server_settings[guild_id]["misc"]:
        for word in ("game","gaming"):
            if word in message.content.lower():
                await message.channel.send(f"{message.author.mention} just lost the game!")

    await bot.process_commands(message)

@bot.event
async def on_voice_state_update(member, before, after):
    active_channel = None
    for state in (before,after):
        if state.channel == None:
            continue
        active_channel = state.channel
        print("User has interacted with",active_channel)
    channel_id = active_channel.id
    guild_id = str(active_channel.guild.id)
    inactive_time = server_settings[guild_id]["inactive_time"]
    last_message_time[channel_id] = datetime.datetime.now(datetime.UTC)
    
    print(f"added {active_channel} to dict at time {last_message_time[channel_id]}")
    save_times()
    # Cancel previous task if it exists
    if channel_id in scheduled_tasks:
        scheduled_tasks[channel_id].cancel()
    # Schedule a new task
    scheduled_tasks[channel_id] = asyncio.create_task(schedule_archive(archive_channel, active_channel, inactive_time))
    

@bot.event
async def on_guild_channel_create(channel):
    
    guild_id = str(channel.guild.id)  # safe string key
    inactive_time = server_settings[guild_id]["inactive_time"]
    print("Getting timers")
    graveyard = server_settings[guild_id]["graveyard"]
    category = discord.utils.get(channel.guild.categories, name=graveyard)
    print("found graveyard")
    if channel.category == category:
        print(f"{channel.name} in graveyard")
        return
    
    last_message_time[channel.id] = channel.created_at
    # Cancel previous task if it exists
    if channel.id in scheduled_tasks:
        scheduled_tasks[channel.id].cancel()

    # Schedule a new task
    scheduled_tasks[channel.id] = asyncio.create_task(schedule_archive(archive_channel,channel, inactive_time))


@bot.command()
async def helpme(ctx):
    print("Displaying help command")
    guild_id = str(ctx.guild.id)
    setting_misc = server_settings[guild_id]["misc"]
    setting_inactive_role = server_settings[guild_id]["inactive_role"]
    setting_graveyard = server_settings[guild_id]["graveyard"]
    setting_inactive_time = server_settings[guild_id]["inactive_time"]
    setting_do_user_archive = server_settings[guild_id]["do_user_archive"]
    setting_do_voice_archive = server_settings[guild_id]["do_voice_archive"]
    setting_do_text_archive = server_settings[guild_id]["do_text_archive"]
    setting_admin_roles = server_settings[guild_id]["admin_roles"]

    inactive_time_formatted = format_time(setting_inactive_time)

    # get roles
    print("Retrieving discord roles")
    admin_roles = [discord.utils.get(ctx.guild.roles,name=role_name) for role_name in setting_admin_roles]
    print("Admin roles retrieved")
    inactive_role = discord.utils.get(ctx.guild.roles,name=setting_inactive_role)
    print("inactive_role retrieved")

    # role text
    admin_text = " ".join([str(admin_role.id) for admin_role in admin_roles]) if admin_roles[0] != None else "Not set"
    inactive_text = inactive_role.id  if inactive_role != None else "Not set"

    sent = await ctx.send("User commands\n"
                   "--------------------\n"
                    f"!helpme: Brings up this menu\n"
                    f"!timers: Get remaining time for each channel\n"
                    f"!assign: Manually add inactive role to self (WIP)\n"
                    f"!remove: Manually remove inactive role from self (WIP)\n"
                    "\n"
                    "Admin commands\n"
                    "-------------------\n"
                    f"!reset-settings: Resets settings to default"
                    f"!graveyard (category): Set the archive category to (category)\n"
                    f"!inactive-time (time) (s/m/h/d): Set the inactivity timer\n"
                    f"!misc: Turn on/off miscellaneous mode\n"
                    f"!inactive-role (role): Set the inactive role to (role)\n"
                    "\n"
                    "Settings\n"
                    "-------------------\n"
                    
                    f"Text archiving: {setting_do_text_archive}\n"
                    f"Voice archiving: {setting_do_voice_archive}\n"
                    f"Use inactive role: {setting_do_user_archive}\n"
                    f"Archive category: {setting_graveyard}\n"
                    f"Inactivity timer: {inactive_time_formatted}\n"
                    f"Inactive Role: {inactive_text}\n"
                    f"Admin Roles: {admin_text}\n"
                    f"Misc: {setting_misc}\n")
    
    # replace roles in text
    print("Replacing roles with mentions without pinging")
    print(admin_roles,inactive_role)
    roles = []
    if admin_roles[0] != None:
        roles += admin_roles
    if inactive_role != None: 
        roles += [inactive_role]
    print("Made roles list")
    edited = sent.content
    for role in roles:
        if str(role.id) in edited:
            edited = edited.replace(str(role.id),role.mention)
    await sent.edit(content=edited)

@bot.command("reset-settings")
async def reset_settings(ctx):
    guild_id = str(ctx.guild.id)
    server_settings[guild_id] = {"misc": DEFAULT_MISC,
                                    "bot_alert_channel": DEFAULT_BOT_ALERT_CHANNEL,
                                    "inactive_role": DEFAULT_INACTIVE_ROLE,
                                    "graveyard": DEFAULT_GRAVEYARD,
                                    "inactive_time": DEFAULT_INACTIVE_TIME,
                                    "do_user_archive": DEFAULT_DO_USER_ARCHIVE,
                                    "do_voice_archive": DEFAULT_DO_VOICE_ARCHIVE,
                                    "do_text_archive": DEFAULT_DO_TEXT_ARCHIVE,
                                    "admin_roles": DEFAULT_ADMIN_ROLES}
    save_settings()

@bot.command()
async def misc(ctx):
    guild_id = str(ctx.guild.id)
    server_settings[guild_id]["misc"] = not(server_settings[guild_id]["misc"])
    await ctx.send(f"Miscellaneous mode: {server_settings[guild_id]["misc"]}")
    save_settings()

@bot.command()
async def assign(ctx):
    guild_id = str(ctx.guild.id)
    inactive_role = server_settings[guild_id]["inactive_role"]
    role = discord.utils.get(ctx.guild.roles, name=inactive_role)
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} is now assigned to {role}")
    else:
        await ctx.send(f"Role:{inactive_role} does not exist")

@bot.command()
async def remove(ctx):
    guild_id = str(ctx.guild.id)
    inactive_role = server_settings[guild_id]["inactive_role"]
    role = discord.utils.get(ctx.guild.roles, name=inactive_role)
    if role:
        await ctx.author.remove_roles(role)
        await ctx.send(f"{ctx.author.mention} is no longer assigned to {role}")
    else:
        await ctx.send(f"Role:{inactive_role} does not exist")

@bot.command("inactive-role")
async def inactiverole(ctx, message):
    guild_id = str(ctx.guild.id)
    role = discord.utils.get(ctx.guild.roles, name=message)
    if role:
        server_settings[guild_id]["inactive_role"] = message
        sent = await ctx.send(f"The inactive role has been set to {role.id}")
        print(sent.content)
        edited = sent.content.replace(str(role.id),role.mention)
        print(sent.content)
        await sent.edit(content=edited)
    else:
        await ctx.send(f"Role:{message} does not exist")
    save_settings()

@bot.command()
async def graveyard(ctx, message):
    guild_id = str(ctx.guild.id)
    category = discord.utils.get(ctx.guild.categories, name=message)
    if category:
        server_settings[guild_id]["graveyard"] = message
        await ctx.send(f"The inactive category has been set to {category}")
    else:
        await ctx.send(f"Category:{message} does not exist")
    save_settings()

@bot.command("inactive-time")
async def inactivetime(ctx, digit, units):
    global last_message_time
    guild_id = str(ctx.guild.id)
    if digit.isdigit():
        t=int(digit)
        if units in ("m", "min", "mins", "minute", "minutes"):
            t *= 60
        elif units in ("h", "hour", "hours"):
            t *= 60*60
        elif units in ("d", "day", "days"):
            t *= 60*60*24
        elif units in ("y", "year", "years"):
            t *= 60*60*24*365

        server_settings[guild_id]["inactive_time"] = t
        await ctx.send(f"The inactive time has been set to {digit+units}")
        await timers(ctx)
        save_settings()
    else:
        await ctx.send(f"Inactive time must be a number")

@bot.command()
async def timers(ctx):
    global server_settings
    guild_id = str(ctx.guild.id)  # safe string key
    print("Getting timers")
    graveyard = server_settings[guild_id]["graveyard"]
    category = discord.utils.get(ctx.guild.categories, name=graveyard)
    print("found graveyard")
    for channel in ctx.guild.text_channels:
        print(f"Looking at {channel.name}")
        if channel.category == category:
            print(f"{channel.name} in graveyard")
            continue
        
        # Cancel previous task if it exists
        if channel.id in scheduled_tasks:
            scheduled_tasks[channel.id].cancel()

        remaining_time = await calculate_remaining_time(channel)
        # Schedule a new task
        scheduled_tasks[channel.id] = asyncio.create_task(schedule_archive(archive_channel,channel, remaining_time))

        await ctx.send(f"{channel.mention}: {format_time(remaining_time)}")#

    for channel in ctx.guild.voice_channels:
        print(f"Looking at {channel.name}")
        if channel.category == category:
            print(f"{channel.name} in graveyard")
            continue
        
        # Cancel previous task if it exists
        if channel.id in scheduled_tasks:
            scheduled_tasks[channel.id].cancel()

        remaining_time = await calculate_remaining_time(channel)
        if remaining_time == -2:
            await ctx.send(f"{channel.mention}: Bot has no recorded voice history, please join to add voice history")
            continue
        # Schedule a new task
        scheduled_tasks[channel.id] = asyncio.create_task(schedule_archive(archive_channel, archive_channel,channel, remaining_time))

        await ctx.send(f"{channel.mention}: {format_time(remaining_time)}")

async def schedule_archive(archive_func, channel, time):
    print(f"scheduling archive of: {channel.name} {channel.id}")
    try:
        if not(str(time).isdigit()):
            return
    except:
        return
    try:
        await asyncio.sleep(time)
        await archive_func(channel)
        
    except asyncio.CancelledError:
        # Task cancelled because a new message arrived
        pass

async def archive_channel(channel):
    global server_settings
    print(f"Archiving channel: {channel.name} {channel.id}")
    guild_id = str(channel.guild.id)
    graveyard = server_settings[guild_id]["graveyard"]
    category = discord.utils.get(channel.guild.categories, name=graveyard)
    if channel.category != category:
        await channel.send(f"This channel: {channel} has been archived")
        print(f"Successfully archived: {channel.name} {channel.id}")
    await channel.edit(category=category)

async def archive_user(guild,member):
    global server_settings
    print(f"Archiving user: {member.name} {member.id}")
    guild_id = str(guild.id)
    print("found guild id",guild_id,type(guild_id))
    inactive_role = server_settings[guild_id]["inactive_role"]
    do_user_archive = server_settings[guild_id]["do_user_archive"]
    if not do_user_archive:
        return
    alert_channel_name = server_settings[guild_id]["bot"]
    role = discord.utils.get(guild.roles, name=inactive_role)
    if role in member.roles:
        return
    
    alert_channel = discord.utils.get(guild.roles, name=alert_channel_name)
    await member.add_roles(role)
    message = await alert_channel.send(f"{member.mention} has been assigned {role.id}")
    edited = message.content.replace(str(role.id),role.mention)
    await message.edit(content=edited)

async def get_last_message_time(channel):
    print("Getting last message time in",channel.name)
    async for message in channel.history(limit=1):
        print(f"The last message in {channel.name} is at {message.created_at}")
        return message.created_at

async def calculate_remaining_time(channel):
    print("calculating time for: ",channel.name)
    guild_id = str(channel.guild.id)
    inactive_time = server_settings[guild_id]["inactive_time"]
    
    if channel.id not in last_message_time.keys():
        print("Channel not in list of active timers")
        if channel.type == discord.ChannelType.text:
            last_message_time[channel.id] = await get_last_message_time(channel)
        elif channel.type  == discord.ChannelType.voice:
            print("Channel is voice channel")
            return -2

        # save_times()
    delta = datetime.datetime.now(datetime.UTC)-last_message_time[channel.id]
    delta = int(delta.total_seconds())

    time_left = inactive_time-delta
    print("Time left:",time_left if time_left > 0 else 1)
    return time_left if time_left > 0 else 1

async def load_channel_task(channel,last_time):
    delta = datetime.datetime.now(datetime.UTC)-last_time
    delta = int(delta.total_seconds())
    time_left = await calculate_remaining_time(channel)
    if time_left == -1: time_left = 1
    print(f"Creating task for {channel.id} with time left: {time_left}")
    scheduled_tasks[channel.id] = asyncio.create_task(schedule_archive(archive_channel, channel, time_left))
def format_time(seconds):
    
    duration = datetime.timedelta(seconds=seconds)
        
    # Extract days, hours, minutes, seconds
    days = duration.days
    hours = duration.seconds // 3600
    minutes = (duration.seconds % 3600) // 60
    seconds = duration.seconds % 60

    # Build human-readable string
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if seconds > 0:
        parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")

    return ' '.join(parts)

# misc commands
@bot.command()
async def hello(ctx):
    guild_id = str(ctx.guild.id)
    if server_settings[guild_id]["misc"]:
        await ctx.send(f"Hello {ctx.author.mention}!")

@bot.command()
async def doxdexter(ctx):
    guild_id = str(ctx.guild.id)
    if server_settings[guild_id]["misc"]:
        await ctx.send(f"53.1464° N, 0.3379° E")
    


bot.run(token, log_handler=handler, log_level=logging.DEBUG)