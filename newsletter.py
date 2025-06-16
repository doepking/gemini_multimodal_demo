import os
import smtplib
import logging
import datetime as dt
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from sqlalchemy import and_
from database import SessionLocal
from models import NewsletterLog
from google import genai
from google.genai import types

# Load environment variables from .env file
load_dotenv()

# Gemini API initialization
client = genai.Client(api_key=os.environ.get("LLM_API_KEY"))
MODEL_NAME = "gemini-2.5-flash-preview-05-20" 
# Safety settings
safety_settings = [
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
]

def _get_newsletter_content_from_llm(prompt):
    """Generates content from the LLM for the newsletter."""
    try:
        thinking_config = types.ThinkingConfig(
            thinking_budget=2048,
            include_thoughts=False
        )
        generation_config = types.GenerateContentConfig(
            max_output_tokens=4096,
            temperature=0.7,
            safety_settings=[
                types.SafetySetting(category=s["category"], threshold=s["threshold"])
                for s in safety_settings
            ],
            thinking_config=thinking_config,
        )
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=generation_config
        )
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            text_parts = [part.text for part in response.candidates[0].content.parts if hasattr(part, 'text') and part.text and part.text.strip()]
            if text_parts:
                return "".join(text_parts)
        return "<li>No insight generated.</li>"
    except Exception as e:
        logger.error(f"LLM generation error for newsletter: {e}", exc_info=True)
        return "<li>Error generating content.</li>"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _get_email_credentials():
    """
    Fetches email credentials from environment variables.
    """
    creds = {
        "smtp_host": os.environ.get("SMTP_HOST"),
        "smtp_port": os.environ.get("SMTP_PORT"),
        "smtp_user": os.environ.get("SMTP_USER"),
        "smtp_password": os.environ.get("SMTP_PASSWORD"),
        "sender_email": os.environ.get("NEWSLETTER_SENDER_EMAIL")
    }
    if not all(creds.values()):
        logger.warning("One or more SMTP environment variables are not set. Email sending will fail.")
    return creds

