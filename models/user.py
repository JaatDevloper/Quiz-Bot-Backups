#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Model class for users
"""

class User:
    """
    Class to represent a user
    """
    
    def __init__(self, user_id, username=None, first_name=None, last_name=None):
        """
        Initialize a user
        
        Args:
            user_id (int): Telegram user ID
            username (str, optional): Telegram username
            first_name (str, optional): User's first name
            last_name (str, optional): User's last name
        """
        self.id = user_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name
    
    def to_dict(self):
        """Convert user to dictionary for serialization"""
        return {
            'id': self.id,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name
        }
    
    @classmethod
    def from_dict(cls, data):
        """Create user from dictionary data"""
        return cls(
            data['id'],
            data.get('username'),
            data.get('first_name'),
            data.get('last_name')
        )
