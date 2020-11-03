import os
import os.path
import json
import time

import asyncio
import discord
from discord.ext import commands
from dotenv import load_dotenv
from bs4 import BeautifulSoup


import imaplib
import email
from email.utils import parsedate_tz, mktime_tz
from email.header import decode_header
import webbrowser
import os

# Load the environment variables
load_dotenv()

ONE_DOT_COM_USER = os.getenv('ONE_DOT_COM_USER')
ONE_DOT_COM_PASSWORD = os.getenv('ONE_DOT_COM_PASSWORD')


def login():
    # create an IMAP4 class with SSL
    imap = imaplib.IMAP4_SSL("imap.one.com")
    # authenticate
    imap.login(ONE_DOT_COM_USER, ONE_DOT_COM_PASSWORD)
    return imap


def final(service):
    service.close()
    service.logout()


def _get_body(msg):
    # extract content type of email
    content_type = msg.get_content_type()

    content_disposition = str(msg.get("Content-Disposition"))
    # get the email body
    payload = msg.get_payload(decode=True)
    if not payload:
        return
    body = payload.decode(msg.get_charsets()[0])
    if content_type == "text/plain" and "attachment" not in content_disposition:
        # print text/plain emails and skip attachments
        return body


def _parse_mail(response, last_request):
    msg = email.message_from_bytes(response[1])
    date = msg['Date']
    subject = msg['Subject']
    epoch = mktime_tz(parsedate_tz(date))
    if epoch < last_request:
        return False, "", ""
    if msg.is_multipart():
        # iterate over email parts
        bodies = []
        for part in msg.walk():
            body = _get_body(part)
            if body:
                bodies.append(body)
        return True, subject, "\n".join(bodies)
    else:
        return True, subject, _get_body(msg)


def format_msg(subject, body):
    return f"**{subject}**\n\n{body}"


def check_mail_for_new(imap, last_request):
    mail_to_check = 10
    status, messages = imap.select("INBOX")
    messages = int(messages[0])
    for i in range(messages, messages-mail_to_check, -1):
        # fetch the email message by ID
        res, msg = imap.fetch(str(i), "(RFC822)")
        for response in msg:
            if isinstance(response, tuple):
                ok, subject, body = _parse_mail(response, last_request)
                if ok:
                    yield format_msg(subject, body)


if __name__ == '__main__':
    imap = login()
    for x in check_mail_for_new(imap, time.time() - 2*24*60*60):
        print(x)
    imap.close()
    imap.logout()
