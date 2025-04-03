#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Standalone script for Telegram Quiz Bot deployment on Koyeb
This file combines both polling mode and a health check server
"""

import os
import sys
import logging
import threading
from flask import Flask, jsonify

from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters
from telegram.ext import ConversationHandler, Dispatcher

# Import handlers
from handlers.quiz_handlers import (
    start, help_command, quiz_callback, answer_callback, 
    time_up_callback, list_quizzes, take_quiz, import_quiz,
    get_results, cancel_quiz
)
from handlers.admin_handlers import (
    create_quiz, add_question, set_quiz_time, set_negative_marking, 
    finalize_quiz, admin_help, admin_command, edit_quiz_time, edit_question_time,
    convert_poll_to_quiz
)

# Import config settings
from config import (
    TELEGRAM_BOT_TOKEN, API_ID, API_HASH, OWNER_ID,
    WEBHOOK_URL, PORT
)

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log")
    ]
)

logger = logging.getLogger(__name__)

# Flask app for health checks
app = Flask(__name__)

def error_handler(update, context):
    """Handle errors in the dispatcher"""
    logger.error(f"Error occurred: {context.error}")
    
    # Get the user who encountered the error
    user_id = update.effective_user.id if update and update.effective_user else "Unknown"
    
    # Log detailed error information
    logger.error(f"Update {update} caused error {context.error} for user {user_id}")
    
    # Notify user about the error
    if update and update.effective_message:
        update.effective_message.reply_text(
            "Sorry, an error occurred while processing your request. Please try again later."
        )

def setup_handlers(dispatcher):
    """Set up all handlers for the bot"""
    
    # Basic command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("list", list_quizzes))
    dispatcher.add_handler(CommandHandler("results", get_results))
    dispatcher.add_handler(CommandHandler("admin", admin_command))
    dispatcher.add_handler(CommandHandler("adminhelp", admin_help))
    
    # Quiz taking conversation handler
    quiz_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("take", take_quiz)],
        states={
            "ANSWERING": [
                CallbackQueryHandler(answer_callback, pattern=r"^answer_"),
                CommandHandler("cancel", cancel_quiz)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_quiz)]
    )
    dispatcher.add_handler(quiz_conv_handler)
    
    # Quiz creation conversation handler
    create_quiz_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("create", create_quiz)],
        states={
            "ADDING_QUESTION": [
                MessageHandler(Filters.text & ~Filters.command, add_question),
                CommandHandler("done", finalize_quiz),
                CommandHandler("cancel", cancel_quiz)
            ],
            "SETTING_TIME": [
                MessageHandler(Filters.text & ~Filters.command, set_quiz_time),
                CommandHandler("cancel", cancel_quiz)
            ],
            "SETTING_NEGATIVE_MARKING": [
                MessageHandler(Filters.text & ~Filters.command, set_negative_marking),
                CommandHandler("cancel", cancel_quiz)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_quiz)]
    )
    dispatcher.add_handler(create_quiz_conv_handler)
    
    # Quiz import handler
    import_quiz_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("import", import_quiz)],
        states={
            "IMPORTING": [
                MessageHandler(Filters.document, import_quiz),
                CommandHandler("cancel", cancel_quiz)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_quiz)]
    )
    dispatcher.add_handler(import_quiz_conv_handler)

    # Edit quiz time handler
    edit_time_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("edittime", edit_quiz_time)],
        states={
            "EDITING_TIME": [
                MessageHandler(Filters.text & ~Filters.command, set_quiz_time),
                CommandHandler("cancel", cancel_quiz)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_quiz)]
    )
    dispatcher.add_handler(edit_time_conv_handler)
    
    # Edit question time handler (direct command, no conversation)
    dispatcher.add_handler(CommandHandler("editquestiontime", edit_question_time))
    
    # Other callback handlers
    dispatcher.add_handler(CallbackQueryHandler(quiz_callback, pattern=r"^quiz_"))
    dispatcher.add_handler(CallbackQueryHandler(time_up_callback, pattern=r"^time_up_"))
    
    # Register error handler
    dispatcher.add_error_handler(error_handler)
    dispatcher.add_handler(MessageHandler(Filters.poll | Filters.forwarded, convert_poll_to_quiz))

# Global variable for the updater
updater = None

def start_bot():
    """Start the bot in polling mode"""
    global updater
    
    # Check if token is available
    token = os.getenv("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
    if not token:
        logger.error("Telegram Bot Token not found. Please set the TELEGRAM_BOT_TOKEN environment variable.")
        exit(1)
    
    # Create the Updater and dispatcher
    updater = Updater(token=token, use_context=True)
    dispatcher = updater.dispatcher
    
    # Set up all handlers
    setup_handlers(dispatcher)
    
    # Start the Bot with clean updates
    logger.info("Starting in polling mode with drop_pending_updates=True")
    updater.start_polling(drop_pending_updates=True)
    
    # Run the bot until you press Ctrl-C
    updater.idle()

# Define Flask routes for health checks
@app.route('/')
def index():
    """Health check endpoint"""
    return jsonify({
        'status': 'active',
        'message': 'Telegram Quiz Bot is running!'
    })

def run_flask():
    """Run the Flask app for health checks"""
    # Run the Flask app on the port required by Koyeb
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == '__main__':
    # Start the Flask app in a separate thread
    logger.info(f"Starting health check server on port {PORT}")
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True  # This ensures the thread will exit when the main program exits
    flask_thread.start()
    
    # Start the bot in polling mode
    logger.info("Starting bot in polling mode")
    start_bot()
