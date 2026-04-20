"""Literature search library — standalone, zero external dependencies.

Quick start:
    from lib.search import search_papers, search_papers_multi_query, papers_to_bibtex
    from lib.models import Paper, Author
"""

from .models import Author, Paper
from .search import papers_to_bibtex, search_papers, search_papers_multi_query

__all__ = [
    "Author",
    "Paper",
    "search_papers",
    "search_papers_multi_query",
    "papers_to_bibtex",
]
