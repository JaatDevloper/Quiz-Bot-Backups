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
        
        
                    
