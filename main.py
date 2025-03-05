import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CallbackContext
)
import PyPDF2
from docx import Document
import openai
import anthropic
from anthropic import Anthropic
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import re

# Configure logging
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Load config
with open('config.json') as f:
    config = json.load(f)
    TELEGRAM_BOT_TOKEN = config['TELEGRAM_BOT_TOKEN']
    OPENAI_API_KEY = config['OPENAI_API_KEY']
    CLAUDE_API_KEY = config['CLAUDE_API_KEY']

# Initialize AI clients
openai.api_key = OPENAI_API_KEY
claude = Anthropic(api_key=CLAUDE_API_KEY)

# Store user data
user_data = {}

def extract_text(file_path: str) -> str:
    """Extract text from PDF or DOCX file."""
    try:
        if file_path.endswith('.pdf'):
            with open(file_path, 'rb') as file:
                return ' '.join(page.extract_text() for page in PyPDF2.PdfReader(file).pages)
        elif file_path.endswith('.docx'):
            return ' '.join(paragraph.text for paragraph in Document(file_path).paragraphs)
    except Exception as e:
        logger.error(f"File processing error: {e}")
    return ''

async def analyze_cv_with_ai(text: str, model: str) -> dict:
    """Use AI (GPT-4 or Claude) to analyze CV text."""
    try:
        prompt = """Analyze this CV and provide a detailed JSON response with:
        {
            "technical_skills": {
                "programming_languages": [],
                "frameworks": [],
                "databases": [],
                "tools": []
            },
            "soft_skills": [],
            "experience": {
                "years": "",
                "roles": [],
                "industries": []
            },
            "education": {
                "level": "",
                "field": "",
                "institutions": []
            },
            "achievements": [],
            "certifications": []
        }
        Make sure to identify ALL skills and categorize them properly.
        """

        if model == 'claude':
            response = claude.completions.create(
                model="claude-2",
                prompt=f"{prompt}\nCV text:\n{text}",
                max_tokens_to_sample=2000,
                temperature=0
            )
            return json.loads(response.completion)
        else:  # GPT-4
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional CV analyzer focusing on technical roles."},
                    {"role": "user", "content": f"{prompt}\nCV text:\n{text}"}
                ]
            )
            return json.loads(response.choices[0].message.content)

    except Exception as e:
        logger.error(f"AI analysis error with {model}: {e}")
        return {}

def search_jobs(analysis: dict, locations: list) -> list:
    """Search for matching jobs on Indeed."""
    jobs = []
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36')
        
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

        # Create search query from skills and roles
        search_terms = []
        if analysis.get('technical_skills'):
            for category in analysis['technical_skills'].values():
                search_terms.extend(category[:2])  # Take top 2 from each category
        if analysis.get('experience', {}).get('roles'):
            search_terms.extend(analysis['experience']['roles'][:2])  # Take last 2 roles

        search_query = ' OR '.join(search_terms[:5])  # Use top 5 terms

        for location in locations:
            indeed_url = f"https://www.indeed.com/jobs?q={search_query}&l={location}&sort=date"
            driver.get(indeed_url)
            time.sleep(3)  # Wait for page load

            try:
                job_cards = driver.find_elements(By.CSS_SELECTOR, "div.job_seen_beacon")
                for card in job_cards[:7]:  # Get more results per location
                    try:
                        title = card.find_element(By.CLASS_NAME, "jobTitle").text
                        company = card.find_element(By.CLASS_NAME, "companyName").text
                        link = card.find_element(By.CSS_SELECTOR, "a.jcs-JobTitle").get_attribute('href')
                        salary = card.find_elements(By.CLASS_NAME, "salary-snippet")
                        salary_text = salary[0].text if salary else "Not specified"
                        
                        jobs.append({
                            'title': title,
                            'company': company,
                            'location': location,
                            'salary': salary_text,
                            'link': link,
                            'posted': 'Recent'  # Could extract exact date if needed
                        })
                    except Exception as e:
                        logger.error(f"Error extracting job details: {e}")
                        continue
            except Exception as e:
                logger.error(f"Error finding job cards: {e}")
                continue

        driver.quit()
    except Exception as e:
        logger.error(f"Job search error: {e}")
    
    return jobs

