#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Utility for generating PDF reports of quiz results
"""

import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def generate_result_pdf(user_id, user_name, results):
    """
    Generate a PDF report of user's quiz results
    
    Args:
        user_id (int): The user's ID
        user_name (str): The user's name
        results (list): List of result dictionaries
        
    Returns:
        BytesIO: PDF file buffer
    """
    buffer = io.BytesIO()
    
    # Create the PDF document
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Create custom styles
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=1,  # Center aligned
        spaceAfter=12
    )
    
    subtitle_style = ParagraphStyle(
        'SubtitleStyle',
        parent=styles['Heading2'],
        fontSize=14,
        spaceAfter=6
    )
    
    normal_style = styles['Normal']
    
    # Build the document content
    content = []
    
    # Add title
    content.append(Paragraph(f"Quiz Results for {user_name}", title_style))
    content.append(Spacer(1, 0.25*inch))
    content.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}", normal_style))
    content.append(Spacer(1, 0.5*inch))
    
    if not results:
        content.append(Paragraph("No quiz results found.", normal_style))
    else:
        # Sort results by date (most recent first)
        sorted_results = sorted(results, key=lambda x: x.get('timestamp', 0), reverse=True)
        
        for i, result in enumerate(sorted_results):
            quiz_title = result.get('quiz_title', 'Unknown Quiz')
            score = result.get('score', 0)
            max_score = result.get('max_score', 0)
            percentage = (score / max_score) * 100 if max_score > 0 else 0
            timestamp = result.get('timestamp', 0)
            date_str = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M') if timestamp else 'Unknown'
            
            # Add quiz result header
            content.append(Paragraph(f"{i+1}. {quiz_title}", subtitle_style))
            content.append(Paragraph(f"Date: {date_str}", normal_style))
            content.append(Paragraph(f"Score: {score:.2f}/{max_score} ({percentage:.1f}%)", normal_style))
            
            # Add question details if available
            if 'answers' in result:
                content.append(Spacer(1, 0.2*inch))
                content.append(Paragraph("Question Details:", normal_style))
                
                # Create table for answers
                table_data = [
                    ["Question", "Your Answer", "Correct?", "Points"]
                ]
                
                negative_factor = result.get('negative_marking_factor', 0.25)
                
                for j, answer in enumerate(result['answers']):
                    q_text = answer.get('question_text', f"Question {j+1}")
                    selected_option = answer.get('selected_option', -1)
                    is_correct = answer.get('is_correct', False)
                    
                    if selected_option == -1:
                        ans_text = "No answer"
                    else:
                        ans_text = answer.get('options', [])[selected_option] if 'options' in answer else f"Option {selected_option+1}"
                    
                    points = 1 if is_correct else -negative_factor if selected_option != -1 else 0
                    
                    table_data.append([
                        q_text[:50] + "..." if len(q_text) > 50 else q_text,
                        ans_text[:20] + "..." if len(ans_text) > 20 else ans_text,
                        "✓" if is_correct else "✗",
                        f"{points:+.2f}"
                    ])
                
                # Create table style
                table_style = TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ])
                
                # Add alternating row colors
                for i in range(1, len(table_data)):
                    if i % 2 == 0:
                        table_style.add('BACKGROUND', (0, i), (-1, i), colors.white)
                
                # Create the table
                table = Table(table_data, colWidths=[2.5*inch, 2*inch, 0.75*inch, 0.75*inch])
                table.setStyle(table_style)
                
                content.append(table)
            
            content.append(Spacer(1, 0.5*inch))
    
    # Build the PDF
    doc.build(content)
    
    # Reset buffer position to the beginning
    buffer.seek(0)
    return buffer
