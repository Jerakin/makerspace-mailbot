import os
import os.path
import json
import time

import discord
from dotenv import load_dotenv
from discord.ext import tasks, commands
from discord.commands import slash_command, Option, permissions, message_command

try:
    from . import gmail
    from . import one
    from . import mail
except ImportError:
    import gmail
    import one
    import mail

import logging

logger = logging.getLogger('makerbot')
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
handler.setFormatter(logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
logger.addHandler(handler)

# Load the environment variables
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')


SCOPE_CANCELLATION = "cancellation"
SCOPE_MODMAIL = "modmail"
SERVICE_GMAIL = "gmail"
SERVICE_ONE = "one"


class MakerBot(discord.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.SESSION = dict()
        logger.debug(f"New Sessions: {os.path.exists('session.json')}")
        if os.path.exists('session.json'):
            with open('session.json', 'r') as fp:
                d = json.load(fp)
                self.SESSION['discord'] = d['discord']
        else:
            self.SESSION['discord'] = {SERVICE_ONE: 0,
                                       SERVICE_GMAIL: 0,
                                       SCOPE_MODMAIL: {"listeners": {}},
                                       SCOPE_CANCELLATION: {"listeners": {}}}

        self.gmail_session = gmail.login()
        self.one_session = one.login()

        self.MAIL_DATA = mail.Data()

        self.one_sessions_job.start()
        self.gmail_sessions_job.start()

    def ignore_sender(self, guild_id, sender):
        if "ignore" not in self.SESSION['discord'][SCOPE_MODMAIL]['listeners'][guild_id]:
            self.SESSION['discord'][SCOPE_MODMAIL]['listeners'][guild_id]['ignore'] = []
        self.SESSION['discord'][SCOPE_MODMAIL]['listeners'][guild_id]['ignore'].append(sender)

    async def on_error(self, event_method, *args, **kwargs):
        logger.error(f"Crash: {event_method}")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.unknown, name="I crashed :("))

    async def on_ready(self):
        logger.debug(f"Ready: {__name__}")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="the Mailbox"))

    async def handle_booking(self, entry):
        if entry.type == mail.TYPE_CANCELED:
            message = await self.alert(entry, SCOPE_CANCELLATION)
            entry.messages.extend(message)
            self.MAIL_DATA.add(entry)
        else:
            messages = self.MAIL_DATA.get_mail(entry)
            if not messages:
                return
            deleted = []
            for message in messages[::-1]:
                if message.id in deleted:
                    continue
                await message.delete()
                self.MAIL_DATA.remove(message)
                deleted.append(message.id)

    @tasks.loop(minutes=5.0)
    async def gmail_sessions_job(self):
        logger.debug(f"Running cancellation check job: {self.gmail_session is not None}")
        if self.gmail_session is None:
            return

        await self.wait_until_ready()
        for received_mail in gmail.check_mail(self.gmail_session, self.get_time(SERVICE_GMAIL)):
            if received_mail.is_booking:
                await self.handle_booking(received_mail)
            else:
                await self.alert(received_mail, SCOPE_MODMAIL)

        self.SESSION['discord'][SERVICE_GMAIL] = int(time.time())

    @tasks.loop(minutes=10.0)
    async def one_sessions_job(self):
        logger.debug(f"Running mod mail check job: {self.one_session is not None}")
        if self.one_session is None:
            return

        await self.wait_until_ready()
        for received_mail in one.check_mail_for_new(self.one_session, self.get_time(SERVICE_ONE)):
            if not received_mail:
                continue
            if received_mail.is_booking:
                await self.handle_booking(received_mail)
            else:
                await self.alert(received_mail, SCOPE_MODMAIL)
        self.SESSION['discord'][SERVICE_ONE] = int(time.time())

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

    @one_sessions_job.after_loop
    @gmail_sessions_job.after_loop
    async def save_session(self):
        await self.wait_until_ready()
        with open('session.json', 'w') as fp:
            json.dump(self.SESSION, fp)

    async def alert(self, message, scope):
        sent = []
        for guild_id in self.SESSION['discord'][scope]['listeners']:
            for channel_id in self.SESSION['discord'][scope]['listeners'][guild_id]["channels"]:
                if "ignore" in self.SESSION['discord'][scope]['listeners'][guild_id]:
                    for _ignore in self.SESSION['discord'][scope]['listeners'][guild_id]["ignore"]:
                        if _ignore in message.sender:
                            return
                channel = self.get_channel(int(channel_id))
                e = discord.Embed()
                e.title = message.subject
                e.description = message.body
                if message.is_booking:
                    e.url = "https://www.malmomakerspace.se/booking-system"
                else:
                    e.set_footer(text=message.sender)
                m_id = await channel.send(embed=e)
                sent.append(m_id)
        return sent

    async def register(self, ctx, arg, scope):
        listeners = self.SESSION["discord"][scope.lower()]["listeners"]
        guild = str(ctx.guild.id)
        channel = str(ctx.channel.id)
        logger.debug(f"Trying Registering {scope}")
        if arg == "start":
            if guild not in listeners:
                listeners[guild] = {"channels": []}
            if channel not in listeners[guild]:
                listeners[guild]["channels"].append(channel)
                logger.debug(f"Success Registering {scope}")
                await ctx.respond(f"MailMan '{scope}' activated", ephemeral=True)
            else:
                logger.debug(f"Failed Registering {scope} - already active")
                await ctx.respond(f"MailMan '{scope}' already active", ephemeral=True)
        elif arg == "stop":
            if guild in listeners and channel in listeners[guild]["channels"]:
                listeners[guild]["channels"].remove(channel)
                logger.debug(f"Success deactivating {scope}")
                await ctx.respond(f"MailMan '{scope}' deactivated", ephemeral=True)
            else:
                logger.debug(f"Failed deactivating {scope} - not found")
                await ctx.respond(f"MailMan '{scope}' not found", ephemeral=True)

    def get_time(self, service):
        if self.SESSION['discord'][service]:
            return self.SESSION['discord'][service]
        return int(time.time()) - (14 * 24 * 60 * 60)


