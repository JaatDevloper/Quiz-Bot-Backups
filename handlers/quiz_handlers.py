#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Handlers for user-facing quiz functionality
"""

import json
import logging
import time
import os
from datetime import datetime
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from models.user import User
from utils.database import (
    get_quiz, get_quizzes, get_user, record_quiz_result,
    get_user_quiz_results
)
from utils.quiz_manager import QuizSession, import_quiz_from_file
from utils.pdf_generator import generate_result_pdf
from config import ADMIN_USERS

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Store active sessions by user_id
active_sessions = {}

def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message when the command /start is issued."""
    try:
        user = update.effective_user
        
        # Create a simpler welcome message with basic formatting
        welcome_message = (
            "🎓 Welcome to Telegram Quiz Bot! 🎓\n\n"
            f"Hello {user.first_name}! I'm your interactive quiz companion.\n\n"
            "🚀 Key Features:\n"
            "• 📋 Multiple choice quizzes\n"
            "• ⏱️ Custom time limits per question\n"
            "• 📊 Negative marking for wrong answers\n"
            "• 📑 PDF generation of results\n"
            "• 📤 Import/Export quizzes\n\n"
            "📝 Commands:\n"
            "• /start - Show this welcome message\n"
            "• /help - Get help information\n"
            "• /list - List available quizzes\n"
            "• /take [quiz_id] - Start a quiz\n"
            "• /cancel - Cancel operation\n"
            "• /results - Get quiz results as PDF\n\n"
            "👨‍💻 Created by: @JaatCoderX\n\n"
            "Use /list to see available quizzes!"
        )
        
        # Use plain text for compatibility
        update.message.reply_text(welcome_message)
    except Exception as e:
        import logging
        logging.error(f"Error in start command: {str(e)}")
        update.message.reply_text("Welcome to the Quiz Bot! Use /help to see available commands.")

def help_command(update: Update, context: CallbackContext) -> None:
    """Send a help message when the command /help is issued."""
    commands = [
        "/start - Start the bot",
        "/help - Show this help message",
        "/list - List all available quizzes",
        "/take (quiz_id) - Take a specific quiz",
        "/results - Get your quiz results",
        "/admin - Show admin commands (admin only)",
    ]
    
    update.message.reply_text(
        'Here are the available commands:\n\n' + '\n'.join(commands)
    )

def list_quizzes(update: Update, context: CallbackContext) -> None:
    """List all available quizzes."""
    quizzes = get_quizzes()
    
    if not quizzes:
        update.message.reply_text("There are no quizzes available yet.")
        return
    
    # Create a list of quiz info
    quiz_list = []
    for quiz_id, quiz in quizzes.items():
        quiz_list.append(f"ID: {quiz_id} - {quiz.title}")
        quiz_list.append(f"Description: {quiz.description}")
        quiz_list.append(f"Questions: {len(quiz.questions)}")
        quiz_list.append(f"Time limit: {quiz.time_limit}s per question")
        quiz_list.append("")
    
    # Send the list
    update.message.reply_text(
        'Available Quizzes:\n\n' + '\n'.join(quiz_list) +
        '\nUse /take (quiz_id) to take a quiz.'
    )

def take_quiz(update: Update, context: CallbackContext) -> str:
    """Start a quiz for a user."""
    user_id = update.effective_user.id
    
    # Check if the user is already in a quiz
    if user_id in active_sessions:
        update.message.reply_text(
            "You are already taking a quiz. Please finish it or use /cancel to cancel it."
        )
        return "ANSWERING"
    
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
    
    # Create a new session
    session = QuizSession(user_id, quiz)
    active_sessions[user_id] = session
    
    # Start the quiz
    update.message.reply_text(
        f"Starting quiz: {quiz.title}\n\n"
        f"Description: {quiz.description}\n"
        f"Number of questions: {len(quiz.questions)}\n"
        f"Time limit per question: {quiz.time_limit} seconds\n"
        f"Negative marking: {quiz.negative_marking_factor} points\n\n"
        "Use /cancel to cancel the quiz."
    )
    
    # Send the first question
    send_quiz_question(update, context, session)
    
    return "ANSWERING"

