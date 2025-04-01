#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
In-memory database for quiz data
"""

import json
from datetime import datetime
from models.quiz import Quiz, Question
from models.user import User

# In-memory database
quizzes = {}
users = {}
quiz_results = {}

def get_quizzes():
    """Get all quizzes"""
    return quizzes

def get_quiz(quiz_id):
    """Get a specific quiz by ID"""
    return quizzes.get(quiz_id)

def add_quiz(quiz):
    """Add a quiz to the database"""
    quizzes[quiz.id] = quiz
    return quiz.id

def update_quiz_time(quiz_id, time_limit):
    """Update the overall time limit for a quiz"""
    if quiz_id in quizzes:
        quizzes[quiz_id].time_limit = time_limit
        return True
    return False

def update_question_time_limit(quiz_id, question_index, time_limit):
    """Update the time limit for a specific question in a quiz"""
    if quiz_id in quizzes:
        return quizzes[quiz_id].set_question_time_limit(question_index, time_limit)
    return False

def delete_quiz(quiz_id):
    """Delete a quiz"""
    if quiz_id in quizzes:
        del quizzes[quiz_id]
        return True
    return False

def get_user(user_id, username=None, first_name=None, last_name=None):
    """Get a user by ID or create one if it doesn't exist"""
    if user_id not in users:
        users[user_id] = User(user_id, username, first_name, last_name)
    return users[user_id]

def record_user_answer(user_id, quiz_id, question_index, selected_option, is_correct):
    """Record a user's answer to a specific question"""
    # Initialize user's quiz results if needed
    if user_id not in quiz_results:
        quiz_results[user_id] = {}
    
    if quiz_id not in quiz_results[user_id]:
        quiz_results[user_id][quiz_id] = {
            'quiz_id': quiz_id,
            'answers': [],
            'timestamp': datetime.now().timestamp(),
        }
    
    # Get the question for more detailed recording
    quiz = get_quiz(quiz_id)
    question = None
    if quiz and 0 <= question_index < len(quiz.questions):
        question = quiz.questions[question_index]
    
    # Record answer with all details
    answer_data = {
        'question_index': question_index,
        'selected_option': selected_option,
        'is_correct': is_correct,
    }
    
    # Add question details if available
    if question:
        answer_data['question_text'] = question.text
        answer_data['options'] = question.options
        answer_data['correct_option'] = question.correct_option
    
    # Add to answers list
    quiz_results[user_id][quiz_id]['answers'].append(answer_data)

def record_quiz_result(user_id, quiz_id, score, max_score, answers):
    """Record a quiz result for a user"""
    # Initialize user's quiz results if needed
    if user_id not in quiz_results:
        quiz_results[user_id] = {}
    
    # Get the quiz for title and other details
    quiz = get_quiz(quiz_id)
    quiz_title = quiz.title if quiz else f"Quiz {quiz_id}"
    
    # Format the answers for recording
    formatted_answers = []
    for i, answer in enumerate(answers):
        formatted_answer = {
            'question_index': i,
            'question_text': answer.get('question_text', f"Question {i+1}"),
            'selected_option': answer.get('selected_option', -1),
            'is_correct': answer.get('is_correct', False),
            'options': answer.get('options', []),
            'correct_option': answer.get('correct_option', 0)
        }
        formatted_answers.append(formatted_answer)
    
    # Create result entry
    quiz_results[user_id][quiz_id] = {
        'quiz_id': quiz_id,
        'quiz_title': quiz_title,
        'score': score,
        'max_score': max_score,
        'timestamp': datetime.now().timestamp(),
        'answers': formatted_answers,
        'negative_marking_factor': quiz.negative_marking_factor if quiz else 0.25
    }

def get_user_quiz_results(user_id):
    """Get all quiz results for a user"""
    if user_id not in quiz_results:
        return []
    
    # Format results for the user
    results = []
    for quiz_id, result in quiz_results[user_id].items():
        # Calculate percentage
        max_score = result.get('max_score', 0)
        score = result.get('score', 0)
        percentage = (score / max_score * 100) if max_score > 0 else 0
        
        formatted_result = {
            'quiz_id': quiz_id,
            'quiz_title': result.get('quiz_title', f"Quiz {quiz_id}"),
            'score': score,
            'max_score': max_score,
            'percentage': round(percentage, 1),
            'timestamp': result.get('timestamp', 0),
            'date': datetime.fromtimestamp(result.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M'),
            'answers': result.get('answers', []),
            'negative_marking_factor': result.get('negative_marking_factor', 0.25)
        }
        results.append(formatted_result)
    
    # Sort by timestamp (most recent first)
    return sorted(results, key=lambda x: x['timestamp'], reverse=True)

def get_quiz_results(quiz_id):
    """Get all results for a specific quiz"""
    results = []
    for user_id, user_results in quiz_results.items():
        if quiz_id in user_results:
            results.append({
                'user_id': user_id,
                'result': user_results[quiz_id]
            })
    return results

def export_quiz(quiz_id):
    """Export a quiz to JSON format"""
    quiz = get_quiz(quiz_id)
    if not quiz:
        return None
    
    return json.dumps(quiz.to_dict(), indent=2)