async def handle_callback(update: Update, context: CallbackContext) -> None:
    """Handle callback queries from inline keyboards."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("model_"):
        model = query.data.replace("model_", "")
        chat_id = update.effective_chat.id
        user_data[chat_id] = {'model': model}
        await query.edit_message_text(
            f"*Selected {model.upper()}*\nPlease upload your resume (PDF or DOCX)",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_document(update: Update, context: CallbackContext) -> None:
    """Process uploaded CV documents."""
    chat_id = update.effective_chat.id
    doc = update.message.document

    # Reset any existing user data for this chat
    if chat_id in user_data:
        user_data[chat_id] = {}

    if doc.mime_type not in ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        await update.message.reply_text("*Please upload your CV as a PDF or DOCX file.*", parse_mode=ParseMode.MARKDOWN)
        return

    if 'model' not in user_data.get(chat_id, {}):
        keyboard = [
            [InlineKeyboardButton("GPT-4", callback_data="model_gpt4"),
             InlineKeyboardButton("Claude", callback_data="model_claude")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "*Please select an AI model to analyze your CV:*",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        return

    try:
        await update.message.reply_text("*🔍 Analyzing your CV...*", parse_mode=ParseMode.MARKDOWN)
        
        file = await context.bot.get_file(doc.file_id)
        file_path = f"cv_{chat_id}{os.path.splitext(doc.file_name)[1]}"
        await file.download_to_drive(file_path)
        
        text = extract_text(file_path)
        if not text:
            await update.message.reply_text("*❌ Could not read the document. Please ensure it's not password protected.*", parse_mode=ParseMode.MARKDOWN)
            return

        analysis = await analyze_cv_with_ai(text, user_data[chat_id]['model'])
        user_data[chat_id].update({'analysis': analysis})

        # Format and send analysis results
        message = "*📑 CV Analysis Results*\n\n"
        
        if analysis.get('technical_skills'):
            message += "*🔧 Technical Skills*\n"
            for category, skills in analysis['technical_skills'].items():
                if skills:
                    message += f"*{category.title()}:*\n▫️ {', '.join(skills)}\n\n"

        if analysis.get('soft_skills'):
            message += "*🤝 Professional Skills*\n"
            message += "▫️ " + "\n▫️ ".join(analysis['soft_skills']) + "\n\n"
        
        if analysis.get('experience'):
            exp = analysis['experience']
            message += f"*👨‍💼 Experience:* {exp.get('years', 'Not specified')}\n"
            if exp.get('roles'):
                message += "*Recent Roles:*\n▫️ " + "\n▫️ ".join(exp['roles']) + "\n"
            if exp.get('industries'):
                message += "*Industries:*\n▫️ " + "\n▫️ ".join(exp['industries']) + "\n\n"
        
        if analysis.get('education'):
            edu = analysis['education']
            message += f"*🎓 Education:* {edu.get('level', '')} in {edu.get('field', '')}\n"
            if edu.get('institutions'):
                message += "▫️ " + "\n▫️ ".join(edu['institutions']) + "\n\n"
        
        if analysis.get('certifications'):
            message += "*📜 Certifications:*\n"
            message += "▫️ " + "\n▫️ ".join(analysis['certifications']) + "\n\n"

        message += "*🌍 Please enter your preferred locations (comma-separated):*\n"
        message += "_Example: London, Manchester, Remote_"

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("*❌ Error processing your CV. Please try again.*", parse_mode=ParseMode.MARKDOWN)
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

async def handle_message(update: Update, context: CallbackContext) -> None:
    """Handle location input and search jobs."""
    chat_id = update.effective_chat.id
    if chat_id not in user_data:
        await update.message.reply_text("*Please upload your resume first.*", parse_mode=ParseMode.MARKDOWN)
        return

    locations = [loc.strip() for loc in update.message.text.split(',') if loc.strip()]
    if not locations:
        await update.message.reply_text("*Please enter valid locations.*", parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text("*🔍 Searching for matching jobs...*", parse_mode=ParseMode.MARKDOWN)
    
    jobs = search_jobs(user_data[chat_id], locations)
    
    if jobs:
        message = "*🎯 Matching Jobs*\n\n"
        for job in jobs:
            message += f"*{job['title']}*\n"
            message += f"🏢 {job['company']}\n"
            message += f"📍 {job['location']}\n"
            message += f"💰 {job['salary']}\n"
            message += f"🔗 [Apply Here]({job['link']})\n\n"
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(
            "*❌ No matching jobs found. Try different locations or upload an updated resume.*",
            parse_mode=ParseMode.MARKDOWN
        )

def main() -> None:
    """Start the bot."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    
    # Start polling
    app.run_polling()

if __name__ == "__main__":
    main()