def send_quiz_question(update: Update, context: CallbackContext, session: QuizSession) -> None:
    """Send the current question to the user."""
    question = session.get_current_question()
    
    if not question:
        # No more questions, end the quiz
        end_quiz(update, context, session)
        return
    
    # Get the question-specific time limit or use quiz default
    time_limit = question.time_limit if question.time_limit is not None else session.quiz.time_limit
    
    # Create options buttons
    keyboard = []
    for i, option in enumerate(question.options):
        # Use A, B, C, D for options
        option_letter = chr(65 + i)  # A=0, B=1, etc.
        button = InlineKeyboardButton(
            f"{option_letter}. {option}", 
            callback_data=f"answer_{i}"
        )
        keyboard.append([button])
    
    # Add a message indicating the current question number
    question_number = session.current_question_index + 1
    total_questions = len(session.quiz.questions)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Get chat id (could be from a message or callback query)
    if update.message:
        chat_id = update.message.chat_id
        message = update.message.reply_text(
            f"Question {question_number} of {total_questions}:\n\n"
            f"{question.text}\n\n"
            f"Time limit: {time_limit} seconds",
            reply_markup=reply_markup
        )
        message_id = message.message_id
    else:
        chat_id = update.callback_query.message.chat_id
        update.callback_query.edit_message_text(
            f"Question {question_number} of {total_questions}:\n\n"
            f"{question.text}\n\n"
            f"Time limit: {time_limit} seconds",
            reply_markup=reply_markup
        )
        message_id = update.callback_query.message.message_id
    
    # Set up timer for this question
    if time_limit > 0:
        context.job_queue.run_once(
            time_up,
            time_limit,
            context={
                'chat_id': chat_id,
                'message_id': message_id,
                'user_id': session.user_id,
                'question_index': session.current_question_index
            }
        )

def answer_callback(update: Update, context: CallbackContext) -> str:
    """Process user's answer to a quiz question."""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Check if the user is in an active quiz session
    if user_id not in active_sessions:
        query.answer("You are not currently taking a quiz.")
        query.edit_message_text("This quiz has expired. Use /take to start a new quiz.")
        return
    
    session = active_sessions[user_id]
    
    # Remove any pending time_up jobs for this question
    current_jobs = context.job_queue.get_jobs_by_name(f"time_up_{user_id}_{session.current_question_index}")
    for job in current_jobs:
        job.schedule_removal()
    
    # Extract the selected option from callback data
    selected_option = int(query.data.split('_')[1])
    
    # Get the current question
    question = session.get_current_question()
    if not question:
        query.answer("This question is no longer active.")
        return "ANSWERING"
    
    # Check if the answer is correct
    is_correct = selected_option == question.correct_option
    
    # Record the answer
    session.record_answer(selected_option, is_correct)
    
    # Show feedback
    if is_correct:
        query.answer("Correct!")
        feedback = "✅ Correct!"
    else:
        query.answer("Incorrect!")
        feedback = f"❌ Incorrect! The correct answer was: {chr(65 + question.correct_option)}. {question.options[question.correct_option]}"
    
    # Update the message to show the correct answer
    query.edit_message_text(
        f"{query.message.text}\n\n{feedback}"
    )
    
    # Move to the next question
    session.move_to_next_question()
    
    # Check if there are more questions
    if session.get_current_question():
        # Send the next question after a short delay
        context.job_queue.run_once(
            lambda _: send_quiz_question(update, context, session),
            2,  # 2 seconds delay
            context=None
        )
    else:
        # End the quiz after a short delay
        context.job_queue.run_once(
            lambda _: end_quiz(update, context, session),
            2,  # 2 seconds delay
            context=None
        )
    
    return "ANSWERING"

