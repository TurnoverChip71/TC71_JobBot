import time
import openai
import anthropic
import json
import requests
import PyPDF2
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from config import OPENAI_API_KEY, CLAUDE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, KEYWORDS, LOCATIONS, SKILLS, RESUME_PDF_PATH, AI_MODEL

def extract_text_from_pdf(pdf_path):
    """Extract text from a PDF file."""
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        text = "".join([page.extract_text() for page in reader.pages if page.extract_text()])
    return text

RESUME_TEXT = extract_text_from_pdf(RESUME_PDF_PATH)

def setup_driver():
    """Set up the Selenium WebDriver."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    return driver

def scrape_indeed_jobs(keywords, locations, num_jobs=10):
    """Scrape Indeed job listings for multiple keywords and locations."""
    driver = setup_driver()
    jobs = []
    
    for keyword in keywords:
        for location in locations:
            base_url = "https://www.indeed.com/jobs?q={}&l={}".format(keyword, location)
            driver.get(base_url)
            time.sleep(3)  # Let the page load
            
            job_cards = driver.find_elements(By.CLASS_NAME, "job_seen_beacon")
            for card in job_cards[:num_jobs]:
                try:
                    title = card.find_element(By.CSS_SELECTOR, "h2 a").text
                    company = card.find_element(By.CLASS_NAME, "companyName").text
                    job_location = card.find_element(By.CLASS_NAME, "companyLocation").text
                    link = card.find_element(By.CSS_SELECTOR, "h2 a").get_attribute("href")
                    jobs.append({"title": title, "company": company, "location": job_location, "link": link})
                except Exception as e:
                    print("Error scraping job:", e)
    
    driver.quit()
    return jobs

def analyze_job_match(job_description, resume_text, skills):
    """Use AI model to compare a job description with a resume and skills and return a match score."""
    if AI_MODEL == "gpt-4":
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an AI that analyzes job fit."},
                {"role": "user", "content": f"Compare this job description: {job_description} with this resume: {resume_text} and these key skills: {', '.join(skills)}. Rate the fit from 0 to 100%."}
            ],
            api_key=OPENAI_API_KEY
        )
    elif AI_MODEL == "claude":
        response = anthropic.Anthropic(api_key=CLAUDE_API_KEY).messages.create(
            model="claude-2",
            messages=[
                {"role": "system", "content": "You are an AI that analyzes job fit."},
                {"role": "user", "content": f"Compare this job description: {job_description} with this resume: {resume_text} and these key skills: {', '.join(skills)}. Rate the fit from 0 to 100%."}
            ]
        )
    else:
        return "0%"
    
    return response["choices"][0]["message"]["content"]

def auto_apply_linkedin(job_link):
    """Automate LinkedIn Easy Apply."""
    driver = setup_driver()
    driver.get(job_link)
    time.sleep(5)  # Allow time for the page to load
    
    try:
        apply_button = driver.find_element(By.CLASS_NAME, "jobs-apply-button")
        apply_button.click()
        time.sleep(2)
        # Additional steps like filling forms can be added here
        print("Applied to:", job_link)
    except Exception as e:
        print("Error applying:", e)
    
    driver.quit()

def send_notification(job_title, company, link):
    """Send a Telegram notification with job details."""
    message = f"New Job Match!\n{job_title} at {company}\nApply here: {link}"
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage", data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

def handle_telegram_command(command):
    """Handle Telegram bot commands to update config."""
    if command.startswith("/set_model"):
        global AI_MODEL
        AI_MODEL = command.split(" ")[1]
        return f"AI model updated to {AI_MODEL}"
    return "Unknown command"

if __name__ == "__main__":
    # Step 1: Scrape jobs
    jobs = scrape_indeed_jobs(KEYWORDS, LOCATIONS)
    
    for job in jobs:
        match_score = analyze_job_match(job['title'], RESUME_TEXT, SKILLS)
        if int(match_score.replace("%", "")) > 75:
            send_notification(job['title'], job['company'], job['link'])
            auto_apply_linkedin(job['link'])
          
