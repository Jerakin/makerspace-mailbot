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


def register(ctx, arg, scope, name):
    listeners = SESSION["discord"][scope]["listeners"]
    if arg == "start":
        if ctx.guild not in listeners:
            listeners[ctx.guild] = []
        if ctx.channel not in listeners[ctx.guild]:
            listeners[ctx.guild].append(ctx.channel)
            await ctx.send(f"MailMan '{name}' activated")
    elif arg == "stop":
        if ctx.guild in listeners and ctx.channel in listeners[ctx.guild]:
            listeners[ctx.guild].remove(ctx.channel)
            await ctx.send(f"MailMan '{name}' deactivated")


@bot.command(name="cancelled")
# @commands.has_role('admin')
async def mailman(ctx, arg):
    register(ctx, arg, 'cancelled', 'Cancelled Sessions')


@bot.command(name="modmail")
# @commands.has_role('admin')
async def mailman(ctx, arg):
    register(ctx, arg, 'modmail', 'Mod Mail')


def alert(messages, scope):
    for guild in SESSION['discord'][scope]['listeners']:
        for channel in SESSION['discord'][scope]['listeners'][guild]:
            for message in messages:
                await channel.send(message)
    SESSION['discord'][scope]['last_request'] = time.time()


async def cancelled_sessions_alert(service):
    await bot.wait_until_ready()
    messages = gmail.check_mail_for_cancelled(service, SESSION['discord']['cancelled']['last_request'])
    alert(messages, 'cancelled')
    await asyncio.sleep(60 * 15)  # task runs every 15 min


async def mod_mail_alert(imap):
    await bot.wait_until_ready()
    messages = one.check_mail_for_new(imap, SESSION['discord']['modmail']['last_request'])
    alert(messages, 'modmail')
    await asyncio.sleep(60 * 15)  # task runs every 15 min


def main():
    if os.path.exists('session.json'):
        with open('session.json', 'r') as fp:
            d = json.load(fp)
            SESSION['discord'] = d['discord']
    else:
        SESSION['discord'] = {"modmail": {"listeners": {}}, "cancelled": {"listeners": {}}}
        SESSION['discord']['modmail']['last_request'] = int(time.time()) - (7 * 24 * 60 * 60)
        SESSION['discord']['cancelled']['last_request'] = int(time.time()) - (7 * 24 * 60 * 60)
    service = gmail.login()
    imap = one.login()
    bot.loop.create_task(mod_mail_alert(imap))
    bot.loop.create_task(cancelled_sessions_alert(service))
    bot.run(TOKEN)


if __name__ == '__main__':
    main()
