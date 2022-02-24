import os
import time
import re
import imaplib
import email
from email.utils import parsedate_tz, mktime_tz

from dotenv import load_dotenv
from email_reply_parser import EmailReplyParser


# Load the environment variables
load_dotenv()

ONE_DOT_COM_USER = os.getenv('ONE_DOT_COM_USER')
ONE_DOT_COM_PASSWORD = os.getenv('ONE_DOT_COM_PASSWORD')


def login():
    if not ONE_DOT_COM_PASSWORD or not ONE_DOT_COM_USER:
        return

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
                break
        body = "\n".join(bodies)
    else:
        body = _get_body(msg)

    if body:
        # Remove replied to emails
        body = EmailReplyParser.parse_reply(body)

        # Remove hyperlinks
        body = re.sub(r'http\S+', '<REDACTED URL>', body, flags=re.MULTILINE)

        # Limit body max amount of characters
        body = body[:min(len(body), 1800)]

        # Add divider
        body = body + "\n" + "="*40
        return True, subject, body
    return False, "", ""


def format_msg(subject, body):
    return f"**{subject}**\n\n{body}"


def check_mail_for_new(imap, last_request):
    mail_to_check = 10
    status, messages = imap.select("INBOX", readonly=True)
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
