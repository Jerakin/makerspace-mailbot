import os
import os.path
import json
import time

import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv

try:
    from . import gmail
    from . import one
except ImportError:
    import gmail
    import one

# Load the environment variables
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')

bot = commands.Bot(command_prefix='!')

# Hold the guilds and channels that the message writes in
# TODO: Save to disk
SESSION = {}


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the Mailbox"))


async def register(ctx, arg, scope, name):
    listeners = SESSION["discord"][scope]["listeners"]
    if arg == "start":
        if ctx.guild.id not in listeners:
            listeners[ctx.guild.id] = []
        if ctx.channel.id not in listeners[ctx.guild.id]:
            listeners[ctx.guild.id].append(ctx.channel.id)
            await ctx.send(f"MailMan '{name}' activated")
    elif arg == "stop":
        if ctx.guild.id in listeners and ctx.channel.id in listeners[ctx.guild.id]:
            listeners[ctx.guild.id].remove(ctx.channel.id)
            await ctx.send(f"MailMan '{name}' deactivated")


@bot.command(name="cancelled")
# @commands.has_role('admin')
async def mailman(ctx, arg):
    await register(ctx, arg, 'cancelled', 'Cancelled Sessions')


@bot.command(name="modmail")
# @commands.has_role('admin')
async def mailman(ctx, arg):
    await register(ctx, arg, 'modmail', 'Mod Mail')


async def alert(messages, scope):
    for guild in SESSION['discord'][scope]['listeners']:
        for channel in SESSION['discord'][scope]['listeners'][guild]:
            for message in messages:
                await bot.get_guild(int(guild)).get_channel(int(channel)).send(message)
        SESSION['discord'][scope]['last_request'] = int(time.time())


def get_time(scope):
    if 'last_request' in SESSION['discord'][scope]:
        return SESSION['discord'][scope]['last_request']
    return int(time.time()) - (7 * 24 * 60 * 60)


async def cancelled_sessions_alert(service):
    await bot.wait_until_ready()
    messages = gmail.check_mail_for_cancelled(service, get_time('cancelled'))
    await alert(messages, 'cancelled')
    await asyncio.sleep(60 * 15)


async def mod_mail_alert(imap):
    await bot.wait_until_ready()
    messages = one.check_mail_for_new(imap, get_time('modmail'))
    await alert(messages, 'modmail')
    await asyncio.sleep(60 * 15)


async def save_session():
    await bot.wait_until_ready()
    with open('session.json', 'w') as fp:
        json.dump(SESSION, fp)
    await asyncio.sleep(60 * 10)


def main():
    if os.path.exists('session.json'):
        with open('session.json', 'r') as fp:
            d = json.load(fp)
            SESSION['discord'] = d['discord']
    else:
        SESSION['discord'] = {"modmail": {"listeners": {}}, "cancelled": {"listeners": {}}}
    service = gmail.login()
    imap = one.login()
    bot.loop.create_task(mod_mail_alert(imap))
    bot.loop.create_task(cancelled_sessions_alert(service))
    bot.loop.create_task(save_session())
    bot.run(TOKEN)


if __name__ == '__main__':
    main()
