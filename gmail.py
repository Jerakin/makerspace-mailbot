import os
import base64
import os.path
import pickle
import re

from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CANCEL_BODY_REGEXP = re.compile('Appointment for (.*) on ([0-9\-]*) at (\d\d:\d\d) has been cancelled')
BOOK_BODY_REGEXP = re.compile('for (.*) at ([0-9\-]*) (\d\d:\d\d)')


class Entry:
    def __init__(self, msg, messages):
        self.date = msg['date']
        self.area = msg['area']
        self.time = msg['time']
        self.messages = messages


class Data:
    def __init__(self):
        self._data = []

    def add(self, entry):
        self._data.append(entry)

    def __getitem__(self, item):
        return self._data[item]

    def remove(self, msg):
        for entry in self._data:
            if msg in entry.messages:
                entry.messages.remove(msg)

    def get_mail(self, entry):
        date = entry["date"]
        area = entry["area"]
        time = entry["time"]
        for x in self._data:
            if date == x.date and area == x.area and time == x.time:
                return x.messages


def login():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    else:
        if not os.path.exists('credentials.json'):
            return
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    service = build('gmail', 'v1', credentials=creds)
    return service


def _parse_payload(payload):
    # Fetching message body
    email_parts = payload['parts']  # fetching the message parts
    part_one = email_parts[0]  # fetching first element of the part
    part_body = part_one['body']  # fetching body of the message
    if 'parts' in part_one:
        part_body = part_one['parts'][0]['body']
    if 'data' not in part_body:
        return ""
    part_data = part_body['data']  # fetching data from the body
    clean_one = part_data.replace("-", "+")  # decoding from Base64 to UTF-8
    clean_one = clean_one.replace("_", "/")  # decoding from Base64 to UTF-8
    clean_two = base64.b64decode(bytes(clean_one, 'UTF-8'))  # decoding from Base64 to UTF-8
    soup = BeautifulSoup(clean_two, "lxml")
    message_body = soup.body()
    # message_body is a readible form of message body
    # depending on the end user's requirements, it can be further cleaned
    # using regex, beautiful soup, or any other method
    return str(message_body)


def read_email(service, msg_id):
    temp_dict = {}

    message = service.users().messages().get(userId='me', id=msg_id).execute()  # fetch the message using API
    payload = message['payload']  # get payload of the message
    headers = payload['headers']  # get header of the payload

    for h in headers:  # getting the Subject
        if h['name'] == 'Subject':
            temp_dict['Subject'] = h['value']
        if h['name'] == "From":
            temp_dict['From'] = h['value']
    if 'NO-REPLY@simplybook.me' not in temp_dict['From']:
        return
    msg_body = _parse_payload(payload)
    if 'Confirmation of cancellation' in temp_dict['Subject']:
        match = CANCEL_BODY_REGEXP.search(msg_body)
        if match:
            return {"area": match.group(1), "date": match.group(2), "time": match.group(3), "type": "cancel"}
    if 'has booked an appointment with' in temp_dict['Subject']:
        match = BOOK_BODY_REGEXP.search(msg_body)
        if match:
            return {"area": match.group(1), "date": match.group(2), "time": match.group(3), "type": "book"}


def get_emails(service, last_request):
    # Call the Gmail API
    response = service.users().messages().list(userId='me', q=f'after:{last_request}').execute()
    messages = []
    if 'messages' in response:
        messages.extend(response['messages'])

    return messages


def check_mail(service, last_request):
    for mail in get_emails(service, last_request)[::-1]:
        data = read_email(service, mail['id'])
        if data:
            yield data
