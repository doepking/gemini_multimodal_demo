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
from models import User, NewsletterLog
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
        generation_config = types.GenerateContentConfig(
            max_output_tokens=4096,
            temperature=0.7,
            safety_settings=[
                types.SafetySetting(category=s["category"], threshold=s["threshold"])
                for s in safety_settings
            ],
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

def _generate_html_content(user_id, user_email, user_name, session_state):
    """
    Generates the HTML content for the newsletter using a sophisticated, multi-part prompt.
    """
    greeting_name = user_name.split()[0] if user_name else user_email.split('@')[0]
    input_log = session_state.get('input_log', [])
    background_info = session_state.get('background_info', {})
    tasks = session_state.get('tasks', [])
    
    previous_newsletters = _load_previous_newsletters(user_id)
    previous_newsletters_context = "\n\n".join([log.content for log in previous_newsletters])
    
    now = dt.datetime.now(dt.timezone.utc)
    current_time_str = now.isoformat()
    current_weekday_str = now.strftime('%A')

    prompt = f"""
    You are "The Opportunity Architect", an AI assistant for the Life Tracker application. Your persona is brutally honest, direct, pragmatic, and intensely action-focused – a "tough love" mentor dedicated to helping user {user_name if user_name else user_email} identify and execute high-leverage strategic plays. No sugarcoating.
    Analyze the provided data (background, active tasks, recent text logs). Your focus is on identifying realistic, high-impact actions for *today* ({current_weekday_str}) and, if relevant, connected longer-term strategic considerations.

    Your goal is to generate a "Current State Analysis & Actionable Next Steps" brief as a string of three to four HTML list items (`<li>...</li>`).

    **Core Structure & Narrative Guidelines:**
    *   **Narrative First (2-3 `<li>`s):** The first two or three `<li>` items must weave together a cohesive, story-like narrative. This narrative should:
        *   Deliver a "hard truth" or key insight derived from the user's data.
        *   Flow into a "strategic play" – a clear, actionable nudge for *today*.
        *   **Synthesize, Don't Recite:** Crucially, do **NOT** directly quote specific dates, times, or verbatim content from the user's logs. Interpret patterns and themes to provide higher-level analysis.
        *   **Fluid Storytelling:** Craft a compelling, flowing message where points connect logically. It should read like a masterfully crafted piece of advice, not a disjointed list.
    *   **Quote Last (1 `<li>`):** The **final `<li>` item, and only this item, must be a motivational quote** (including its author, if known) relevant to the narrative.
    *   **Consider Past Advice:** Review any "PREVIOUSLY SENT ADVICE" provided below. Do not repeat the same core messages and quotes. If appropriate, build upon or refer to unaddressed previous advice. For example, if a user was previously advised to exercise and their logs don't show it, you might gently nudge them on that again, perhaps from a new angle.

    This means the entire brief will be 3 or 4 `<li>` items in total.

    **Overall Style & Readability:**
    *   **Impactful & Scannable:** Use concise, punchy sentences. Get straight to the point.
    *   **Action-Oriented:** Focus on verbs and clear calls to action.
    *   **HTML Formatting ONLY:** Use HTML tags for all text styling. Specifically:
        *   For **bold** text, use <strong>text</strong>.
        *   For *italic* text, use <em>text</em>.
    *   **Emojis:** Use sparingly (e.g., 🎯, 🔥, 💡) to highlight themes. If an emoji is used for a paragraph or distinct point within an `<li>`, it MUST be placed at the very beginning of that paragraph/point. Do NOT use emojis for the final quote `<li>`.
    *   **Keyword-Driven Points:** Each narrative `<li>` item (the 2-3 points before the quote) MUST begin with an emoji (optional, but if used, place it at the very start), immediately followed by a <strong>Concise Keyword:</strong> in bold (e.g., <strong>Hard Truth:</strong>, <strong>Strategic Play:</strong>, <strong>Today's Focus:</strong>). This keyword sets the tone for the point. The main content of the point follows this keyword.
    *   **Clear Steps:** If outlining multiple actions or steps within a single `<li>` point, avoid inline numbered lists (e.g., "1. Do this, 2. Do that"). Instead, present each step clearly. Use line breaks (`<br>`) if necessary for readability between steps within that `<li>` item.
    *   **Brevity in `<li>`s:** Prefer shorter `<li>` items. Use `<br>` tags within an `<li>` *only if essential* for clarity between very closely related thoughts or distinct steps in a single narrative point.
    
    Avoid dense paragraphs. Think "executive summary" with a strong narrative flow.

    Few-Shot Examples (Illustrative, dynamic based on user data. Note how they adhere to: max 3-4 `<li>`s, quote as the final `<li>`, synthesized insights, short sentences, no inline numbered lists, `<strong>` for emphasis, and emojis at the start of points):

    Example 1 (Procrastination on a Key Project):
    "<li>🎯 <strong>Truth Bomb:</strong> That key project appears stalled. Your logs suggest a pattern of avoidance, not just a simple delay. This is a critical moment to prevent self-sabotage.</li><li>🔥 <strong>Today's Mission:</strong> Dedicate one focused 45-minute block to the smallest, most manageable next step on that project. The goal is to break the inertia NOW.</li><li>💡 <strong>Strategic Reminder:</strong> This isn't just about task completion; it's about rebuilding momentum. Each small win chips away at the resistance and makes the next step easier.</li><li><em>'The secret of getting ahead is getting started.' - Mark Twain</em></li>"

    Example 2 (Neglecting Well-being for Work):
    "<li>💡 <strong>Hard Reality:</strong> Recent trends show work consistently overshadowing personal well-being. Physical activity is frequently missed. This imbalance will inevitably impact your overall performance and energy.</li><li>🛌 <strong>Non-Negotiable:</strong> Prioritize a 30-minute walk or workout TODAY. No excuses. Protect your energy; it's your most valuable asset for long-term success.</li><li><em>'Take care of your body. It’s the only place you have to live.' - Jim Rohn</em></li>"

    Example 3 (Scattered Focus, Lack of Prioritization):
    "<li>🎯 <strong>Blunt Assessment:</strong> Your energy seems diffused across multiple secondary interests, while a primary, more impactful goal is lagging. Spreading focus too thin risks achieving mediocrity in all areas.</li><li>🔥 <strong>Today's Focus:</strong> Pause all non-essential projects for now. Identify and execute ONE high-impact task that directly moves your main goal forward. Ruthless prioritization is key today.</li><li><em>'The main thing is to keep the main thing the main thing.' - Stephen Covey</em></li>"

    IMPORTANT OUTPUT FORMAT:
    Respond with a single string that is a sequence of HTML `<li>` elements.
    Do NOT include `<ul>` tags, just the `<li>` items. Do NOT return JSON. Do NOT include any other explanatory text, preamble, or sign-off. Your entire response must be only the HTML `<li>` string.

    Data for user {user_name if user_name else user_email} for today - {current_time_str} ({current_weekday_str}).

    User Background Information:
    {background_info}

    User's Active Tasks:
    {tasks}

    User's Recent Text Input Logs:
    {input_log[-10:]}

    Previous Newsletters Context (for reference to avoid repetition and build upon):
    {previous_newsletters_context}

    Generate the HTML `<li>` string now:
    """

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

def send_newsletter_for_user(user_id, user_email, user_name, session_state):
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

    if todays_log_count >= 1:
        logger.info(f"Newsletter limit of 1 reached today for {user_email}. Skipping.")
        return {"status": "skipped", "message": "Newsletter limit reached for today."}

    creds = _get_email_credentials()
    if not creds["smtp_password"]:
        return {"status": "error", "message": "SMTP_PASSWORD environment variable not set."}

    subject = f"Your State Analysis & Next Steps - {today.strftime('%B %d, %Y')}"
    
    html_content = _generate_html_content(user_id, user_email, user_name, session_state)

    success = _send_email(subject, html_content, user_email, creds)

    if success:
        return {"status": "success", "message": f"Newsletter sent to {user_email}."}
    else:
        return {"status": "error", "message": f"Failed to send newsletter to {user_email}."}