def time_up(context: CallbackContext) -> None:
    """Handle when time is up for a question."""
    job = context.job
    job_context = job.context
    
    chat_id = job_context['chat_id']
    message_id = job_context['message_id']
    user_id = job_context['user_id']
    question_index = job_context['question_index']
    
    # Check if the user is still in an active session
    if user_id not in active_sessions:
        return
    
    session = active_sessions[user_id]
    
    # Check if the user has already moved to another question
    if session.current_question_index != question_index:
        return
    
    # Create a fake update to handle the time up event
    class FakeUpdate:
        def __init__(self, message, effective_user):
            self.callback_query = message
            self.effective_user = effective_user
            self.message = None
    
    class FakeUser:
        def __init__(self, user_id):
            self.id = user_id
    
    class FakeMessage:
        def __init__(self, chat_id, message_id):
            self.chat_id = chat_id
            self.message_id = message_id
            self.text = f"Time's up! You didn't answer in time."
        
        def edit_message_text(self, text, reply_markup=None):
            self.text = text
            return self
    
    class FakeCallbackQuery:
        def __init__(self, message, from_user):
            self.message = message
            self.from_user = from_user
            self.data = f"time_up_{question_index}"
        
        def answer(self, text):
            pass
        
        def edit_message_text(self, text, reply_markup=None):
            self.message.text = text
            return self.message
    
    fake_message = FakeMessage(chat_id, message_id)
    fake_user = FakeUser(user_id)
    fake_callback_query = FakeCallbackQuery(fake_message, fake_user)
    fake_update = FakeUpdate(fake_callback_query, fake_user)
    
    # Add time up button
    keyboard = [[InlineKeyboardButton("Continue", callback_data=f"time_up_{question_index}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Update the message
    question = session.get_current_question()
    if question:
        context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=f"{fake_message.text}\n\nThe correct answer was: {chr(65 + question.correct_option)}. {question.options[question.correct_option]}",
            reply_markup=reply_markup
        )
    
    # Record no answer (-1)
    session.record_answer(-1, False)

def time_up_callback(update: Update, context: CallbackContext) -> None:
    """Handle time up callback query."""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Check if the user is in an active quiz session
    if user_id not in active_sessions:
        query.answer("You are not currently taking a quiz.")
        query.edit_message_text("This quiz has expired. Use /take to start a new quiz.")
        return
    
    session = active_sessions[user_id]
    
    # Move to the next question
    session.move_to_next_question()
    
    # Answer the callback
    query.answer("Moving to next question...")
    
    # Check if there are more questions
    if session.get_current_question():
        # Send the next question
        send_quiz_question(update, context, session)
    else:
        # End the quiz
        end_quiz(update, context, session)

def end_quiz(update: Update, context: CallbackContext, session: QuizSession) -> None:
    """End the quiz and show results."""
    user_id = session.user_id
    
    # Calculate final score
    score = session.calculate_score()
    max_score = len(session.quiz.questions)
    
    # Get the user
    user = get_user(user_id)
    
    # Format the results message
    result_message = f"Quiz: {session.quiz.title}\n\n"
    result_message += f"Final score: {score}/{max_score} "
    result_message += f"({score/max_score*100:.1f}%)\n\n"
    
    # Add a summary of answers
    result_message += "Summary of your answers:\n"
    for i, (question, answer) in enumerate(zip(session.quiz.questions, session.answers)):
        result_message += f"{i+1}. "
        if answer['selected_option'] == -1:
            result_message += "❌ No answer\n"
        elif answer['is_correct']:
            result_message += "✅ Correct\n"
        else:
            result_message += "❌ Incorrect\n"
    
    # Inform about negative marking
    result_message += f"\nNegative marking factor: {session.quiz.negative_marking_factor}"
    
    # Add button to get PDF results
    keyboard = [[InlineKeyboardButton("Get PDF Results", callback_data=f"quiz_pdf_{session.quiz.id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Record the quiz result in the database
    record_quiz_result(user_id, session.quiz.id, score, max_score, session.answers)
    
    # Send the results
    if update.callback_query:
        update.callback_query.edit_message_text(result_message, reply_markup=reply_markup)
    else:
        context.bot.send_message(chat_id=user_id, text=result_message, reply_markup=reply_markup)
    
    # Remove the active session
    if user_id in active_sessions:
        del active_sessions[user_id]

def cancel_quiz(update: Update, context: CallbackContext) -> int:
    """Cancel the current quiz."""
    user_id = update.effective_user.id
    
    if user_id in active_sessions:
        del active_sessions[user_id]
        update.message.reply_text("Quiz canceled. Use /list to see available quizzes.")
    else:
        update.message.reply_text("You are not currently taking a quiz.")
    
    return -1  # End the conversation

def get_results(update: Update, context: CallbackContext) -> None:
    """Send quiz results to user in PDF format."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    
    # Get the user's quiz results
    results = get_user_quiz_results(user_id)
    
    if not results:
        update.message.reply_text("You haven't taken any quizzes yet.")
        return
    
    # Generate PDF
    pdf_buffer = generate_result_pdf(user_id, user.username or user.first_name or str(user_id), results)
    
    # Send the PDF
    update.message.reply_document(
        document=pdf_buffer,
        filename=f"quiz_results_{user_id}.pdf",
        caption="Here are your quiz results."
    )

def import_quiz(update: Update, context: CallbackContext) -> str:
    """Import a quiz from a file."""
    user_id = update.effective_user.id
    
    # Check if the user is an admin
    if user_id not in ADMIN_USERS:
        update.message.reply_text("Sorry, only admins can import quizzes.")
        return
    
    # Check if this is the initial command or file upload
    if update.message.document:
        # User has uploaded a file
        document = update.message.document
        
        # Check the file type (should be JSON)
        if not document.file_name.endswith('.json'):
            update.message.reply_text("Please upload a JSON file.")
            return "IMPORTING"
        
        # Download the file
        file = context.bot.get_file(document.file_id)
        
        # Process the file
        try:
            # Download the file content
            file_content = BytesIO()
            file.download(out=file_content)
            file_content.seek(0)
            
            # Parse the JSON
            quiz_data = json.loads(file_content.read().decode('utf-8'))
            
            # Import the quiz
            quiz = import_quiz_from_file(quiz_data, user_id)
            
            if quiz:
                update.message.reply_text(
                    f"Quiz imported successfully!\n\n"
                    f"Title: {quiz.title}\n"
                    f"Description: {quiz.description}\n"
                    f"Questions: {len(quiz.questions)}\n"
                    f"ID: {quiz.id}\n\n"
                    f"Use /list to see all quizzes."
                )
            else:
                update.message.reply_text("Failed to import quiz. Invalid format.")
        
        except Exception as e:
            logger.error(f"Error importing quiz: {e}")
            update.message.reply_text(f"Error importing quiz: {str(e)}")
        
        return
    else:
        # Initial command
        update.message.reply_text(
            "Please upload a JSON file with your quiz data.\n\n"
            "The file should have the following format:\n"
            "{\n"
            '  "title": "Quiz Title",\n'
            '  "description": "Quiz Description",\n'
            '  "time_limit": 60,\n'
            '  "negative_marking_factor": 0.25,\n'
            '  "questions": [\n'
            '    {\n'
            '      "text": "Question text",\n'
            '      "options": ["Option A", "Option B", "Option C", "Option D"],\n'
            '      "correct_option": 0,\n'
            '      "time_limit": 30\n'
            '    },\n'
            '    ...\n'
            '  ]\n'
            "}\n\n"
            "Use /cancel to cancel."
        )
        
        return "IMPORTING"

def quiz_callback(update: Update, context: CallbackContext) -> None:
    """Handle quiz-related callback queries."""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Parse the callback data
    data = query.data.split('_')
    if len(data) < 3:
        query.answer("Invalid callback data")
        return
    
    action = data[1]
    quiz_id = data[2]
    
    if action == "pdf":
        # Generate and send PDF results
        user = get_user(user_id)
        results = get_user_quiz_results(user_id)
        
        # Filter results for specific quiz if needed
        if quiz_id != "all":
            results = [r for r in results if r['quiz_id'] == quiz_id]
        
        if not results:
            query.answer("No results found")
            return
        
        # Generate PDF
        pdf_buffer = generate_result_pdf(user_id, user.username or user.first_name or str(user_id), results)
        
        # Answer the callback
        query.answer("Generating PDF results...")
        
        # Send the PDF
        context.bot.send_document(
            chat_id=user_id,
            document=pdf_buffer,
            filename=f"quiz_results_{user_id}.pdf",
            caption="Here are your quiz results."
        )
    else:
        query.answer("Unknown action")
