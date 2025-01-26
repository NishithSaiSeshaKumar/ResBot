import os
import time
import re
import logging
import requests
from flask import Flask, request, jsonify, render_template
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from scihub import SciHub

load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Logging setup
LOG_FILE = "logs.html"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(message)s",
)

# Folder to store downloaded papers
DUMP_FOLDER = 'dump'
os.makedirs(DUMP_FOLDER, exist_ok=True)

# Initialize the Telegram bot
TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = Bot(TOKEN)
dispatcher = Dispatcher(bot, None, use_context=True)

# Function to start the bot
def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    update.message.reply_text('Welcome to ResBot! Send me a DOI or URL to download a paper.')
    logging.info(f"User {update.message.chat_id} started the bot.")

# Function to handle messages
def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_input = update.message.text.strip()
    try:
        # Check if the input is DOI or URL
        doi = get_doi_from_url(user_input) if user_input.startswith("http") else user_input

        # Reinitialize SciHub for each request
        sh = SciHub()

        # Download paper
        temp_file_path = os.path.join(DUMP_FOLDER, "temp_download.pdf")
        result = sh.download(doi, path=temp_file_path)

        while not os.path.exists(temp_file_path) or not temp_file_path.endswith('.pdf'):
            time.sleep(1)

        if isinstance(result, dict):
            file_name = result.get('name', 'downloaded_paper.pdf')
            final_file_path = os.path.join(DUMP_FOLDER, file_name)
            os.rename(temp_file_path, final_file_path)
        else:
            final_file_path = temp_file_path
            file_name = os.path.basename(final_file_path)

        with open(final_file_path, 'rb') as file:
            bot.send_document(chat_id=update.message.chat_id, document=file)
        update.message.reply_text(f'Downloaded and sent: {file_name}')
        logging.info(f"File {file_name} sent to user {update.message.chat_id}.")

    except Exception as e:
        update.message.reply_text(f'Error: {str(e)}')
        logging.error(f"Error for user {update.message.chat_id}: {str(e)}")

# Function to extract DOI from URL
def get_doi_from_url(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        match = re.search(r'"doi":"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)"', response.text, re.IGNORECASE)
        if match:
            return match.group(1)
        else:
            raise ValueError("DOI not found.")
    except Exception as e:
        raise ValueError(f"Failed to extract DOI: {str(e)}")

# Register handlers
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Endpoint for Telegram webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "OK", 200

# Logs page
@app.route('/logs', methods=['GET'])
def view_logs():
    with open(LOG_FILE, "r") as file:
        logs = file.read()
    return f"<html><body><pre>{logs}</pre></body></html>"

# Vercel requires this entry point
@app.route('/')
def home():
    return "ResBot is running!"

if __name__ == '__main__':
    app.run(debug=True)
