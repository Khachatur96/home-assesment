import constants as c
import re
from enums import EmailClass
import subprocess



def classify_urgency(response):
    # Convert the response to lowercase to handle case variations
    response = response.lower()
    
    # Define patterns for urgent and non-urgent keywords
    urgent_keywords = ['urgent', 'important', 'crucial', 'critical']
    negations = ['not', 'non', 'less']

    # Check for urgent keywords with preceding negation
    pattern_urgent = r'\b(?:' + '|'.join(urgent_keywords) + r')\b'
    pattern_negation = r'\b(?:' + '|'.join(negations) + r')\s+(?:' + '|'.join(urgent_keywords) + r')\b'

    # Search for patterns in the response
    if re.search(pattern_negation, response):
        return EmailClass.NOT_URGENT
    elif re.search(pattern_urgent, response):
        return EmailClass.URGENT
    else:
        return None
