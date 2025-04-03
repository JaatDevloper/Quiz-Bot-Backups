#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Handlers for admin functionality to create and manage quizzes
"""

import logging
import json
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
import re
import time
from telegram.ext import MessageHandler, Filters
from models.quiz import Quiz, Question
from utils.database import (
    add_quiz, get_quiz, get_quizzes, update_quiz_time,
    update_question_time_limit, delete_quiz, export_quiz
)
from config import ADMIN_USERS, DEFAULT_QUIZ_TIME, DEFAULT_NEGATIVE_MARKING

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Dictionary to store quiz creation data
quiz_creation_data = {}

def admin_command(update: Update, context: CallbackContext) -> None:
    """Show admin commands when /admin is issued."""
    user_id = update.effective_user.id
    
    # Check if the user is an admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, you don't have admin privileges.")
        return
    
    # List of admin commands
    commands = [
        "/create - Create a new quiz",
        "/adminhelp - Show detailed admin help",
        "/edittime (quiz_id) - Edit quiz time limit",
        "/editquestiontime (quiz_id) (question_index) (time_limit) - Edit time limit for a specific question",
        "/import - Import a quiz from JSON",
    ]
    
    update.message.reply_text(
        'Admin Commands:\n\n' + '\n'.join(commands)
    )

def admin_help(update: Update, context: CallbackContext) -> None:
    """Show detailed admin help."""
    user_id = update.effective_user.id
    
    # Check if the user is an admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, you don't have admin privileges.")
        return
    
    help_text = (
        "Admin Help\n\n"
        "Creating a Quiz:\n"
        "1. Use /create to start creating a quiz\n"
        "2. Send the quiz title and description in the format: 'Title | Description'\n"
        "3. Add questions in the format: 'Question text | Option A | Option B | Option C | Option D | CorrectOption(0-3)'\n"
        "   Note: The correct option is 0-indexed (0 for A, 1 for B, etc.)\n"
        "4. Use /done when you've added all questions\n"
        "5. Set the time limit per question in seconds\n"
        "6. Set the negative marking factor (e.g., 0.25 means -0.25 points for wrong answers)\n\n"
        
        "Editing Quiz Times:\n"
        "- Use /edittime (quiz_id) to change the overall time limit for all questions\n"
        "- Use /editquestiontime (quiz_id) (question_index) (time_limit) to set a specific time for one question\n"
        "  Example: /editquestiontime quiz123 2 30\n"
        "  This sets question #3 (index 2) in quiz 'quiz123' to have a 30-second time limit\n\n"
        
        "Importing Quizzes:\n"
        "- Use /import and then upload a JSON file with quiz data\n"
        "- The JSON format should match the exported quiz format\n\n"
        
        "Note: Question indices start at 0, so the first question has index 0, second has index 1, etc."
    )
    
    update.message.reply_text(help_text)
    
def create_quiz(update: Update, context: CallbackContext) -> str:
    """Start the quiz creation process."""
    user_id = update.effective_user.id
    
    # Check if the user is an admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can create quizzes.")
        return 
    
    # Initialize quiz creation data for this user
    quiz_creation_data[user_id] = {
        'questions': []
    }
    
    update.message.reply_text(
        "Let's create a new quiz!\n\n"
        "First, send me the quiz title and description in the format:\n"
        "Title | Description\n\n"
        "For example:\n"
        "History Quiz | Test your knowledge of world history\n\n"
        "Use /cancel to cancel quiz creation."
    )
    
    return "ADDING_QUESTION"

def add_question(update: Update, context: CallbackContext) -> str:
    """Process quiz information or add a question to the quiz being created."""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Check if quiz creation data exists for this user
    if user_id not in quiz_creation_data:
        update.message.reply_text("Something went wrong. Please start again with /create.")
        return "ADDING_QUESTION"
    
    # Check if we need to process quiz title and description
    if 'title' not in quiz_creation_data[user_id]:
        try:
            parts = text.split('|', 1)
            if len(parts) < 2:
                update.message.reply_text(
                    "Please use the format: Title | Description\n\n"
                    "Try again or use /cancel to cancel."
                )
                return "ADDING_QUESTION"
            
            title = parts[0].strip()
            description = parts[1].strip()
            
            quiz_creation_data[user_id]['title'] = title
            quiz_creation_data[user_id]['description'] = description
            
            update.message.reply_text(
                f"Great! Quiz title: '{title}' and description set.\n\n"
                "Now let's add questions. Send each question in the format:\n"
                "Question text | Option A | Option B | Option C | Option D | CorrectOption(0-3)\n\n"
                "For example:\n"
                "What is the capital of France? | Berlin | Paris | London | Madrid | 1\n\n"
                "Note: The correct option number is 0-indexed (0=A, 1=B, 2=C, 3=D)\n\n"
                "Use /done when you've added all questions or /cancel to cancel."
            )
            
            return "ADDING_QUESTION"
        
        except Exception as e:
            logger.error(f"Error processing quiz info: {e}")
            update.message.reply_text(
                "Error processing your input. Please use the format: Title | Description\n\n"
                "Try again or use /cancel to cancel."
            )
            return "ADDING_QUESTION"
    
    # Process a question
    try:
        parts = text.split('|')
        if len(parts) < 6:
            update.message.reply_text(
                "Please use the format: Question | OptionA | OptionB | OptionC | OptionD | CorrectOption(0-3)\n\n"
                "Try again or use /cancel to cancel."
            )
            return "ADDING_QUESTION"
        
        question_text = parts[0].strip()
        options = [p.strip() for p in parts[1:5]]
        correct_option = int(parts[5].strip())
        
        # Validate correct_option
        if correct_option < 0 or correct_option > 3:
            update.message.reply_text(
                "The correct option must be 0, 1, 2, or 3 (corresponding to A, B, C, D).\n\n"
                "Try again or use /cancel to cancel."
            )
            return "ADDING_QUESTION"
        
        # Create a question
        question = {
            'text': question_text,
            'options': options,
            'correct_option': correct_option
        }
        
        # Add to quiz creation data
        quiz_creation_data[user_id]['questions'].append(question)
        
        update.message.reply_text(
            f"Question added! You now have {len(quiz_creation_data[user_id]['questions'])} questions.\n\n"
            "Add another question or use /done to finish adding questions."
        )
        
        return "ADDING_QUESTION"
    
    except Exception as e:
        logger.error(f"Error adding question: {e}")
        update.message.reply_text(
            "Error processing your question. Please use the format:\n"
            "Question | OptionA | OptionB | OptionC | OptionD | CorrectOption(0-3)\n\n"
            "Try again or use /cancel to cancel."
        )
        return "ADDING_QUESTION"
        
def finalize_quiz(update: Update, context: CallbackContext) -> str:
    """Finalize quiz creation and proceed to setting time limit."""
    user_id = update.effective_user.id
    
    # Check if quiz creation data exists for this user
    if user_id not in quiz_creation_data:
        update.message.reply_text("Something went wrong. Please start again with /create.")
        return 
    
    # Check if we have questions
    if 'questions' not in quiz_creation_data[user_id] or len(quiz_creation_data[user_id]['questions']) == 0:
        update.message.reply_text(
            "You haven't added any questions yet. Please add at least one question or use /cancel to cancel."
        )
        return "ADDING_QUESTION"
    
    update.message.reply_text(
        f"You've added {len(quiz_creation_data[user_id]['questions'])} questions.\n\n"
        "Now, set the time limit for each question in seconds.\n"
        f"Default is {DEFAULT_QUIZ_TIME} seconds. Enter a number (10-300):\n\n"
        "Use /cancel to cancel."
    )
    
    return "SETTING_TIME"

def set_quiz_time(update: Update, context: CallbackContext) -> str:
    """Set the time limit for questions in the quiz."""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Check if quiz creation data exists
    if user_id not in quiz_creation_data:
        update.message.reply_text("Something went wrong. Please start again with /create.")
        return 
    
    # Process time limit
    try:
        time_limit = int(text)
        
        # Validate time limit
        if time_limit < 10 or time_limit > 300:
            update.message.reply_text(
                "Time limit must be between 10 and 300 seconds.\n\n"
                "Please try again or use /cancel to cancel."
            )
            return "SETTING_TIME"
        
        # Add time limit to quiz creation data
        quiz_creation_data[user_id]['time_limit'] = time_limit
        
        update.message.reply_text(
            f"Time limit set to {time_limit} seconds per question.\n\n"
            "Finally, set the negative marking factor (0-1).\n"
            f"Default is {DEFAULT_NEGATIVE_MARKING}. Example: 0.25 means -0.25 points for wrong answers.\n\n"
            "Use /cancel to cancel."
        )
        
        return "SETTING_NEGATIVE_MARKING"
    
    except Exception as e:
        logger.error(f"Error setting time limit: {e}")
        update.message.reply_text(
            "Please enter a valid number for the time limit.\n\n"
            "Try again or use /cancel to cancel."
        )
        return "SETTING_TIME"
        
def edit_quiz_time(update: Update, context: CallbackContext) -> str:
    """Start the process to edit a quiz's time limit."""
    user_id = update.effective_user.id
    
    # Check if the user is an admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can edit quizzes.")
        return 
    
    # Check if quiz ID was provided
    if not context.args:
        update.message.reply_text(
            "Please provide a quiz ID. Use /list to see available quizzes."
        )
        return 
    
    quiz_id = context.args[0]
    quiz = get_quiz(quiz_id)
    
    if not quiz:
        update.message.reply_text(
            f"Quiz with ID {quiz_id} not found. Use /list to see available quizzes."
        )
        return
    
    # Store the quiz ID in quiz_creation_data for later use
    quiz_creation_data[user_id] = {
        'quiz_id': quiz_id,
        'current_time': quiz.time_limit
    }
    
    update.message.reply_text(
        f"Editing time limit for quiz: {quiz.title}\n"
        f"Current time limit: {quiz.time_limit} seconds per question.\n\n"
        "Enter a new time limit (10-300 seconds):"
    )
    
    return "EDITING_TIME"

