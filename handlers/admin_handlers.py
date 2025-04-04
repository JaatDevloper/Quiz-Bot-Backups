#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Handlers for admin functionality to create and manage quizzes
"""

import logging
import json
from io import BytesIO

import io
import re
import os
import tempfile
from models.quiz import Quiz, Question
from utils.database import add_quiz, get_quiz
from telegram import Update
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler
import re
import time
from datetime import datetime
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
    """Show admin help message."""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_USERS:
        update.message.reply_text("You are not authorized to use admin commands.")
        return
    
    update.message.reply_text(
        "🔐 Admin Commands:\n\n"
        "/create - Create a new quiz\n"
        "/edittime - Edit time limit for a quiz\n"
        "/editquestiontime - Edit time limit for a specific question\n"
        "/start_marathon - Start a marathon quiz (multiple questions)\n"
        "/finalize_marathon - Save the current marathon quiz\n"
        "/cancel_marathon - Cancel the current marathon quiz\n"
        "/correct <number> - Set the correct answer for the last added question\n\n"
        "🔄 Poll to Quiz:\n"
        "Forward any poll to convert it to a quiz\n\n"
        "📑 PDF Import:\n"
        "Send a PDF file to import questions\n"
        "PDF should contain questions in format:\n"
        "Question: What is X?\n"
        "A) Option 1\n"
        "B) Option 2\n"
        "C) Option 3\n"
        "D) Option 4\n"
        "Correct: A"
    )

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
    """Convert a poll to a quiz or add it to a marathon quiz."""
    try:
        user_id = update.effective_user.id
        
        # Check if user is admin
        if user_id not in ADMIN_USERS:
            return
        
        # Check if the message contains a poll
        if update.message and update.message.poll:
            poll = update.message.poll
            
            # Check if there's an active marathon
            if 'marathon_quiz' in context.user_data:
                # Add the question to the marathon quiz
                quiz = context.user_data['marathon_quiz']
                
                # Create a question from the poll
                from models.quiz import Question
                options = [option.text for option in poll.options]
                if len(options) < 2:
                    update.message.reply_text("Poll must have at least 2 options.")
                    return
                
                question = Question(
                    text=poll.question,
                    options=options,
                    correct_option=0  # Default first option is correct
                )
                
                # Add the question to the quiz
                quiz.questions.append(question)
                
                # Send confirmation
                update.message.reply_text(
                    f"➕ Question added to marathon quiz.\n\n"
                    f"Question: {poll.question[:50]}...\n"
                    f"Options: {len(options)}\n\n"
                    f"Total questions: {len(quiz.questions)}\n"
                    f"⚠️ Note: The first option is set as correct by default.\n\n"
                    f"You can:\n"
                    f"- Use /correct <number> to change the correct option\n"
                    f"- Forward more polls to add more questions\n"
                    f"- Use /finalize_marathon to save the quiz"
                )
                
            else:
                # Create a standalone quiz as before
                try:
                    # Get poll options
                    options = [option.text for option in poll.options]
                    if len(options) < 2:
                        update.message.reply_text("Poll must have at least 2 options.")
                        return
                    
                    # Create a quiz from the poll
                    import uuid
                    from models.quiz import Quiz, Question
                    
                    # Generate a quiz ID
                    quiz_id = str(uuid.uuid4())
                    update.message.reply_text(f"Creating quiz with ID: {quiz_id[:8]}...")
                    
                    # Create quiz title and description
                    title = f"Poll Quiz {quiz_id[-8:]}"
                    description = f"Created from poll: {poll.question[:30]}..."
                    
                    # Create the quiz object - WITHOUT id parameter
                    quiz = Quiz(
                        title=title,
                        description=description,
                        creator_id=user_id,
                        time_limit=15,  # Default time limit
                        negative_marking_factor=0  # Default no negative marking
                    )
                    
                    # Set the ID after creation
                    quiz.id = quiz_id
                    
                    # Add the question from the poll
                    update.message.reply_text("Adding question to quiz...")
                    
                    question = Question(
                        text=poll.question,
                        options=options,
                        correct_option=0  # Default first option is correct
                    )
                    
                    quiz.questions.append(question)
                    
                    # Save to database using add_quiz
                    update.message.reply_text("Saving quiz to database...")
                    from utils.database import add_quiz
                    saved_id = add_quiz(quiz)
                    
                    # Send confirmation
                    update.message.reply_text(
                        f"✅ Quiz created successfully!\n\n"
                        f"Title: {title}\n"
                        f"Description: {description}\n\n"
                        f"The quiz has 1 question with {len(options)} options.\n"
                        f"⚠️ Note: The first option is set as correct by default.\n\n"
                        f"Users can take this quiz with:\n/take {saved_id}\n\n"
                        f"Tip: Use /start_marathon to create a quiz with multiple questions."
                    )
                    
                except Exception as e:
                    import traceback
                    logger.error(f"Error creating quiz: {str(e)}")
                    logger.error(traceback.format_exc())
                    update.message.reply_text(f"Error creating quiz: {str(e)}")
        else:
            update.message.reply_text("No poll found in this message. Please forward a message containing a poll.")
                
    except Exception as e:
        import traceback
        logger.error(f"Error in convert_poll_to_quiz: {str(e)}")
        logger.error(traceback.format_exc())
        if update and update.message:
            update.message.reply_text(f"Error processing poll: {str(e)}")

def set_negative_marking(update: Update, context: CallbackContext) -> str:
    """Set the negative marking factor and finalize the quiz."""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Check if quiz creation data exists
    if user_id not in quiz_creation_data:
        update.message.reply_text("Something went wrong. Please start again with /create.")
        return 
    
    # Process negative marking
    try:
        negative_marking = float(text)
        
        # Validate negative marking
        if negative_marking < 0 or negative_marking > 1:
            update.message.reply_text(
                "Negative marking factor must be between 0 and 1.\n\n"
                "Please try again or use /cancel to cancel."
            )
            return "SETTING_NEGATIVE_MARKING"
        
        # Get quiz creation data
        creation_data = quiz_creation_data[user_id]
        title = creation_data['title']
        description = creation_data['description']
        time_limit = creation_data['time_limit']
        
        # Create the quiz
        quiz = Quiz(title, description, user_id, time_limit, negative_marking)
        
        # Add questions
        for q_data in creation_data['questions']:
            question = Question(q_data['text'], q_data['options'], q_data['correct_option'])
            quiz.add_question(question)
        
        # Add to database
        quiz_id = add_quiz(quiz)
        
        # Clean up creation data
        if user_id in quiz_creation_data:
            del quiz_creation_data[user_id]
        
        update.message.reply_text(
            f"Quiz created successfully!\n\n"
            f"Title: {title}\n"
            f"Description: {description}\n"
            f"Questions: {len(quiz.questions)}\n"
            f"Time limit: {time_limit} seconds per question\n"
            f"Negative marking: {negative_marking}\n\n"
            f"Quiz ID: {quiz_id}\n\n"
            f"Users can take this quiz with /take {quiz_id}"
        )
        
        return 
    
    except Exception as e:
        logger.error(f"Error setting negative marking: {e}")
        update.message.reply_text(
            "Please enter a valid number for the negative marking factor.\n\n"
            "Try again or use /cancel to cancel."
        )
        return "SETTING_NEGATIVE_MARKING"

def handle_addquestion(update: Update, context: CallbackContext) -> None:
    """Add a question to a quiz being created from a poll."""
    user_id = update.effective_user.id
    
    # Get the current quiz creation session for this user
    # Implementation depends on how you're storing the quiz creation state
    
    # Add a new question to the quiz
    # Implementation depends on your data structures

def handle_editanswer(update: Update, context: CallbackContext) -> None:
    """Edit the correct answer for a question in a quiz."""
    user_id = update.effective_user.id
    
    # Get the current quiz creation session for this user
    # Implementation depends on how you're storing the quiz creation state
    
    # Parse the message for the answer index
    # Update the correct answer
    # Implementation depends on your data structures

def handle_finalize(update: Update, context: CallbackContext) -> None:
    """Finalize a quiz created from a poll."""
    user_id = update.effective_user.id
    
    # Get the current quiz creation session for this user
    # Implementation depends on how you're storing the quiz creation state
    
    # Finalize the quiz (save to database, etc.)
    # Implementation depends on your data structures

# Add these functions to your admin_handlers.py file

def add_question_command(update: Update, context: CallbackContext) -> None:
    """Add a question to a quiz being created from a poll."""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can use this command.")
        return
    
    # Check if there's an active quiz creation session for this poll
    if 'poll_quiz' not in context.user_data:
        update.message.reply_text("No active poll-to-quiz conversion. Please forward a poll first.")
        return
    
    # Ask the user to send the question text
    update.message.reply_text(
        "Please send the question text for the new question.\n"
        "Format: Question text\nOption A|Option B|Option C|Option D\nCorrect Option (0-3)"
    )
    
    # Set the state to wait for the question
    context.user_data['waiting_for_poll_question'] = True

def edit_answer_command(update: Update, context: CallbackContext) -> None:
    """Edit the correct answer for a quiz created from a poll."""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can use this command.")
        return
    
    # Check if there's an active quiz creation session for this poll
    if 'poll_quiz' not in context.user_data:
        update.message.reply_text("No active poll-to-quiz conversion. Please forward a poll first.")
        return
    
    # Get the current quiz being created
    quiz = context.user_data['poll_quiz']
    
    # Create a keyboard with question numbers
    keyboard = []
    for i, question in enumerate(quiz.questions):
        keyboard.append([InlineKeyboardButton(f"Question {i+1}", callback_data=f"edit_answer_{i}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Ask the user to select a question
    update.message.reply_text(
        "Please select a question to edit the correct answer:",
        reply_markup=reply_markup
    )

def finalize_command(update: Update, context: CallbackContext) -> None:
    """Finalize a quiz created from a poll."""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can use this command.")
        return
    
    # Check if there's an active quiz creation session for this poll
    if 'poll_quiz' not in context.user_data:
        update.message.reply_text("No active poll-to-quiz conversion. Please forward a poll first.")
        return
    
    # Get the quiz being created
    quiz = context.user_data['poll_quiz']
    
    # Set default values if not already set
    if not hasattr(quiz, 'time_limit') or quiz.time_limit is None:
        quiz.time_limit = 30  # Default time limit of 30 seconds
    
    if not hasattr(quiz, 'negative_marking_factor') or quiz.negative_marking_factor is None:
        quiz.negative_marking_factor = 0  # Default no negative marking
    
    # Save the quiz to the database
    quiz_id = save_quiz(quiz, user_id)
    
    # Send confirmation to the user
    update.message.reply_text(
        f"Quiz has been finalized and saved!\n\n"
        f"Title: {quiz.title}\n"
        f"Description: {quiz.description}\n"
        f"Questions: {len(quiz.questions)}\n"
        f"ID: {quiz_id}\n\n"
        f"Users can take this quiz with:\n/take {quiz_id}"
    )
    
    # Clear the quiz creation data
    if 'poll_quiz' in context.user_data:
        del context.user_data['poll_quiz']

def handle_admin_input(update: Update, context: CallbackContext) -> None:
    """Handle text input during admin operations."""
    if 'waiting_for_question' in context.user_data and context.user_data['waiting_for_question']:
        # Process input for adding a question
        text = update.message.text
        
        try:
            # Parse the input (question, options, correct option)
            lines = text.strip().split('\n')
            question_text = lines[0]
            options_text = lines[1]
            correct_option = int(lines[2])
            
            options = options_text.split('|')
            
            # Add the question to the quiz
            quiz = context.user_data['poll_quiz']
            
            question = Question(
                text=question_text,
                options=options,
                correct_option=correct_option
            )
            
            quiz.questions.append(question)
            
            # Send confirmation
            update.message.reply_text(
                f"Question added!\n\n"
                f"Total questions: {len(quiz.questions)}\n\n"
                f"What would you like to do next?\n"
                f"1. Add more questions with /addquestion\n"
                f"2. Edit correct answers with /editanswer\n"
                f"3. Finalize the quiz with /finalize"
            )
            
            # Reset the waiting state
            context.user_data['waiting_for_question'] = False
            
        except Exception as e:
            update.message.reply_text(
                "Invalid format. Please use the format:\n\n"
                "Question text\n"
                "Option A|Option B|Option C|Option D\n"
                "Correct option number (0-3)"
            )
    
    elif 'waiting_for_answer_edit' in context.user_data and context.user_data['waiting_for_answer_edit']:
        # Process input for editing an answer
        text = update.message.text
        
        try:
            # Parse the input (question number, correct option)
            parts = text.strip().split()
            question_num = int(parts[0]) - 1  # Convert to 0-based index
            correct_option = int(parts[1])
            
            # Update the correct option
            quiz = context.user_data['poll_quiz']
            quiz.questions[question_num].correct_option = correct_option
            
            # Send confirmation
            update.message.reply_text(
                f"Answer updated for question {question_num + 1}.\n\n"
                f"What would you like to do next?\n"
                f"1. Add more questions with /addquestion\n"
                f"2. Edit more answers with /editanswer\n"
                f"3. Finalize the quiz with /finalize"
            )
            
            # Reset the waiting state
            context.user_data['waiting_for_answer_edit'] = False
            
        except Exception as e:
            update.message.reply_text(
                "Invalid format. Please use the format: 'question_number correct_option'\n"
                "Example: '1 2' to set question 1's correct answer to option 2"
            )

def start_marathon(update: Update, context: CallbackContext) -> None:
    """Start a new quiz marathon."""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can use this command.")
        return
    
    # Check if there's already an active marathon
    if 'marathon_quiz' in context.user_data:
        update.message.reply_text(
            "A quiz marathon is already in progress. You can:\n"
            "- Add more questions by forwarding polls\n"
            "- Finalize the quiz with /finalize_marathon\n"
            "- Cancel the current marathon with /cancel_marathon"
        )
        return
    
    # Get title and description from the command
    args = update.message.text.split(' ', 1)
    title = f"Marathon Quiz {datetime.now().strftime('%Y-%m-%d')}"
    description = "A quiz created from multiple polls"
    
    if len(args) > 1:
        title_desc = args[1].split('|', 1)
        title = title_desc[0].strip()
        if len(title_desc) > 1:
            description = title_desc[1].strip()
    
    # Create a new quiz
    import uuid
    from models.quiz import Quiz
    
    quiz = Quiz(
        title=title,
        description=description,
        creator_id=user_id,
        time_limit=15,  # Default time limit
        negative_marking_factor=0  # Default no negative marking
    )
    
    # Set the ID
    quiz.id = str(uuid.uuid4())
    
    # Store the quiz in user context
    context.user_data['marathon_quiz'] = quiz
    
    update.message.reply_text(
        f"🏁 Marathon quiz started!\n\n"
        f"Title: {title}\n"
        f"Description: {description}\n\n"
        f"Forward polls to add questions.\n"
        f"When you're done, use /finalize_marathon to save the quiz."
    )

def finalize_marathon(update: Update, context: CallbackContext) -> None:
    """Finalize and save the marathon quiz."""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can use this command.")
        return
    
    # Check if there's an active marathon
    if 'marathon_quiz' not in context.user_data:
        update.message.reply_text("No active marathon quiz. Start one with /start_marathon")
        return
    
    quiz = context.user_data['marathon_quiz']
    
    # Make sure there are questions
    if not quiz.questions:
        update.message.reply_text("The quiz has no questions. Please forward polls to add questions.")
        return
    
    # Save the quiz
    from utils.database import add_quiz
    saved_id = add_quiz(quiz)
    
    # Send confirmation
    update.message.reply_text(
        f"✅ Marathon quiz finalized and saved!\n\n"
        f"Title: {quiz.title}\n"
        f"Description: {quiz.description}\n"
        f"Total questions: {len(quiz.questions)}\n\n"
        f"Users can take this quiz with:\n/take {saved_id}"
    )
    
    # Clear the marathon quiz
    del context.user_data['marathon_quiz']

def cancel_marathon(update: Update, context: CallbackContext) -> None:
    """Cancel the current marathon quiz."""
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can use this command.")
        return
    
    # Check if there's an active marathon
    if 'marathon_quiz' not in context.user_data:
        update.message.reply_text("No active marathon quiz to cancel.")
        return
    
    # Get the quiz info for feedback
    quiz = context.user_data['marathon_quiz']
    question_count = len(quiz.questions)
    
    # Clear the marathon quiz
    del context.user_data['marathon_quiz']
    
    update.message.reply_text(
        f"❌ Marathon quiz canceled.\n"
        f"The quiz with {question_count} questions has been discarded."
    )

def convert_poll_to_quiz(update: Update, context: CallbackContext) -> None:
    """Convert a poll to a quiz or add it to a marathon quiz."""
    try:
        user_id = update.effective_user.id
        
        # Check if user is admin
        if user_id not in ADMIN_USERS:
            return
        
        # Check if the message contains a poll
        if update.message and update.message.poll:
            poll = update.message.poll
            
            # Check if there's an active marathon
            if 'marathon_quiz' in context.user_data:
                # Add the question to the marathon quiz
                quiz = context.user_data['marathon_quiz']
                
                # Create a question from the poll
                from models.quiz import Question
                options = [option.text for option in poll.options]
                if len(options) < 2:
                    update.message.reply_text("Poll must have at least 2 options.")
                    return
                
                question = Question(
                    text=poll.question,
                    options=options,
                    correct_option=0  # Default first option is correct
                )
                
                # Add the question to the quiz
                quiz.questions.append(question)
                
                # Send confirmation
                update.message.reply_text(
                    f"➕ Question added to marathon quiz.\n\n"
                    f"Question: {poll.question[:50]}...\n"
                    f"Options: {len(options)}\n\n"
                    f"Total questions: {len(quiz.questions)}\n"
                    f"⚠️ Note: The first option is set as correct by default.\n\n"
                    f"You can:\n"
                    f"- Forward more polls to add more questions\n"
                    f"- Use /finalize_marathon to save the quiz\n"
                    f"- Use /edit_answer to change correct options"
                )
                
            else:
                # Create a standalone quiz as before
                try:
                    # Get poll options
                    options = [option.text for option in poll.options]
                    if len(options) < 2:
                        update.message.reply_text("Poll must have at least 2 options.")
                        return
                    
                    # Create a quiz from the poll
                    import uuid
                    from models.quiz import Quiz, Question
                    
                    # Generate a quiz ID
                    quiz_id = str(uuid.uuid4())
                    update.message.reply_text(f"Creating quiz with ID: {quiz_id[:8]}...")
                    
                    # Create quiz title and description
                    title = f"Poll Quiz {quiz_id[-8:]}"
                    description = f"Created from poll: {poll.question[:30]}..."
                    
                    # Create the quiz object - WITHOUT id parameter
                    quiz = Quiz(
                        title=title,
                        description=description,
                        creator_id=user_id,
                        time_limit=15,  # Default time limit
                        negative_marking_factor=0  # Default no negative marking
                    )
                    
                    # Set the ID after creation
                    quiz.id = quiz_id
                    
                    # Add the question from the poll
                    update.message.reply_text("Adding question to quiz...")
                    
                    question = Question(
                        text=poll.question,
                        options=options,
                        correct_option=0  # Default first option is correct
                    )
                    
                    quiz.questions.append(question)
                    
                    # Save to database using add_quiz
                    update.message.reply_text("Saving quiz to database...")
                    from utils.database import add_quiz
                    saved_id = add_quiz(quiz)
                    
                    # Send confirmation
                    update.message.reply_text(
                        f"✅ Quiz created successfully!\n\n"
                        f"Title: {title}\n"
                        f"Description: {description}\n\n"
                        f"The quiz has 1 question with {len(options)} options.\n"
                        f"⚠️ Note: The first option is set as correct by default.\n\n"
                        f"Users can take this quiz with:\n/take {saved_id}\n\n"
                        f"Tip: Use /start_marathon to create a quiz with multiple questions."
                    )
                    
                except Exception as e:
                    import traceback
                    logger.error(f"Error creating quiz: {str(e)}")
                    logger.error(traceback.format_exc())
                    update.message.reply_text(f"Error creating quiz: {str(e)}")
        else:
            update.message.reply_text("No poll found in this message. Please forward a message containing a poll.")
                
    except Exception as e:
        import traceback
        logger.error(f"Error in convert_poll_to_quiz: {str(e)}")
        logger.error(traceback.format_exc())
        if update and update.message:
            update.message.reply_text(f"Error processing poll: {str(e)}")

def start_marathon(update: Update, context: CallbackContext) -> None:
    """Start a new quiz marathon."""
    try:
        user_id = update.effective_user.id
        
        # Check if user is admin
        if user_id not in ADMIN_USERS:
            update.message.reply_text("Sorry, only admins can use this command.")
            return
        
        # Check if there's already an active marathon
        if 'marathon_quiz' in context.user_data:
            update.message.reply_text(
                "A quiz marathon is already in progress. You can:\n"
                "- Add more questions by forwarding polls\n"
                "- Finalize the quiz with /finalize_marathon\n"
                "- Cancel the current marathon with /cancel_marathon"
            )
            return
        
        # Get title and description from the command
        args = update.message.text.split(' ', 1)
        title = f"Marathon Quiz {datetime.now().strftime('%Y-%m-%d')}"
        description = "A quiz created from multiple polls"
        
        if len(args) > 1:
            title_desc = args[1].split('|', 1)
            title = title_desc[0].strip()
            if len(title_desc) > 1:
                description = title_desc[1].strip()
        
        # Create a new quiz
        import uuid
        from models.quiz import Quiz
        
        quiz = Quiz(
            title=title,
            description=description,
            creator_id=user_id,
            time_limit=15,  # Default time limit
            negative_marking_factor=0  # Default no negative marking
        )
        
        # Set the ID
        quiz.id = str(uuid.uuid4())
        
        # Store the quiz in user context
        context.user_data['marathon_quiz'] = quiz
        
        update.message.reply_text(
            f"🏁 Marathon quiz started!\n\n"
            f"Title: {title}\n"
            f"Description: {description}\n\n"
            f"Forward polls to add questions.\n"
            f"When you're done, use /finalize_marathon to save the quiz."
        )
    except Exception as e:
        import traceback
        logger.error(f"Error in start_marathon: {str(e)}")
        logger.error(traceback.format_exc())
        if update and update.message:
            update.message.reply_text(f"Error starting marathon: {str(e)}")

def finalize_marathon(update: Update, context: CallbackContext) -> None:
    """Finalize and save the marathon quiz."""
    try:
        user_id = update.effective_user.id
        
        # Check if user is admin
        if user_id not in ADMIN_USERS:
            update.message.reply_text("Sorry, only admins can use this command.")
            return
        
        # Check if there's an active marathon
        if 'marathon_quiz' not in context.user_data:
            update.message.reply_text("No active marathon quiz. Start one with /start_marathon")
            return
        
        quiz = context.user_data['marathon_quiz']
        
        # Make sure there are questions
        if not quiz.questions:
            update.message.reply_text("The quiz has no questions. Please forward polls to add questions.")
            return
        
        # Save the quiz
        from utils.database import add_quiz
        saved_id = add_quiz(quiz)
        
        # Send confirmation
        update.message.reply_text(
            f"✅ Marathon quiz finalized and saved!\n\n"
            f"Title: {quiz.title}\n"
            f"Description: {quiz.description}\n"
            f"Total questions: {len(quiz.questions)}\n\n"
            f"Users can take this quiz with:\n/take {saved_id}"
        )
        
        # Clear the marathon quiz
        del context.user_data['marathon_quiz']
    except Exception as e:
        import traceback
        logger.error(f"Error in finalize_marathon: {str(e)}")
        logger.error(traceback.format_exc())
        if update and update.message:
            update.message.reply_text(f"Error finalizing marathon: {str(e)}")

def cancel_marathon(update: Update, context: CallbackContext) -> None:
    """Cancel the current marathon quiz."""
    try:
        user_id = update.effective_user.id
        
        # Check if user is admin
        if user_id not in ADMIN_USERS:
            update.message.reply_text("Sorry, only admins can use this command.")
            return
        
        # Check if there's an active marathon
        if 'marathon_quiz' not in context.user_data:
            update.message.reply_text("No active marathon quiz to cancel.")
            return
        
        # Get the quiz info for feedback
        quiz = context.user_data['marathon_quiz']
        question_count = len(quiz.questions)
        
        # Clear the marathon quiz
        del context.user_data['marathon_quiz']
        
        update.message.reply_text(
            f"❌ Marathon quiz canceled.\n"
            f"The quiz with {question_count} questions has been discarded."
        )
    except Exception as e:
        import traceback
        logger.error(f"Error in cancel_marathon: {str(e)}")
        logger.error(traceback.format_exc())
        if update and update.message:
            update.message.reply_text(f"Error canceling marathon: {str(e)}")

def set_question_correct_answer(update: Update, context: CallbackContext) -> None:
    """Set the correct answer for the last added question in marathon mode."""
    try:
        user_id = update.effective_user.id
        
        # Check if user is admin
        if user_id not in ADMIN_USERS:
            update.message.reply_text("Sorry, only admins can use this command.")
            return
        
        # Check arguments
        if not context.args:
            update.message.reply_text(
                "Please provide the option number: /correct <option_number>\n"
                "For example, /correct 2 will set the second option as correct."
            )
            return
        
        # Parse option number
        try:
            option_num = int(context.args[0])
        except ValueError:
            update.message.reply_text("Please provide a valid number.")
            return
        
        # Check if in marathon mode
        if 'marathon_quiz' not in context.user_data:
            update.message.reply_text(
                "No active marathon quiz. Start one with /start_marathon first."
            )
            return
        
        quiz = context.user_data['marathon_quiz']
        
        # Check if there are any questions
        if not quiz.questions:
            update.message.reply_text("The marathon quiz has no questions yet. Forward a poll first.")
            return
        
        # Get the last question
        last_question = quiz.questions[-1]
        
        # Adjust option number to 0-based index
        correct_option = option_num - 1
        
        # Validate option number
        if correct_option < 0 or correct_option >= len(last_question.options):
            update.message.reply_text(
                f"Invalid option number. Please choose between 1 and {len(last_question.options)}."
            )
            return
        
        # Set the correct option
        old_correct = last_question.correct_option + 1  # Convert to 1-based for display
        last_question.correct_option = correct_option
        
        # Confirm the change
        update.message.reply_text(
            f"✅ Correct answer updated for the last question:\n\n"
            f"Question: {last_question.text[:50]}...\n"
            f"Changed correct answer from option {old_correct} to option {option_num}."
        )
        
    except Exception as e:
        import traceback
        logger.error(f"Error in set_question_correct_answer: {str(e)}")
        logger.error(traceback.format_exc())
        update.message.reply_text(f"Error setting correct answer: {str(e)}")

def import_questions_from_pdf(update: Update, context: CallbackContext) -> None:
    """Import questions from a PDF file."""
    try:
        user_id = update.effective_user.id
        
        # Check if user is admin
        if user_id not in ADMIN_USERS:
            update.message.reply_text("Sorry, only admins can use this command.")
            return
        
        # Check if PDF was uploaded
        if update.message and update.message.document:
            document = update.message.document
            
            # Check if it's a PDF
            if not document.mime_type.endswith('pdf'):
                update.message.reply_text("Please upload a PDF file.")
                return
            
            # Download the PDF
            file_id = document.file_id
            update.message.reply_text("Downloading PDF file...")
            
            file = context.bot.get_file(file_id)
            pdf_path = f"/tmp/{file_id}.pdf"
            file.download(pdf_path)
            
            update.message.reply_text("Processing PDF file. This may take a moment...")
            
            # Extract text from PDF
            try:
                import fitz  # PyMuPDF
                
                doc = fitz.open(pdf_path)
                text = ""
                
                for page in doc:
                    text += page.get_text()
                
                # Close and remove the file
                doc.close()
                import os
                os.remove(pdf_path)
                
                # Parse questions from text
                questions = parse_questions_from_text(text)
                
                if not questions:
                    update.message.reply_text(
                        "No questions found in the PDF. Make sure the PDF contains questions in the expected format:\n\n"
                        "Question: What is the capital of France?\n"
                        "A) Paris\n"
                        "B) London\n"
                        "C) Berlin\n"
                        "D) Madrid\n"
                        "Correct: A\n\n"
                        "or similar formatting."
                    )
                    return
                
                # Ask if user wants to create a new quiz or add to marathon
                if 'marathon_quiz' in context.user_data:
                    keyboard = [
                        [InlineKeyboardButton("Add to marathon", callback_data=f"pdf_marathon_{file_id}")],
                        [InlineKeyboardButton("Create new quiz", callback_data=f"pdf_new_{file_id}")]
                    ]
                else:
                    keyboard = [
                        [InlineKeyboardButton("Create new quiz", callback_data=f"pdf_new_{file_id}")]
                    ]
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Store questions in context for later
                context.user_data[f'pdf_questions_{file_id}'] = questions
                
                update.message.reply_text(
                    f"Found {len(questions)} questions in the PDF.\n\n"
                    f"What would you like to do?",
                    reply_markup=reply_markup
                )
                
            except Exception as e:
                import traceback
                logger.error(f"Error processing PDF: {str(e)}")
                logger.error(traceback.format_exc())
                update.message.reply_text(f"Error processing PDF: {str(e)}")
        else:
            update.message.reply_text(
                "Please upload a PDF file containing questions.\n\n"
                "The PDF should contain questions in a format like:\n\n"
                "Question: What is the capital of France?\n"
                "A) Paris\n"
                "B) London\n"
                "C) Berlin\n"
                "D) Madrid\n"
                "Correct: A\n\n"
                "or similar formatting."
            )
            
    except Exception as e:
        import traceback
        logger.error(f"Error in import_questions_from_pdf: {str(e)}")
        logger.error(traceback.format_exc())
        update.message.reply_text(f"Error importing questions: {str(e)}")

def handle_pdf_import_callback(update: Update, context: CallbackContext) -> None:
    """Handle callbacks for PDF question import."""
    try:
        query = update.callback_query
        query.answer()
        
        user_id = query.from_user.id
        
        # Check if user is admin
        if user_id not in ADMIN_USERS:
            query.edit_message_text("Sorry, only admins can use this feature.")
            return
        
        # Parse callback data
        data = query.data.split('_')
        action = data[1]  # 'marathon' or 'new'
        file_id = data[2]  # file ID for retrieving questions
        
        # Get questions from context
        questions_key = f'pdf_questions_{file_id}'
        if questions_key not in context.user_data:
            query.edit_message_text("Questions not found. Please upload the PDF again.")
            return
        
        questions = context.user_data[questions_key]
        
        if action == 'marathon':
            # Add to marathon
            if 'marathon_quiz' not in context.user_data:
                query.edit_message_text("Marathon quiz not found. Start one with /start_marathon first.")
                return
            
            quiz = context.user_data['marathon_quiz']
            
            # Add questions to marathon
            for q in questions:
                quiz.questions.append(q)
            
            query.edit_message_text(
                f"✅ Added {len(questions)} questions to marathon quiz.\n\n"
                f"Marathon quiz now has {len(quiz.questions)} questions in total."
            )
            
        elif action == 'new':
            # Create a new quiz
            import uuid
            from models.quiz import Quiz
            
            # Generate a quiz ID
            quiz_id = str(uuid.uuid4())
            
            # Create quiz title and description
            title = f"PDF Quiz {quiz_id[-8:]}"
            description = f"Created from PDF with {len(questions)} questions"
            
            # Create the quiz object
            quiz = Quiz(
                title=title,
                description=description,
                creator_id=user_id,
                time_limit=15,  # Default time limit
                negative_marking_factor=0  # Default no negative marking
            )
            
            # Set the ID
            quiz.id = quiz_id
            
            # Add questions
            for q in questions:
                quiz.questions.append(q)
            
            # Save to database
            from utils.database import add_quiz
            saved_id = add_quiz(quiz)
            
            query.edit_message_text(
                f"✅ Created new quiz with {len(questions)} questions!\n\n"
                f"Title: {title}\n"
                f"Description: {description}\n\n"
                f"Users can take this quiz with:\n/take {saved_id}"
            )
        
        # Clean up
        del context.user_data[questions_key]
        
    except Exception as e:
        import traceback
        logger.error(f"Error in handle_pdf_import_callback: {str(e)}")
        logger.error(traceback.format_exc())
        if query:
            query.edit_message_text(f"Error processing PDF questions: {str(e)}")

def parse_questions_from_text(text):
    """Parse questions, options, and correct answers from text."""
    from models.quiz import Question
    import re
    
    # Normalize line endings
    text = text.replace('\r\n', '\n')
    
    # Define patterns for different question formats
    patterns = [
        # Format: "Question: text\nA) option1\nB) option2\nC) option3\nD) option4\nCorrect: A"
        r'(?:Question:|Q:|Q\.|^\d+[\.\)]) (.*?)\s*\n(?:[Aa]\)|[Aa]\.) (.*?)\s*\n(?:[Bb]\)|[Bb]\.) (.*?)\s*\n(?:[Cc]\)|[Cc]\.) (.*?)\s*\n(?:[Dd]\)|[Dd]\.) (.*?)\s*\n(?:Correct:?|Answer:?|Ans:?)\s*([ABCDabcd])',
        
        # Format: "Question: text\n1. option1\n2. option2\n3. option3\n4. option4\nCorrect: 1"
        r'(?:Question:|Q:|Q\.|^\d+[\.\)]) (.*?)\s*\n(?:1[\.\)]) (.*?)\s*\n(?:2[\.\)]) (.*?)\s*\n(?:3[\.\)]) (.*?)\s*\n(?:4[\.\)]) (.*?)\s*\n(?:Correct:?|Answer:?|Ans:?)\s*([1234])',
        
        # Format: "Question: text\noption1 (*)\noption2\noption3\noption4"
        r'(?:Question:|Q:|Q\.|^\d+[\.\)]) (.*?)\s*\n(.*?)(?:\s*\(\*\)|\s*\*)\s*\n(.*?)\s*\n(.*?)\s*\n(.*?)\s*(?:\n|$)'
    ]
    
    questions = []
    
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.MULTILINE | re.DOTALL)
        
        for match in matches:
            if len(match.groups()) >= 5:
                question_text = match.group(1).strip()
                options = [
                    match.group(2).strip(),
                    match.group(3).strip(),
                    match.group(4).strip(),
                    match.group(5).strip()
                ]
                
                # Determine correct option
                correct_option = 0  # Default to first option
                if len(match.groups()) >= 6 and match.group(6):
                    answer_mark = match.group(6).upper()
                    if answer_mark in 'ABCD':
                        correct_option = 'ABCD'.index(answer_mark)
                    elif answer_mark in '1234':
                        correct_option = int(answer_mark) - 1
                
                # Create Question object
                question = Question(
                    text=question_text,
                    options=options,
                    correct_option=correct_option
                )
                
                questions.append(question)
    
    return questions

def import_questions_from_pdf(update, context):
    """
    Handler function for importing questions from a PDF document
    """
    # Check if user is admin
    user_id = update.effective_user.id
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can import questions from PDFs.")
        return
    
    # Check if a document was provided
    if not update.message.document or update.message.document.mime_type != 'application/pdf':
        update.message.reply_text("Please forward a PDF file.")
        return
    
    # Get the document file
    document = update.message.document
    file_id = document.file_id
    
    update.message.reply_text("Downloading PDF file...")
    
    # Download the file
    file = context.bot.get_file(file_id)
    file_bytes = io.BytesIO()
    file.download(out=file_bytes)
    file_bytes.seek(0)
    
    update.message.reply_text("Processing PDF file. This may take a moment...")
    
    # Extract text from PDF
    try:
        pdf_text = extract_text_from_pdf(file_bytes)
        
        # Parse questions from the text
        questions = parse_questions_from_pdf_text(pdf_text)
        
        if not questions:
            update.message.reply_text("No questions could be extracted from the PDF. "
                                      "Make sure the format is correct.")
            return
        
        # Store questions temporarily in user data
        context.user_data['pdf_questions'] = questions
        
        # Create a confirmation message with question preview
        preview_text = "Extracted the following questions:\n\n"
        for i, question in enumerate(questions[:3], 1):  # Preview first 3 questions
            preview_text += f"{i}. {question['question']}\n"
            for j, option in enumerate(question['options'], 1):
                preview_text += f"   {j}. {option}\n"
            preview_text += f"   Correct: Option {question['correct_answer']}\n\n"
        
        if len(questions) > 3:
            preview_text += f"... and {len(questions) - 3} more questions\n\n"
        
        # Ask user to confirm import and provide a quiz name
        keyboard = [
            [InlineKeyboardButton("Create New Quiz", callback_data="pdf_create")],
            [InlineKeyboardButton("Add to Marathon Quiz", callback_data="pdf_marathon")],
            [InlineKeyboardButton("Cancel", callback_data="pdf_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            f"{preview_text}What would you like to do with these questions?",
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        update.message.reply_text(f"Error processing PDF: {str(e)}")

def extract_text_from_pdf(file_bytes):
    """
    Basic text extraction from PDF as binary
    This is a fallback method when PDF parsing libraries are not available
    """
    text = ""
    try:
        # Try to get text directly from binary data
        binary_content = file_bytes.getvalue()
        
        # Log the size for debugging
        logger.info(f"PDF binary size: {len(binary_content)} bytes")
        
        # Decode the binary data to text with error handling
        decoded_text = binary_content.decode('utf-8', errors='ignore')
        
        # Basic cleanup - remove non-printable characters while preserving Unicode
        cleaned_text = ''.join(c if c.isprintable() or c in '\n\r\t' else ' ' for c in decoded_text)
        
        # Extract lines that might be questions
        lines = []
        for line in cleaned_text.split('\n'):
            line = line.strip()
            # Accept shorter lines that might be in Hindi
            if len(line) > 3 and not line.startswith('%') and not line.startswith('/'):
                lines.append(line)
        
        text = '\n'.join(lines)
        logger.info(f"Extracted {len(lines)} text lines from PDF")
        
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        raise
    
    return text

def parse_questions_from_pdf_text(text):
    """
    Parse questions from the extracted PDF text
    
    Supports multiple formats including:
    - Standard format with "Correct:" label
    - Format with checkmark (✓) to indicate correct answer
    - Hindi and other non-English text support
    """
    questions = []
    lines = text.split('\n')
    
    # Print the extracted text for debugging
    logger.info(f"Extracted text lines: {len(lines)}")
    if len(lines) > 0:
        logger.info(f"First 10 lines preview: {lines[:10]}")
    
    current_question = None
    current_options = []
    correct_answer = None
    
    # Patterns for different formats
    question_pattern = re.compile(r'^(?:Q)?(\d+)[.)]\s+(.*)')
    option_pattern1 = re.compile(r'^(?:\()?([A-D])(?:\))?[.)]\s+(.*)')
    option_pattern2 = re.compile(r'^(?:\()?([a-d])(?:\))?[.)]\s+(.*)')
    correct_pattern = re.compile(r'^[Cc]orrect:?\s*([A-Da-d])')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Check for question
        question_match = question_pattern.match(line)
        if question_match:
            # Save previous question if exists
            if current_question and current_options:
                if correct_answer:
                    if correct_answer.upper() in "ABCD":
                        correct_idx = ord(correct_answer.upper()) - ord('A') + 1
                    else:
                        correct_idx = int(correct_answer)
                else:
                    correct_idx = 1  # Default to first option
                
                questions.append({
                    'question': current_question,
                    'options': current_options,
                    'correct_answer': correct_idx
                })
            
            # Start new question
            current_question = question_match.group(2)
            current_options = []
            correct_answer = None
            
        # Check for options with checkmark for correct answer
        checkmark_match = False
        if "✓" in line or "√" in line or "✔" in line:
            # This option has a checkmark, indicating it's correct
            checkmark_match = True
            # Try to extract the option letter
            option_match = option_pattern1.match(line.replace("✓", "").replace("√", "").replace("✔", "").strip())
            if option_match:
                correct_answer = option_match.group(1)
        
        # Check for standard options
        option_match = option_pattern1.match(line) or option_pattern2.match(line)
        if option_match:
            option_letter = option_match.group(1)
            option_text = option_match.group(2)
            current_options.append(option_text)
            
            # If this option has checkmark in the same line or next line
            if checkmark_match or (i+1 < len(lines) and ("✓" in lines[i+1] or "√" in lines[i+1] or "✔" in lines[i+1])):
                correct_answer = option_letter
        
        # Check for correct answer standard format
        correct_match = correct_pattern.match(line)
        if correct_match:
            correct_answer = correct_match.group(1)
        
        i += 1
    
    # Add the last question
    if current_question and current_options:
        if correct_answer:
            if correct_answer.upper() in "ABCD":
                correct_idx = ord(correct_answer.upper()) - ord('A') + 1
            else:
                correct_idx = int(correct_answer)
        else:
            correct_idx = 1  # Default to first option
        
        questions.append({
            'question': current_question,
            'options': current_options,
            'correct_answer': correct_idx
        })
    
    logger.info(f"Extracted {len(questions)} questions from PDF")
    return questions

def handle_pdf_import_callback(update, context):
    """
    Handle callback queries from PDF import buttons
    """
    query = update.callback_query
    query.answer()
    
    action = query.data.split('_')[1]
    
    if 'pdf_questions' not in context.user_data:
        query.edit_message_text("Session expired. Please upload your PDF again.")
        return
    
    questions = context.user_data['pdf_questions']
    
    if action == 'cancel':
        query.edit_message_text("PDF import cancelled.")
        return
    
    if action == 'create':
        # Ask for quiz name
        keyboard = []
        for i in range(1, 6):
            keyboard.append([InlineKeyboardButton(f"Quiz {i}", callback_data=f"pdf_name_Quiz {i}")])
        
        keyboard.append([InlineKeyboardButton("Custom Name", callback_data="pdf_custom_name")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        query.edit_message_text("Please select a name for your quiz or choose 'Custom Name':", 
                              reply_markup=reply_markup)
        return
    
    if action == 'marathon':
        # Check if there's an ongoing marathon
        if 'marathon_quiz' not in context.user_data:
            query.edit_message_text("No marathon quiz in progress. Please start a marathon first with /start_marathon")
            return
        
        # Add all questions to the marathon
        marathon_quiz = context.user_data['marathon_quiz']
        for q_data in questions:
            question = Question(
                q_data['question'],
                q_data['options'],
                q_data['correct_answer'] - 1  # Convert to 0-based index
            )
            marathon_quiz.add_question(question)
        
        query.edit_message_text(f"Added {len(questions)} questions to your marathon quiz. "
                              f"Current question count: {len(marathon_quiz.questions)}")
        return
    
    if action.startswith('name_'):
        # Create a new quiz with the selected name
        quiz_name = action.split('name_')[1]
        create_quiz_from_pdf(context, quiz_name, questions)
        query.edit_message_text(f"Quiz '{quiz_name}' created with {len(questions)} questions!")
        return
    
    if action == 'custom_name':
        # This requires the user to send a text message with the name
        # We'll need to handle this in a conversation
        context.user_data['waiting_for_pdf_quiz_name'] = True
        query.edit_message_text("Please reply with a name for your quiz:")
        return

def create_quiz_from_pdf(context, quiz_name, questions_data):
    """
    Create a new quiz from PDF-extracted questions
    """
    new_quiz = Quiz(quiz_name)
    
    # Add questions
    for q_data in questions_data:
        question = Question(
            q_data['question'],
            q_data['options'],
            q_data['correct_answer'] - 1  # Convert to 0-based index
        )
        new_quiz.add_question(question)
    
    # Set default time (30 seconds per question)
    new_quiz.time = len(new_quiz.questions) * 30
    
    # Save to database
    add_quiz(new_quiz)
    
    return new_quiz
        
        
                    
