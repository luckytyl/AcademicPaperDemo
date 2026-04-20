"""Citation verifier library — standalone, zero external dependencies.

Quick start:
    from lib.verify import verify_citations, filter_verified_bibtex, annotate_paper_hallucinations
    from lib.verify import VerifyStatus, VerificationReport
"""

from .verify import (
    VerificationReport,
    VerifyStatus,
    CitationResult,
    annotate_paper_hallucinations,
    filter_verified_bibtex,
    parse_bibtex_entries,
    verify_citations,
)

__all__ = [
    "VerifyStatus",
    "CitationResult",
    "VerificationReport",
    "verify_citations",
    "filter_verified_bibtex",
    "annotate_paper_hallucinations",
    "parse_bibtex_entries",
]
