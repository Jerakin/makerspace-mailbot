import re


CANCEL_BODY_REGEXP = re.compile('Appointment for (.*) on ([0-9\-]*) at (\d\d:\d\d) has been cancelled')
BOOK_BODY_REGEXP = re.compile('for (.*) at ([0-9\-]*) (\d\d:\d\d)')

TYPE_CANCELED = "cancelled"
TYPE_BOOKED = "booked"


class Mail:
    def __init__(self):
        self._subject = None
        self._body = None
        self.sender = None
        self.is_booking = False

    @property
    def subject(self):
        return self._subject

    @subject.setter
    def subject(self, v):
        self._subject = v

    @property
    def body(self):
        return self._body

    @body.setter
    def body(self, v):
        self._body = v

    def __repr__(self):
        return f"{self.subject}; {self.sender}"

    @property
    def text(self):
        return f"{self.subject}\nFrom: {self.sender}\n\n{self.body}"


class Booking(Mail):
    def __init__(self):
        super(Booking, self).__init__()
        self.is_booking = True
        self.date = None
        self.area = None
        self.time = None
        self.type = None
        self.messages = []

    @property
    def subject(self):
        return f"Appointment for {self.area}"

    @property
    def body(self):
        return f"On **{self.date}** at **{self.time}** has been {self.type}."

    @subject.setter
    def subject(self, v):
        self._subject = v

    @body.setter
    def body(self, v):
        self._body = v


class Data:
    def __init__(self):
        self._email_entries = []

    def add(self, entry):
        self._email_entries.append(entry)

    def __getitem__(self, item):
        return self._email_entries[item]

    def remove(self, entry):
        for this_entry in self._email_entries:
            if entry in this_entry.messages:
                this_entry.messages.remove(entry)

    def get_mail(self, entry):
        date = entry.date
        area = entry.area
        time = entry.time
        for this_entry in self._email_entries:
            if date == this_entry.date and area == this_entry.area and time == this_entry.time:
                return this_entry.messages