def _get_db():
    """Generator function to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _load_previous_newsletters(user_id):
    """Loads previously sent newsletter content for a user."""
    db = next(_get_db())
    return db.query(NewsletterLog).filter(NewsletterLog.user_id == user_id).order_by(NewsletterLog.created_at.desc()).limit(3).all()

def _save_newsletter_log(user_id, content_li_items):
    """Saves the sent newsletter content for a user."""
    db = next(_get_db())
    log_entry = NewsletterLog(
        user_id=user_id,
        content=content_li_items
    )
    db.add(log_entry)
    db.commit()

def _generate_html_content(user_id, user_email, user_name, session_state, persona_prompt, persona_name):
    """
    Generates the HTML content for the newsletter using a sophisticated, multi-part prompt.
    """
    greeting_name = user_name.split()[0] if user_name else user_email.split('@')[0]
    background_info = session_state.get('background_info', {})

    # Get last 20 tasks from session state, sorted by creation date
    all_tasks = session_state.get('tasks', [])
    # Ensure created_at is a datetime object for sorting
    for task in all_tasks:
        if isinstance(task.created_at, str):
            task.created_at = dt.datetime.fromisoformat(task.created_at.replace("Z", "+00:00"))
    
    recent_tasks = sorted(all_tasks, key=lambda t: t.created_at, reverse=True)[:20]
    
    tasks_preview = [
        f"Desc: {task.description}, Status: {task.status}, Created: {task.created_at.strftime('%Y-%m-%d %H:%M (%A)')}, Deadline: {task.deadline.strftime('%Y-%m-%d %H:%M (%A)') if task.deadline else 'None'}"
        for task in recent_tasks
    ]
    tasks_str = "\\n- ".join(tasks_preview) if tasks_preview else "No recent tasks."

    # Format input log with weekday
    input_log = session_state.get('input_log', [])
    recent_logs_preview = []
    for log in input_log[-200:]:  # Last 200 logs
        timestamp = log.created_at.strftime('%Y-%m-%d %H:%M (%A)') if log.created_at else 'No timestamp'
        content_preview = log.content[:500] + "..." if len(log.content) > 500 else log.content
        recent_logs_preview.append(f"[{timestamp}] {content_preview}")
    recent_logs_str = "\\n- ".join(recent_logs_preview) if recent_logs_preview else "No recent logs."
    
    previous_newsletters = _load_previous_newsletters(user_id)
    previous_newsletters_context = "\n\n".join([log.content for log in previous_newsletters])
    
    now = dt.datetime.now(dt.timezone.utc)
    current_time_str = now.isoformat()
    current_weekday_str = now.strftime('%A')

    # Replace placeholders in the persona prompt
    prompt = persona_prompt.format(
        current_time_str=current_time_str,
        current_weekday_str=current_weekday_str,
        background_info=json.dumps(background_info, indent=2),
        tasks_str=tasks_str,
        recent_logs_str=recent_logs_str,
        previous_newsletters_context=previous_newsletters_context
    )

    # We pass an empty conversation history as per the user's request
    combined_content_li_items = _get_newsletter_content_from_llm(prompt)

    # Safeguard against markdown in response
    processed_content = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', combined_content_li_items)
    processed_content = re.sub(r'\*(.*?)\*', r'<em>\1</em>', processed_content)

    # Save the log
    _save_newsletter_log(user_id, processed_content)

    # Split content for styling
    insights_and_nudges_html = ""
    motivational_quote_text = ""
    last_li_start_index = processed_content.rfind('<li>')

    if last_li_start_index != -1:
        insights_and_nudges_html = processed_content[:last_li_start_index]
        quote_li_full_tag = processed_content[last_li_start_index:]
        quote_li_content_raw = re.sub(r'</?li[^>]*>', '', quote_li_full_tag)
        motivational_quote_text = quote_li_content_raw.replace("<em>", "").replace("</em>", "").strip()
    else:
        insights_and_nudges_html = processed_content

    # Persona-specific titles
    persona_titles = {
        "Pragmatist": "Your Commander's Briefing",
        "Analyst": "Your Systems Analysis",
        "Catalyst": "Your Creative Catalyst"
    }
    email_title = persona_titles.get(persona_name, "Your State Analysis & Next Steps")

    # World-class HTML styling
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{email_title}</title>
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
            <div class="header"><h1>{email_title}</h1></div>
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
    message["From"] = f"The Opportunity Architect <{creds['sender_email']}>"
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

def send_newsletter_for_user(user_id, user_email, user_name, session_state, persona_prompt, persona_name):
    """
    Main public function to generate and send a newsletter to a single user.
    It loads the necessary data from session_state and calls the core sending function.
    Includes a rate-limiting check to prevent sending more than three newsletters per day.
    """
    logger.info(f"Preparing to send newsletter to {user_email}.")

    db = next(_get_db())
    today = dt.date.today()
    start_of_day = dt.datetime.combine(today, dt.time.min)
    end_of_day = dt.datetime.combine(today, dt.time.max)

    # Rate-limiting check
    todays_log_count = db.query(NewsletterLog).filter(
        NewsletterLog.user_id == user_id,
        and_(NewsletterLog.created_at >= start_of_day, NewsletterLog.created_at <= end_of_day)
    ).count()

    if todays_log_count >= 3:
        logger.info(f"Newsletter limit of 3 reached today for {user_email}. Skipping.")
        return {"status": "skipped", "message": "Newsletter limit reached for today."}

    creds = _get_email_credentials()
    if not creds["smtp_password"]:
        return {"status": "error", "message": "SMTP_PASSWORD environment variable not set."}

    persona_titles = {
        "Pragmatist": "Your Commander's Briefing",
        "Analyst": "Your Systems Analysis",
        "Catalyst": "Your Creative Catalyst"
    }
    subject = f"{persona_titles.get(persona_name, 'Your State Analysis & Next Steps')} - {today.strftime('%B %d, %Y')}"
    
    html_content = _generate_html_content(user_id, user_email, user_name, session_state, persona_prompt, persona_name)

    success = _send_email(subject, html_content, user_email, creds)

    if success:
        return {"status": "success", "message": f"Newsletter sent to {user_email}."}
    else:
        return {"status": "error", "message": f"Failed to send newsletter to {user_email}."}
