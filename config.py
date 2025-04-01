#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Configuration settings for the Telegram Quiz Bot
"""

import os

# Bot configuration
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7867071540:AAF7T8I0vPgvFPVT7vb0v8sMIVYLKeH41-0")
API_ID = os.environ.get("API_ID", "28624690")  # Your Telegram API ID
API_HASH = os.environ.get("API_HASH", "67e6593b5a9b5ab20b11ccef6700af5b")  # Your Telegram API Hash
OWNER_ID = os.environ.get("OWNER_ID", "7656415064")  # Telegram ID of the bot owner

DEFAULT_QUIZ_TIME = 60  # Default time limit for each question in seconds
ADMIN_USERS = [int(id) for id in os.environ.get("ADMIN_USERS", OWNER_ID).split(",") if id]  # List of admin user IDs who can create/edit quizzes

# Quiz settings
DEFAULT_NEGATIVE_MARKING = 0.25  # Default negative marking coefficient

# PDF Generation settings
PDF_TEMPLATE_PATH = "templates/result_template.html"
FONT_PATH = os.path.join(os.path.dirname(__file__), "resources", "fonts")
LOGO_PATH = None  # Set to your logo path if needed

# Database Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

# Web server configuration for webhook mode
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")  # e.g., https://your-app-name.koyeb.app/webhook
PORT = int(os.environ.get("PORT", "8080"))
