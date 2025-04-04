import os
import logging
from dotenv import load_dotenv
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from flask import Flask, request

# Import your handlers
from admin_handlers import start, help_command, admin_command, create_poll, import_poll, import_questions_from_pdf, on_poll_answer, diagnose_pdf, handle_pdf_callback
from quiz_handlers import create_quiz, list_quizzes, view_quiz, start_quiz, handle_quiz_response, end_quiz, create_marathon, add_to_marathon, handle_marathon_response, list_marathons, view_marathon, start_marathon, end_marathon

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

    # Register command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("admin", admin_command))
    dispatcher.add_handler(CommandHandler("createpoll", create_poll))
    dispatcher.add_handler(CommandHandler("importpoll", import_poll))
    dispatcher.add_handler(CommandHandler("createquiz", create_quiz))
    dispatcher.add_handler(CommandHandler("listquizzes", list_quizzes))
    dispatcher.add_handler(CommandHandler("viewquiz", view_quiz))
    dispatcher.add_handler(CommandHandler("startquiz", start_quiz))
    dispatcher.add_handler(CommandHandler("endquiz", end_quiz))
    dispatcher.add_handler(CommandHandler("createmarathon", create_marathon))
    dispatcher.add_handler(CommandHandler("addtomarathon", add_to_marathon))
    dispatcher.add_handler(CommandHandler("listmarathons", list_marathons))
    dispatcher.add_handler(CommandHandler("viewmarathon", view_marathon))
    dispatcher.add_handler(CommandHandler("startmarathon", start_marathon))
    dispatcher.add_handler(CommandHandler("endmarathon", end_marathon))
    dispatcher.add_handler(CommandHandler("diagnose_pdf", diagnose_pdf))

    # Register message handlers
    dispatcher.add_handler(MessageHandler(Filters.poll, import_poll))
    dispatcher.add_handler(MessageHandler(Filters.document.mime_type("application/pdf"), import_questions_from_pdf))

    # Register callback query handlers
    dispatcher.add_handler(CallbackQueryHandler(handle_quiz_response, pattern=r"quiz_"))
    dispatcher.add_handler(CallbackQueryHandler(handle_marathon_response, pattern=r"marathon_"))
    dispatcher.add_handler(CallbackQueryHandler(handle_pdf_callback, pattern=r"pdf_"))

    # Register poll answer handler
    dispatcher.add_handler(MessageHandler(Filters.poll_answer, on_poll_answer))

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
