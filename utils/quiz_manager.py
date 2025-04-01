#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Quiz management utilities for handling active quiz sessions
"""

import json
import logging
import uuid
from models.quiz import Quiz, Question
from utils.database import record_user_answer

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class QuizSession:
    """
    Class to manage an active quiz session for a user
    """
    
    def __init__(self, user_id, quiz):
        """
        Initialize a quiz session
        
        Args:
            user_id (int): Telegram user ID
            quiz (Quiz): The quiz being taken
        """
        self.user_id = user_id
        self.quiz = quiz
        self.current_question_index = 0
        self.answers = []
        
        # Initialize answer placeholders for each question
        for _ in range(len(quiz.questions)):
            self.answers.append({
                'selected_option': -1,  # -1 means no answer
                'is_correct': False
            })
    
    def get_current_question(self):
        """Get the current question or None if quiz is over"""
        if self.current_question_index < len(self.quiz.questions):
            return self.quiz.questions[self.current_question_index]
        return None
    
    def record_answer(self, selected_option, is_correct):
        """Record user's answer for the current question"""
        if self.current_question_index < len(self.answers):
            # Get the current question for more details
            question = self.get_current_question()
            
            # Create detailed answer record
            answer = {
                'selected_option': selected_option,
                'is_correct': is_correct
            }
            
            # Add question details if available
            if question:
                answer['question_text'] = question.text
                answer['options'] = question.options
                answer['correct_option'] = question.correct_option
            
            # Update the answers list
            self.answers[self.current_question_index] = answer
            
            # Record in database for persistence
            record_user_answer(
                self.user_id,
                self.quiz.id,
                self.current_question_index,
                selected_option,
                is_correct
            )
    
    def move_to_next_question(self):
        """Move to the next question"""
        self.current_question_index += 1
    
    def calculate_score(self):
        """Calculate the final score with negative marking"""
        score = 0
        for answer in self.answers:
            if answer['is_correct']:
                score += 1
            elif answer['selected_option'] != -1:  # Wrong answer (but not no answer)
                score -= self.quiz.negative_marking_factor
        
        return max(0, score)  # Score can't go below 0

def import_quiz_from_file(quiz_data, creator_id):
    """
    Import a quiz from JSON data
    
    Args:
        quiz_data (dict): Quiz data in JSON format
        creator_id (int): ID of the user importing the quiz
        
    Returns:
        Quiz: The imported quiz object
    """
    try:
        # Required fields
        required_fields = ['title', 'description', 'questions']
        for field in required_fields:
            if field not in quiz_data:
                logger.error(f"Missing required field: {field}")
                return None
        
        # Create quiz
        title = quiz_data['title']
        description = quiz_data['description']
        time_limit = quiz_data.get('time_limit', 60)
        negative_marking_factor = quiz_data.get('negative_marking_factor', 0.25)
        
        quiz = Quiz(title, description, creator_id, time_limit, negative_marking_factor)
        
        # Add questions
        for q_data in quiz_data['questions']:
            # Required question fields
            q_required_fields = ['text', 'options', 'correct_option']
            for field in q_required_fields:
                if field not in q_data:
                    logger.error(f"Missing required question field: {field}")
                    return None
            
            # Validate question data
            if not isinstance(q_data['options'], list) or len(q_data['options']) < 2:
                logger.error("Options must be a list with at least 2 options")
                return None
            
            if not isinstance(q_data['correct_option'], int) or q_data['correct_option'] < 0 or q_data['correct_option'] >= len(q_data['options']):
                logger.error("correct_option must be a valid index into the options list")
                return None
            
            # Create question
            question = Question(
                q_data['text'],
                q_data['options'],
                q_data['correct_option'],
                q_data.get('time_limit')  # Optional per-question time limit
            )
            
            quiz.add_question(question)
        
        return quiz
    
    except Exception as e:
        logger.error(f"Error importing quiz: {e}")
        return None
