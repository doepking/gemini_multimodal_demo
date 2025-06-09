import os
import smtplib
import logging
import datetime as dt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _get_email_credentials():
    """
    Fetches email credentials from environment variables.
    Private function intended for use within this module.
    """
    creds = {
        "smtp_host": os.environ.get("SMTP_HOST"),
        "smtp_port": os.environ.get("SMTP_PORT"),
        "smtp_user": os.environ.get("SMTP_USER"),
        "smtp_password": os.environ.get("SMTP_PASSWORD"),
        "sender_email": os.environ.get("NEWSLETTER_SENDER_EMAIL"),
    }
    if not all(creds.values()):
        logger.warning("One or more SMTP environment variables are not set. Email sending will fail.")
    return creds

def _generate_html_content(user_email, user_name, input_log):
    """
    Generates the HTML content for the newsletter.
    Private function intended for use within this module.
    """
    num_logs = len(input_log)
    greeting_name = user_name.split()[0] if user_name else user_email.split('@')[0]
    
    # Basic insight based on local data
    insight = f"You've made {num_logs} log entries so far. Keep up the great work!"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Your Life Tracker Update</title>
    </head>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
            <h2>Hello {greeting_name},</h2>
            <p>Here is your weekly summary from Life Tracker:</p>
            <h3>Your Activity</h3>
            <p>{insight}</p>
            <p>This is a simplified newsletter. More features coming soon!</p>
            <br>
            <p>Best,</p>
            <p>The Life Tracker Team</p>
        </div>
    </body>
    </html>
    """
    return html_content

def _send_email(subject, html_body, to_email, creds):
    """
    Sends an email using the provided credentials, supporting both SMTP_SSL and STARTTLS.
    Private function intended for use within this module.
    """
    if not all([creds["smtp_host"], creds["smtp_port"], creds["smtp_user"], creds["smtp_password"], creds["sender_email"]]):
        logger.error(f"Email server configuration is incomplete. Skipping email to {to_email}.")
        return False

    message = MIMEMultipart("alternative")
    message["From"] = f"Life Tracker Newsletter <{creds['sender_email']}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(html_body, "html"))

    try:
        port = int(creds["smtp_port"])
        host = creds["smtp_host"]
        user = creds["smtp_user"]
        password = creds["smtp_password"]
        sender = creds["sender_email"]

        # Use SMTP_SSL for port 465, and STARTTLS for other ports (like 587)
        if port == 465:
            with smtplib.SMTP_SSL(host, port) as server:
                server.login(user, password)
                server.sendmail(sender, to_email, message.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                server.starttls()
                server.login(user, password)
                server.sendmail(sender, to_email, message.as_string())
                
        logger.info(f"Newsletter email sent successfully to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send newsletter email to {to_email}: {e}", exc_info=True)
        return False

def send_newsletter_for_user(user_email, user_name, input_log):
    """
    Main public function to generate and send a newsletter to a single user.
    
    Args:
        user_email (str): The recipient's email address.
        user_name (str): The recipient's name.
        input_log (list): A list of dictionaries representing the user's input log.

    Returns:
        dict: A dictionary with status and a message.
    """
    logger.info(f"Preparing to send newsletter to {user_email}.")

    creds = _get_email_credentials()
    if not creds["sender_email"]:
        return {"status": "error", "message": "NEWSLETTER_SENDER_EMAIL environment variable not set."}

    subject = f"Your Life Tracker Weekly Summary - {dt.date.today().strftime('%B %d, %Y')}"
    html_content = _generate_html_content(user_email, user_name, input_log)

    success = _send_email(subject, html_content, user_email, creds)

    if success:
        return {"status": "success", "message": f"Newsletter sent to {user_email}."}
    else:
        return {"status": "error", "message": f"Failed to send newsletter to {user_email}."}
