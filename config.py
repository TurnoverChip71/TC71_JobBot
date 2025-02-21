# config.py

# API Keys
OPENAI_API_KEY = "your-openai-api-key"
CLAUDE_API_KEY = "your-claude-api-key"
TELEGRAM_BOT_TOKEN = "your-telegram-bot-token"
TELEGRAM_CHAT_ID = "your-telegram-chat-id"

# AI Model Selection (Default: gpt-4, Options: gpt-4, claude)
AI_MODEL = "gpt-4"

# Job Search Parameters
KEYWORDS = ["Software Engineer", "Python Developer", "Machine Learning Engineer"]
LOCATIONS = ["Remote", "New York", "San Francisco"]

# Key Skills (Optional, Used for AI Matching)
SKILLS = ["Python", "Machine Learning", "Django", "REST APIs"]

# Path to Resume PDF
RESUME_PDF_PATH = "path/to/your/resume.pdf"

# Function to update config dynamically
def update_config(param, value):
    """Updates a configuration parameter dynamically."""
    global AI_MODEL, KEYWORDS, LOCATIONS, SKILLS
    if param == "model":
        AI_MODEL = value
    elif param == "keywords":
        KEYWORDS = value.split(",")
    elif param == "locations":
        LOCATIONS = value.split(",")
    elif param == "skills":
        SKILLS = value.split(",")
    else:
        return "Invalid parameter"
    
    return f"{param} updated to {value}"
