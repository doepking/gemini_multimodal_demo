import os
import smtplib
import logging
import datetime as dt
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

NEWSLETTER_LOG_FILE = os.path.join('data', 'sent_newsletters.json')

def _get_email_credentials(user_email):
    """
    Fetches email credentials from environment variables.
    The user's own email is used as the sender.
    """
    creds = {
        "smtp_host": os.environ.get("SMTP_HOST"),
        "smtp_port": os.environ.get("SMTP_PORT"),
        "smtp_user": user_email,
        "smtp_password": os.environ.get("SMTP_PASSWORD"),
        "sender_email": user_email,
    }
    if not all(creds.values()):
        logger.warning("One or more SMTP environment variables are not set. Email sending will fail.")
    return creds

def _load_previous_newsletters(user_email):
    """Loads previously sent newsletter content for a user."""
    if not os.path.exists(NEWSLETTER_LOG_FILE):
        return []
    try:
        with open(NEWSLETTER_LOG_FILE, 'r') as f:
            all_logs = json.load(f)
        return all_logs.get(user_email, [])
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def _save_newsletter_log(user_email, content_li_items):
    """Saves the sent newsletter content for a user."""
    if not os.path.exists('data'):
        os.makedirs('data')
    
    all_logs = {}
    if os.path.exists(NEWSLETTER_LOG_FILE):
        try:
            with open(NEWSLETTER_LOG_FILE, 'r') as f:
                all_logs = json.load(f)
        except json.JSONDecodeError:
            all_logs = {}

    if user_email not in all_logs:
        all_logs[user_email] = []

    log_entry = {
        "timestamp": dt.datetime.utcnow().isoformat(),
        "content": content_li_items
    }
    all_logs[user_email].append(log_entry)

    with open(NEWSLETTER_LOG_FILE, 'w') as f:
        json.dump(all_logs, f, indent=2)

