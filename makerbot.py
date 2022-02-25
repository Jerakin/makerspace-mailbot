import os
import os.path
import json
import time

import discord
from dotenv import load_dotenv
from discord.ext import tasks, commands
from discord.commands import slash_command, Option, permissions

try:
    from . import gmail
    from . import one
except ImportError:
    import gmail
    import one

import logging

logger = logging.getLogger('makerbot')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# Load the environment variables
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')


class MakerBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.SESSION = dict()
        logger.debug(f"New Sessions: {os.path.exists('session.json')}")
        if os.path.exists('session.json'):
            with open('session.json', 'r') as fp:
                d = json.load(fp)
                self.SESSION['discord'] = d['discord']
        else:
            self.SESSION['discord'] = {"modmail": {"listeners": {}}, "cancelled": {"listeners": {}}}

        self.gmail_session = gmail.login()
        self.one_session = one.login()

        self.GMAIL_DATA = gmail.Data()

        self.mod_mail_alert.start()
        self.cancelled_sessions_job.start()

    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f"Crash: {event_method}")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.unknown, name="I crashed :("))

    async def on_ready(self):
        logger.debug(f"Ready: {__name__}")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the Mailbox"))

    @tasks.loop(minutes=5.0)
    async def cancelled_sessions_job(self):
        logger.debug(f"Running cancellation check job: {self.gmail_session is not None}")
        if self.gmail_session is None:
            return

        await self.wait_until_ready()
        for mail in gmail.check_mail(self.gmail_session, self.get_time('cancelled')):
            if mail["type"] == "cancel":
                messages = await self.alert(f"Appointment for {mail['area']} on {mail['date']} at {mail['time']} has been cancelled.", 'cancelled')
                entry = gmail.Entry(mail, messages)
                self.GMAIL_DATA.add(entry)
            elif mail["type"] == "book":
                messages = self.GMAIL_DATA.get_mail(mail)
                if not messages:
                    continue
                deleted = []
                for message in messages[::-1]:
                    if message.id in deleted:
                        continue
                    await message.delete()
                    self.GMAIL_DATA.remove(message)
                    deleted.append(message.id)

    @tasks.loop(minutes=10.0)
    async def mod_mail_alert(self):
        logger.debug(f"Running mod mail check job: {self.one_session is not None}")
        if self.one_session:
            await self.wait_until_ready()
            messages = one.check_mail_for_new(self.one_session, self.get_time('modmail'))
            await self.alert(messages, 'modmail')

    @tasks.loop(minutes=50.0)
    async def refresh_sessions(self):
        logger.debug(f"Refreshing Sessions")
        if self.gmail_session:
            self.gmail_session.close()
            self.gmail_session.logout()
            self.gmail_session = gmail.login()
        if self.one_session:
            self.one_session.close()
            self.one_session.logout()
            self.one_session = one.login()

    @mod_mail_alert.after_loop
    @cancelled_sessions_job.after_loop
    async def save_session(self):
        await self.wait_until_ready()
        with open('session.json', 'w') as fp:
            json.dump(self.SESSION, fp)

    async def alert(self, message, scope):
        sent = []
        for guild in self.SESSION['discord'][scope]['listeners']:
            for channel in self.SESSION['discord'][scope]['listeners'][guild]:
                msg = await self.get_channel(int(channel)).send(message)
                sent.append(msg)
            self.SESSION['discord'][scope]['last_request'] = int(time.time())
        return sent

    @slash_command(guild_ids=[770280950155575298])
    @permissions.has_role("admin")
    async def register(self, ctx: discord.ApplicationContext,
                       feature: Option(str, "What to register for", choices=["Cancellation", "Modmail"]),
                       value: Option(str, "Register or Unregister", choices=["start", "stop"])):

        await self._register(ctx, value, feature, value)

    @commands.has_permissions(administrator=True)
    async def on_message(self, message):
        command, *msg = message.content.split(" ")
        if command.startswith("!cancelled"):
            await self._register(message, " ".join(msg), 'cancelled', 'Cancelled Sessions')
        elif command.startswith("!modmail"):
            await self._register(message, " ".join(msg), 'modmail', 'Info Mail')
        elif command.startswith("!mailman"):
            await message.channel.send(f"Hi there!")

    async def _register(self, message, arg, scope, name):
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
        return int(time.time()) - (14 * 24 * 60 * 60)


def main():
    client = MakerBot()
    logger.debug(f"Starting: {__name__}")
    client.run(TOKEN)


if __name__ == '__main__':
    main()
