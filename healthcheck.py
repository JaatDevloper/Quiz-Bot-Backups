import os
import logging
from dotenv import load_dotenv
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from flask import Flask, request

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

TOKEN = os.environ.get("TELEGRAM_TOKEN")
PORT = int(os.environ.get("PORT", "8080"))
APP_NAME = os.environ.get("APP_NAME")

# Initialize the Flask app
app = Flask(__name__)

# Set up health check route
@app.route('/')
def health():
    return 'I am alive!'

def main():
    # Initialize the updater and dispatcher
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    # Define a simple start command
    def start(update, context):
        update.message.reply_text('Welcome to the Advance Quiz Bot! Use /help to see available commands.')

    def help_command(update, context):
        update.message.reply_text('Available commands:\n/start - Start the bot\n/help - Show this help message')

    # Register basic command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))

    # Start the webhook
    if APP_NAME:
        updater.start_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"https://{APP_NAME}.koyeb.app/{TOKEN}"
        )
        
        # Set up the webhook route
        @app.route('/' + TOKEN, methods=['POST'])
        def webhook():
            update = request.get_json(force=True)
            updater.dispatcher.process_update(update)
            return 'ok'
        
        # Run the Flask app
        app.run(host='0.0.0.0', port=PORT)
    else:
        # If running locally, use polling instead of webhook
        updater.start_polling()
        logger.info("Bot started polling...")
        updater.idle()

if __name__ == '__main__':
    main()
