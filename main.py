import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import json
import asyncio
import datetime
import time

# TODO: Add voice channel archiving (and setting for it)
# TODO: Add exempt text channels
# TODO: command to display archive timers
# TODO: Add user archiving
# TODO: Add a permission role
# TODO: Don't send archive message from archive



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

bot = commands.Bot(command_prefix="!", intents=intents)

DEFAULT_INACTIVE_ROLE = "dead"
DEFAULT_MISC = True
DEFAULT_GRAVEYARD = "graveyard"
DEFAULT_INACTIVE_TIME = 60*60*24*7

load_settings()

@bot.event
async def on_ready():
    load_times()
    print("Loaded times")
    # do not run if new server
    for guild in bot.guilds:
        guild_id = str(guild.id) 
        if guild_id not in server_settings.keys():
            return
    
    for channel_id, last_time in last_message_time.items():
        print(channel_id)
        guild_id = str(channel.guild.id)
        graveyard = server_settings[guild_id]["graveyard"]
        category = discord.utils.get(channel.guild.categories, name=graveyard)

        channel = bot.get_channel(channel_id)
        if channel:
            # skip graveyard channels
            if channel.category == category:
                continue
            print(last_time)
            print(datetime.datetime.now(datetime.UTC))
            delta = datetime.datetime.now(datetime.UTC)-last_time
            delta = int(delta.total_seconds())
            print(delta)
            for guild in bot.guilds:
                guild_id = str(guild.id) 
                if guild_id not in server_settings.keys():
                    continue
                print(guild_id)
                time_left = await calculate_remaining_time(channel)
                if time_left == -1: time_left = 1
                print(f"Creating task for {channel_id} with time left: {time_left}")
                scheduled_tasks[channel_id] = asyncio.create_task(schedule_archive(channel, time_left))
    print(f"Bot is ready and tasks rescheduled for {len(scheduled_tasks)} channels.")

@bot.event
async def on_guild_join(guild):
    guild_id = str(guild.id)  # keys must be str for JSON
    if guild_id not in server_settings:
        server_settings[guild_id] = {"misc": DEFAULT_MISC,
                                     "inactive_role": DEFAULT_INACTIVE_ROLE,
                                     "graveyard": DEFAULT_GRAVEYARD,
                                     "inactive_time": DEFAULT_INACTIVE_TIME}
        save_settings()

@bot.event
async def on_message(message):
    guild_id = str(message.guild.id)
    channel_id = message.channel.id
    inactive_time = server_settings[guild_id]["inactive_time"]

    if message.author == bot.user:
        return
    print(1)
    # store message time
    last_message_time[channel_id] = message.created_at
    save_times()
    print("Message sent at:",message.created_at)
    # Cancel previous task if it exists
    if channel_id in scheduled_tasks:
        scheduled_tasks[channel_id].cancel()

    print(3)
    # Schedule a new task
    scheduled_tasks[channel_id] = asyncio.create_task(schedule_archive(message.channel, inactive_time))

    print(4)
    # misc features
    if server_settings[guild_id]["misc"]:
        for word in ("game","gaming"):
            if word in message.content.lower():
                await message.channel.send(f"{message.author.mention} just lost the game!")

    await bot.process_commands(message)

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
    scheduled_tasks[channel.id] = asyncio.create_task(schedule_archive(channel, inactive_time))


@bot.command()
async def helpme(ctx):
    guild_id = str(ctx.guild.id)
    setting_misc = server_settings[guild_id]["misc"]
    setting_inactive_role = server_settings[guild_id]["inactive_role"]
    setting_graveyard = server_settings[guild_id]["graveyard"]
    setting_inactive_time = server_settings[guild_id]["inactive_time"]

    inactive_time_formatted = format_time(setting_inactive_time)

    await ctx.send("User commands\n"
                   "--------------------\n"
                    f"!helpme: Brings up this menu\n"
                    f"!timers: Get remaining time for each channel\n"
                    f"!assign: Manually add inactive role to self (WIP)\n"
                    f"!remove: Manually remove inactive role from self (WIP)\n"
                    "\n"
                    "Admin commands\n"
                    "-------------------\n"
                    f"!graveyard (category): Set the archive category to (category)\n"
                    f"!inactivetime (time) (s/m/h/d): Set the inactivity timer\n"
                    f"!misc: Turn on/off miscellaneous mode\n"
                    f"!inactiverole (role): Set the inactive role to (role)\n"
                    "\n"
                    "Settings\n"
                    "-------------------\n"
                    f"Archive category: {setting_graveyard}\n"
                    f"Inactivity timer: {inactive_time_formatted}\n"
                    f"Inactive Role: {setting_inactive_role}\n"
                    f"Misc: {setting_misc}\n")

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

@bot.command()
async def inactiverole(ctx, message):
    guild_id = str(ctx.guild.id)
    role = discord.utils.get(ctx.guild.roles, name=message)
    if role:
        server_settings[guild_id]["inactive_role"] = message
        await ctx.send(f"The inactive role has been set to {role}")
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

@bot.command()
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
        scheduled_tasks[channel.id] = asyncio.create_task(schedule_archive(channel, remaining_time))

        await ctx.send(f"{channel.mention}: {format_time(remaining_time)}")

async def schedule_archive(channel, time):
    print("scheduling archive")
    try:
        if not(str(time).isdigit()):
            return
    except:
        return
    try:
        await asyncio.sleep(time)
        print("waited enough time")
        print("archiving channel")
        await archive_channel(channel)
        
    except asyncio.CancelledError:
        # Task cancelled because a new message arrived
        pass

async def archive_channel(channel):
    global server_settings
    guild_id = str(channel.guild.id)
    print("found guild id",guild_id,type(guild_id))
    graveyard = server_settings[guild_id]["graveyard"]
    category = discord.utils.get(channel.guild.categories, name=graveyard)
    print("found graveyard")
    await channel.edit(category=category)
    await channel.send(f"This channel: {channel} has been archived")

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
        last_message_time[channel.id] = await get_last_message_time(channel)

        # save_times()
    delta = datetime.datetime.now(datetime.UTC)-last_message_time[channel.id]
    delta = int(delta.total_seconds())

    time_left = inactive_time-delta
    print("Time left:",time_left if time_left > 0 else 1)
    return time_left if time_left > 0 else 1


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

bot.run(token, log_handler=handler, log_level=logging.DEBUG)