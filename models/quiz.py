#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Model classes for quizzes and questions
"""

import uuid
from datetime import datetime

class Question:
    """
    Class to represent a quiz question
    """
    
    def __init__(self, text, options, correct_option, time_limit=None):
        """
        Initialize a question
        
        Args:
            text (str): The question text
            options (list): List of answer options
            correct_option (int): Index of the correct option (0-based)
            time_limit (int, optional): Time limit for this specific question in seconds.
                                      If None, the quiz's default time limit will be used.
        """
        self.text = text
        self.options = options
        self.correct_option = correct_option
        self.time_limit = time_limit
    
    def to_dict(self):
        """Convert question to dictionary for serialization"""
        return {
            'text': self.text,
            'options': self.options,
            'correct_option': self.correct_option,
            'time_limit': self.time_limit
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create question from dictionary data"""
        return cls(
            data['text'],
            data['options'],
            data['correct_option'],
            data.get('time_limit')
        )

class Quiz:
    """
    Class to represent a quiz with multiple questions
    """
    
    def __init__(self, title, description, creator_id, time_limit=60, negative_marking_factor=0.25):
        """
        Initialize a quiz
        
        Args:
            title (str): The quiz title
            description (str): Quiz description
            creator_id (int): Telegram ID of the creator
            time_limit (int): Time limit for each question in seconds
            negative_marking_factor (float): Factor for negative marking
        """
        self.id = str(uuid.uuid4())[:8]  # Generate a short unique ID
        self.title = title
        self.description = description
        self.creator_id = creator_id
        self.time_limit = time_limit
        self.negative_marking_factor = negative_marking_factor
        self.questions = []
        self.created_at = datetime.now().timestamp()
    
    def add_question(self, question):
        """
        Add a question to the quiz
        
        Args:
            question (Question): The question to add
        """
        self.questions.append(question)
    
    def get_question(self, index):
        """
        Get a question by index
        
        Args:
            index (int): The question index
            
        Returns:
            Question: The question at the specified index or None
        """
        if 0 <= index < len(self.questions):
            return self.questions[index]
        return None
    
    def set_question_time_limit(self, question_index, time_limit):
        """
        Set the time limit for a specific question
        
        Args:
            question_index (int): The index of the question
            time_limit (int): New time limit in seconds, or None to use quiz default
            
        Returns:
            bool: True if successful, False otherwise
        """
        if 0 <= question_index < len(self.questions):
            self.questions[question_index].time_limit = time_limit
            return True
        return False
    
    def to_dict(self):
        """Convert quiz to dictionary for serialization"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'creator_id': self.creator_id,
            'time_limit': self.time_limit,
            'negative_marking_factor': self.negative_marking_factor,
            'questions': [q.to_dict() for q in self.questions],
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create quiz from dictionary data"""
        quiz = cls(
            data['title'],
            data['description'],
            data['creator_id'],
            data['time_limit'],
            data['negative_marking_factor']
        )
        quiz.id = data['id']
        quiz.created_at = data.get('created_at', datetime.now().timestamp())
        
        # Add questions
        for q_data in data['questions']:
            quiz.add_question(Question.from_dict(q_data))
        
        return quiz
