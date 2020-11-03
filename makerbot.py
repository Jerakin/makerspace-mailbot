import os
import os.path
import json
import time

import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord.ext import tasks

try:
    from . import gmail
    from . import one
except ImportError:
    import gmail
    import one

# Load the environment variables
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')

class MakerBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.SESSION = dict()
        if os.path.exists('session.json'):
            with open('session.json', 'r') as fp:
                d = json.load(fp)
                self.SESSION['discord'] = d['discord']
        else:
            self.SESSION['discord'] = {"modmail": {"listeners": {}}, "cancelled": {"listeners": {}}}

        self.gmail_session = gmail.login()
        self.one_session = one.login()

        self.cancelled_sessions_alert.start()
        self.mod_mail_alert.start()

    async def on_ready(self):
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the Mailbox"))

    @tasks.loop(minutes=15.0)
    async def cancelled_sessions_alert(self):
        await self.wait_until_ready()
        messages = gmail.check_mail_for_cancelled(self.gmail_session, self.get_time('cancelled'))
        await self.alert(messages, 'cancelled')

    @tasks.loop(minutes=15.0)
    async def mod_mail_alert(self):
        await self.wait_until_ready()
        messages = one.check_mail_for_new(self.one_session, self.get_time('modmail'))
        await self.alert(messages, 'modmail')

    @mod_mail_alert.after_loop
    @cancelled_sessions_alert.after_loop
    async def save_session(self):
        await self.wait_until_ready()
        with open('session.json', 'w') as fp:
            json.dump(self.SESSION, fp)

    async def alert(self, messages, scope):
        for guild in self.SESSION['discord'][scope]['listeners']:
            for channel in self.SESSION['discord'][scope]['listeners'][guild]:
                for message in messages:
                    await self.get_channel(int(channel)).send(message)
            self.SESSION['discord'][scope]['last_request'] = int(time.time())

    async def on_message(self, message):
        command, *msg = message.content.split(" ")
        if command.startswith("!cancelled"):
            await self.register(message, " ".join(msg), 'cancelled', 'Cancelled Sessions')
        elif command.startswith("!modmail"):
            await self.register(message, " ".join(msg), 'modmail', 'Info Mail')
        elif command.startswith("!mailman"):
            await message.channel.send(f"Hi there!")

    async def register(self, message, arg, scope, name):
        listeners = self.SESSION["discord"][scope]["listeners"]
        guild = str(message.guild.id)
        channel = str(message.channel.id)
        if arg == "start":
            if guild not in listeners:
                listeners[guild] = []
            if channel not in listeners[guild]:
                listeners[guild].append(channel)
                await message.channel.send(f"MailMan '{name}' activated")
        elif arg == "stop":
            if guild in listeners and channel in listeners[guild]:
                listeners[guild].remove(channel)
                await message.channel.send(f"MailMan '{name}' deactivated")

    def get_time(self, scope):
        if 'last_request' in self.SESSION['discord'][scope]:
            return self.SESSION['discord'][scope]['last_request']
        return int(time.time()) - (7 * 24 * 60 * 60)


def main():
    client = MakerBot()
    client.run(TOKEN)


if __name__ == '__main__':
    main()