def _generate_html_content(user_email, user_name, input_log, background_info, tasks):
    """
    Generates the HTML content for the newsletter using a sophisticated, multi-part prompt.
    """
    from utils import get_chat_response

    greeting_name = user_name.split()[0] if user_name else user_email.split('@')[0]
    
    previous_newsletters = _load_previous_newsletters(user_email)
    previous_newsletters_context = "\n\n".join([log['content'] for log in previous_newsletters[-3:]])
    
    now = dt.datetime.now(dt.timezone.utc)
    current_time_str = now.isoformat()
    current_weekday_str = now.strftime('%A')

    prompt = f"""
    You are "The Opportunity Architect" an AI assistant. Your persona is brutally honest, direct, and action-focused.
    Your goal is to generate a "Current State Analysis & Actionable Next Steps" brief as a string of three to four HTML list items (`<li>...</li>`).

    - The first 2-3 `<li>`s must be a cohesive narrative: a "hard truth" insight based on the user's state, followed by a "strategic play" for today.
    - The final `<li>` must be a relevant motivational quote.
    - Do NOT directly quote user logs. Synthesize patterns.
    - Each narrative `<li>` must start with a `<strong>Keyword:</strong>`.
    - Use `<strong>` for bold and `<em>` for italics. Use emojis sparingly at the start of points.
    - Review "PREVIOUSLY SENT ADVICE" to avoid repetition.
    - Consider the current time: {current_time_str} ({current_weekday_str}).

    Data for {user_name} ({user_email}):
    - Background: {background_info}
    - Active Tasks: {tasks}
    - Recent Logs: {input_log[-10:]}
    - PREVIOUSLY SENT ADVICE:
    {previous_newsletters_context}

    Generate the HTML `<li>` string now:
    """

    # We pass an empty conversation history as per the user's request
    response_data = get_chat_response([], {}, user_prompt=prompt)
    combined_content_li_items = response_data.get("text_response", "<li>No insight generated.</li>")

    # Save the log
    _save_newsletter_log(user_email, combined_content_li_items)

    # Split content for styling
    insights_and_nudges_html = ""
    motivational_quote_text = ""
    last_li_start_index = combined_content_li_items.rfind('<li>')

    if last_li_start_index != -1:
        insights_and_nudges_html = combined_content_li_items[:last_li_start_index]
        quote_li_full_tag = combined_content_li_items[last_li_start_index:]
        quote_li_content_raw = re.sub(r'</?li[^>]*>', '', quote_li_full_tag)
        motivational_quote_text = quote_li_content_raw.replace("<em>", "").replace("</em>", "").strip()
    else:
        insights_and_nudges_html = combined_content_li_items

    # World-class HTML styling
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Your Current State Analysis & Next Steps</title>
        <style>
            body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f7f6; color: #333; }}
            .email-wrapper {{ max-width: 600px; margin: 25px auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
            .header {{ background-color: #5D9CEC; color: #ffffff; padding: 30px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 28px; font-weight: 500; }}
            .content {{ padding: 30px; }}
            .greeting p {{ font-size: 17px; line-height: 1.6; color: #555; margin-bottom: 20px; }}
            .section-title {{ font-size: 22px; color: #5D9CEC; margin-top: 25px; margin-bottom: 15px; padding-bottom: 10px; border-bottom: 2px solid #e0e0e0; }}
            .content ul {{ padding-left: 25px; margin-top: 10px; list-style-type: '→ '; }}
            .content ul li {{ margin-bottom: 12px; font-size: 16px; line-height: 1.7; color: #444; }}
            .section-divider {{ border: 0; height: 1px; background-color: #e8e8e8; margin: 35px 0; }}
            .quote-section {{ margin: 30px 0 25px; padding: 20px 25px; background-color: #f0f5fb; border-radius: 10px; border-left: 6px solid #5D9CEC; }}
            .quote-section p {{ font-style: italic; font-size: 17px; line-height: 1.65; margin: 0; color: #3a506b; }}
            .footer {{ text-align: center; padding: 25px 30px; font-size: 13px; color: #777; background-color: #f4f7f6; border-top: 1px solid #e0e0e0; }}
        </style>
    </head>
    <body>
        <div class="email-wrapper">
            <div class="header"><h1>Your State Analysis & Next Steps</h1></div>
            <div class="content">
                <div class="greeting">
                    <p>Hi {greeting_name},</p>
                    <p>Here's your personalized analysis for {dt.datetime.utcnow().strftime('%A, %B %d, %Y')}:</p>
                </div>
                <hr class="section-divider">
                <h2 class="section-title">Your Analysis & Recommendations</h2>
                <ul>{insights_and_nudges_html}</ul>
                <hr class="section-divider">
                <div class="quote-section"><p>{motivational_quote_text}</p></div>
            </div>
            <div class="footer">
                <p>This newsletter was automatically generated by Life Tracker.</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

def _send_email(subject, html_body, to_email, creds):
    """Sends an email using the provided credentials."""
    if not all([creds["smtp_host"], creds["smtp_port"], creds["smtp_user"], creds["smtp_password"], creds["sender_email"]]):
        logger.error(f"Email server configuration is incomplete. Skipping email to {to_email}.")
        return False

    message = MIMEMultipart("alternative")
    message["From"] = f"Life Tracker AI <{creds['sender_email']}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.attach(MIMEText(html_body, "html"))

    try:
        port = int(creds["smtp_port"])
        host = creds["smtp_host"]
        user = creds["smtp_user"]
        password = creds["smtp_password"]
        sender = creds["sender_email"]

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

def send_newsletter_for_user(user_email, user_name, session_state):
    """
    Main public function to generate and send a newsletter to a single user.
    It loads the necessary data from session_state and calls the core sending function.
    """
    logger.info(f"Preparing to send newsletter to {user_email}.")

    # Load the data required by the newsletter sender from session_state
    input_log = session_state.get('input_log', [])
    background_info = session_state.get('background_info', {})
    tasks = session_state.get('tasks', [])

    creds = _get_email_credentials(user_email)
    if not creds["smtp_password"]:
        return {"status": "error", "message": "SMTP_PASSWORD environment variable not set."}

    subject = f"Your State Analysis & Next Steps - {dt.date.today().strftime('%B %d, %Y')}"
    
    html_content = _generate_html_content(user_email, user_name, input_log, background_info, tasks)

    success = _send_email(subject, html_content, user_email, creds)

    if success:
        return {"status": "success", "message": f"Newsletter sent to {user_email}."}
    else:
        return {"status": "error", "message": f"Failed to send newsletter to {user_email}."}
