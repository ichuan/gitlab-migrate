"""GitLab Migration Tool

A comprehensive tool for migrating users, repositories, groups, and projects
from one GitLab instance to another using API-based migration approaches.
"""

__version__ = '0.1.0'
__author__ = 'GitLab Migration Team'
__email__ = 'team@example.com'

from .cli import main

__all__ = ['main']
