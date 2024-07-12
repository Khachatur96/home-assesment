from enums import EmailClass
from loguru import logger

class EmailManager:
    def __init__(self):
        self.original_emails = []
        self.urgent_emails = []
        self.not_urgent_emails = []
        self.step = -1
        self.report_msgs = []
        self.next_email = False
        # -1 means disabled / not ready
        # 0 means the emails are classified and ready
        # 1 means user is in the middle of workflow - resume sent and agent waits for urgent/non-urgent response
        # 2 means user is listening to emails one by one

    def add_email(self, email_sender: str, email_subject: str, email_body: str, email_kind: str):
        self.original_emails.append((email_sender, email_subject, email_body, email_kind))
        logger.info(f"Email from {email_sender} added to the list of emails")

    def _get_email_classification(self, email_kind: str):
        if email_kind.lower() == 'urgent':
            return EmailClass.URGENT
        else:
            return EmailClass.NOT_URGENT

    def _get_email_summary(self, email_subject, email_body, email_sender):
        return f"Summary of the email with subject: {email_subject}, from {email_sender} is: {email_body[:50]}..."

    async def process_emails(self):
        urgent_emails = []
        not_urgent_emails = []
        for email in self.original_emails:
            sender, subject, body, kind = email  # Include kind in unpacking
            classification = self._get_email_classification(kind)  # Use kind for classification
            summary = self._get_email_summary(subject, body, sender)
            email_details = (sender, summary)
            if classification == EmailClass.URGENT:
                urgent_emails.append(email_details)
            else:
                not_urgent_emails.append(email_details)
        self.urgent_emails = urgent_emails
        self.not_urgent_emails = not_urgent_emails
        self.step = 0

    async def compose_resume_message(self):
        total_emails = len(self.urgent_emails) + len(self.not_urgent_emails)
        prep_urgent = "are" if len(self.urgent_emails) > 1 else "is"
        prep_not_urgent = "are" if len(self.not_urgent_emails) > 1 else "is"
        msg = f"Hello you have {total_emails} unread emails, \
                {len(self.urgent_emails)} of them {prep_urgent} requiring your immediate attention \
                and {len(self.not_urgent_emails)} of them {prep_not_urgent} not. \
                Which emails would you like me to read first? Urgent emails or less urgent emails?"
        return msg

    def compose_reading_message(self, processed_emails, label):
        # split to multiple messages instead of one long message
        return_messages = []
        if len(processed_emails) == 0:
            return_messages.append("You do not have " + label)
        else:
            return_messages.append(label + ":")
            for i, email in enumerate(processed_emails):
                sender, summary = email
                text = f"From: {sender}\n{summary}"
                return_messages.append(text)
        return return_messages

    async def generate_report(self, label):
        if label == EmailClass.URGENT:
            urgent_messages = self.compose_reading_message(self.urgent_emails, "urgent emails")
            not_urgent_messages = self.compose_reading_message(self.not_urgent_emails, "less urgent emails")
            self.report_msgs = urgent_messages + not_urgent_messages
            return True
        elif label == EmailClass.NOT_URGENT:
            not_urgent_messages = self.compose_reading_message(self.not_urgent_emails, "less urgent emails")
            urgent_messages = self.compose_reading_message(self.urgent_emails, "urgent emails")
            self.report_msgs = not_urgent_messages + urgent_messages
            return True
        else:
            self.report_msgs = ["Please choose between urgent emails or less urgent emails"]
            return False

    async def reset(self):
        self.original_emails = []
        self.urgent_emails = []
        self.not_urgent_emails = []
        self.step = -1
        self.report_msgs = []
        self.next_email = False
