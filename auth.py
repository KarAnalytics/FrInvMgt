import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv
import streamlit as st
load_dotenv()

# These should be set in a .env file locally for security.
EMAIL_SENDER = os.getenv("EMAIL_SENDER", "kartucson@gmail.com")
# Gmail requires an "App Password" (16 chars) if 2-Step Verification is on.
# Do NOT use your regular Gmail password here.
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
if not EMAIL_APP_PASSWORD and hasattr(st, "secrets") and "EMAIL_APP_PASSWORD" in st.secrets:
    EMAIL_APP_PASSWORD = st.secrets["EMAIL_APP_PASSWORD"]

def generate_password(length=8):
    """Generate a random alphanumeric password."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def send_real_email(to_email, subject, body):
    """
    Sends a real email using Gmail's SMTP server.
    Requires EMAIL_SENDER and EMAIL_APP_PASSWORD to be configured.
    """
    if not EMAIL_APP_PASSWORD:
        return (False, "Email system offline: App Password not configured in .env file. "
                       f"Simulated message intended for {to_email}: {body}")
        
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_SENDER
        msg['To'] = to_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'plain'))

        # Connect to Gmail's SMTP server
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls() # Secure the connection
        server.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
        
        # Send email
        text = msg.as_string()
        server.sendmail(EMAIL_SENDER, to_email, text)
        server.quit()
        
        return True, "Email sent successfully."
        
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

def simulate_email(to_email, subject, body):
    """
    We will now default to attempting to send the real email.
    If credentials aren't set, `send_real_email` handles the fallback logic gracefully.
    """
    return send_real_email(to_email, subject, body)