logger.debug(f"Starting: {__name__}")
client = MakerBot(intents=discord.Intents(guilds=True), debug_guilds=[773160029766811669])


@client.slash_command(description="Registering a channel for bot messages")
@permissions.has_role("admin")
async def register(ctx: discord.ApplicationContext,
                   feature: Option(str, "What to register for", choices=[SCOPE_CANCELLATION, SCOPE_MODMAIL]),
                   value: Option(str, "Register or Unregister", choices=["start", "stop"])):
    logger.debug("Invoked Slash command")
    await client.register(ctx, value, feature)


@client.slash_command(description="Debug: Resets the last check email check time")
@permissions.has_role("admin")
async def reset(ctx: discord.ApplicationContext):
    client.SESSION['discord'][SERVICE_ONE] = 0
    client.SESSION['discord'][SERVICE_GMAIL] = 0
    await client.save_session()
    await ctx.respond("Session Time Reset", ephemeral=True)


@client.slash_command(description="Debug: Checks for emails")
@permissions.has_role("admin")
async def fetch(ctx: discord.ApplicationContext):
    await client.gmail_sessions_job()
    await client.one_sessions_job()
    await ctx.respond("Checking for new emails", ephemeral=True)


def is_me(m):
    return m.author == client.user


@client.slash_command(description="Clears all bots messages")
@permissions.has_role("admin")
async def clear(ctx: discord.ApplicationContext):
    await ctx.channel.purge(check=is_me)
    await ctx.respond("All messages deleted", ephemeral=True)


@client.slash_command(description="Ignores emails from the sender")
@permissions.has_role("admin")
async def ignore(ctx: discord.ApplicationContext, sender: Option(str, "Sender")):
    client.ignore_sender(str(ctx.guild_id), sender)
    logger.debug(f"Ignore: {sender}")
    await ctx.respond(f"Ignore added: {sender}")


client.run(TOKEN)
