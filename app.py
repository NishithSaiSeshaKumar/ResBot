import os
import time
import re
import requests
from flask import Flask, request, jsonify, render_template
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from scihub import SciHub
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Folder to store downloaded papers
DUMP_FOLDER = 'dump'
LOG_FILE = 'logs.txt'

# Ensure the "dump" folder exists
if not os.path.exists(DUMP_FOLDER):
    os.makedirs(DUMP_FOLDER)

# Write logs to a file for monitoring
def write_log(message):
    with open(LOG_FILE, 'a') as log_file:
        log_file.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text('Welcome to ResBot! Send me a DOI or URL to download a paper.')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text.strip()
    write_log(f"Received input: {user_input}")
    try:
        # Check if the input is a DOI or a URL
        if user_input.startswith("http") or user_input.startswith("www"):
            doi = get_doi_from_url(user_input)
        else:
            doi = user_input

        # Reinitialize SciHub for each request
        sh = SciHub()

        # Generate a temporary file path for the download
        temp_file_path = os.path.join(DUMP_FOLDER, "temp_download.pdf")
        
        # Download the paper
        result = sh.download(doi, path=temp_file_path)

        # Wait until the file is fully downloaded
        while not os.path.exists(temp_file_path) or not temp_file_path.endswith('.pdf'):
            time.sleep(1)

        # Move the downloaded file to a new location
        if isinstance(result, dict):
            file_name = result.get('name', 'downloaded_paper.pdf')
            final_file_path = os.path.join(DUMP_FOLDER, file_name)
            os.rename(temp_file_path, final_file_path)
        else:
            final_file_path = temp_file_path
            file_name = os.path.basename(final_file_path)

        # Send the downloaded file to the user
        with open(final_file_path, 'rb') as file:
            await context.bot.send_document(chat_id=update.message.chat_id, document=file)
            await update.message.reply_text(f'Downloaded and sent: {file_name}')
        write_log(f"Paper sent: {file_name}")

    except Exception as e:
        error_message = f"Error: {str(e)}"
        await update.message.reply_text(error_message)
        write_log(error_message)

# Function to extract DOI from a URL
def get_doi_from_url(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        # Search for DOI in the page content
        match = re.search(r'"doi":"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)"', response.text, re.IGNORECASE)
        if match:
            return match.group(1)
        else:
            raise ValueError("DOI not found.")
    except Exception as e:
        raise ValueError(f"Failed to extract DOI: {str(e)}")

# Flask route to view logs
@app.route('/logs')
def view_logs():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r') as log_file:
            logs = log_file.read()
        return f"<pre>{logs}</pre>"
    return "No logs available."

# Flask route for Telegram bot webhook (entry point)
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), bot)
        application.update_queue.put(update)
        return "OK", 200

# Flask route to test the app
@app.route('/')
def home():
    return "ResBot is running!"

# Main function
if __name__ == '__main__':
    # Telegram Bot setup
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    bot = Application.builder().token(TOKEN).build()

    # Add handlers
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run Flask app
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