def edit_question_time(update: Update, context: CallbackContext) -> int:
    """Edit the time limit for a specific question in a quiz."""
    user_id = update.effective_user.id
    
    # Check if the user is an admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can edit quizzes.")
        return 
    
    # Check if all arguments were provided
    if len(context.args) < 3:
        update.message.reply_text(
            "Please provide all required arguments: /editquestiontime (quiz_id) (question_index) (time_limit)"
        )
        return 
    
    try:
        quiz_id = context.args[0]
        question_index = int(context.args[1])
        time_limit = int(context.args[2])
        
        # Validate time_limit
        if time_limit < 10 or time_limit > 300:
            update.message.reply_text(
                "Time limit must be between 10 and 300 seconds."
            )
            return 
        
        # Get the quiz
        quiz = get_quiz(quiz_id)
        
        if not quiz:
            update.message.reply_text(
                f"Quiz with ID {quiz_id} not found. Use /list to see available quizzes."
            )
            return 
        
        # Check if question_index is valid
        if question_index < 0 or question_index >= len(quiz.questions):
            update.message.reply_text(
                f"Invalid question index. The quiz has {len(quiz.questions)} questions, "
                f"so the valid indices are 0 to {len(quiz.questions) - 1}."
            )
            return 
        
        # Update the question time limit
        if update_question_time_limit(quiz_id, question_index, time_limit):
            update.message.reply_text(
                f"Time limit for question {question_index+1} in quiz {quiz.title} "
                f"has been updated to {time_limit} seconds."
            )
        else:
            update.message.reply_text(
                "Failed to update question time limit. Please try again."
            )
        
        return 
    
    except Exception as e:
        logger.error(f"Error editing question time: {e}")
        update.message.reply_text(
            "Error processing your request. Please use the format:\n"
            "/editquestiontime (quiz_id) (question_index) (time_limit)"
        )
        return

def convert_poll_to_quiz(update: Update, context: CallbackContext) -> None:
    """Convert a forwarded poll to a quiz."""
    # Check if this is a poll
    if update.message.poll:
        poll = update.message.poll
        
        # Extract poll information
        question = poll.question
        options = [option.text for option in poll.options]
        
        # Clean up the question text
        # Remove patterns like [1/100], [Q1], etc.
        clean_question = re.sub(r'\[\d+\/\d+\]|\[Q\d+\]', '', question).strip()
        
        # Store in context to start quiz creation
        user_id = update.effective_user.id
        context.user_data['creating_quiz'] = True
        context.user_data['quiz_title'] = f"Poll Quiz {int(time.time())}"
        context.user_data['quiz_description'] = f"Created from poll: {clean_question[:30]}..."
        context.user_data['quiz'] = Quiz(
            context.user_data['quiz_title'],
            context.user_data['quiz_description'],
            user_id
        )
        
        # Create a new question from the poll
        # Default correct answer is the first option (user will need to edit this)
        new_question = Question(clean_question, options, 0)
        context.user_data['quiz'].add_question(new_question)
        
        # Inform user that a quiz has been created from the poll
        update.message.reply_text(
            f"📊 Created a quiz from the poll!\n\n"
            f"*Title*: {context.user_data['quiz_title']}\n"
            f"*Description*: {context.user_data['quiz_description']}\n\n"
            f"The quiz has 1 question with {len(options)} options.\n"
            f"⚠️ *Note*: The first option is set as correct by default.\n\n"
            f"Do you want to:\n"
            f"1. Add more questions with /addquestion\n"
            f"2. Edit correct answer with /editanswer\n"
            f"3. Finalize the quiz with /finalize",
            parse_mode='Markdown'
        )
        
        return True
    
    # If someone forwards a message from a quiz bot
    elif update.message.forward_from and update.message.text:
        if update.message.forward_from.username and "quiz" in update.message.forward_from.username.lower():
            # Try to extract question and options from text
            text = update.message.text
            
            # Clean up the text (remove patterns like [1/100])
            clean_text = re.sub(r'\[\d+\/\d+\]|\[Q\d+\]', '', text).strip()
            
            # Try to parse the text to extract question and options
            lines = clean_text.split('\n')
            if len(lines) >= 2:
                question = lines[0].strip()
                options = []
                correct_option = 0  # Default
                
                # Extract options (assuming they're in format "A. Option")
                for i, line in enumerate(lines[1:]):
                    line = line.strip()
                    if line and (line[0].isalpha() or line[0].isdigit()) and len(line) > 2 and line[1] in ['.', ')', ']']:
                        option = line[2:].strip()
                        options.append(option)
                        
                        # Look for indicators of correct answer like "(correct)" or "✓"
                        if "correct" in line.lower() or "✓" in line or "✅" in line:
                            correct_option = len(options) - 1
                
                if options:
                    # Store in context to start quiz creation
                    user_id = update.effective_user.id
                    context.user_data['creating_quiz'] = True
                    context.user_data['quiz_title'] = f"Imported Quiz {int(time.time())}"
                    context.user_data['quiz_description'] = f"Created from imported message: {question[:30]}..."
                    context.user_data['quiz'] = Quiz(
                        context.user_data['quiz_title'],
                        context.user_data['quiz_description'],
                        user_id
                    )
                    
                    # Create a new question
                    new_question = Question(question, options, correct_option)
                    context.user_data['quiz'].add_question(new_question)
                    
                    # Inform user that a quiz has been created
                    update.message.reply_text(
                        f"📝 Created a quiz from the forwarded message!\n\n"
                        f"*Title*: {context.user_data['quiz_title']}\n"
                        f"*Description*: {context.user_data['quiz_description']}\n\n"
                        f"The quiz has 1 question with {len(options)} options.\n"
                        f"⚠️ *Note*: Option {chr(65+correct_option)} is set as correct by default.\n\n"
                        f"Do you want to:\n"
                        f"1. Add more questions with /addquestion\n"
                        f"2. Edit correct answer with /editanswer\n"
                        f"3. Finalize the quiz with /finalize",
                        parse_mode='Markdown'
                    )
                    
                    return True
    
    return False
        
        
        
                    
