from typing import Annotated

from mock_data import DOCUMENTS, CLAIM_VERIFICATION

def get_document_span(
    document_id: Annotated[str,'The document id to retrieve from.'],
    page: Annotated[str,'The page key inside the document (e.g. page_12).'],
)->str:
    doc = DOCUMENTS.get(document_id)
    if not doc:
        return "document not found"
    span = doc.get(page)
    if not span:
        return 'span not found'
    return span

def get_claim_verdict(
    claim: Annotated[str,"The factual claim from the report to verify."],
)->str:
    """Return a verification verdict for a claim: SUPPORTED, MISMATCH OR UNSUPPORTED"""
    return CLAIM_VERIFICATION.get(claim, "UNSUPPORTED")

def flag_for_manual_review(
    claim: Annotated[str,"The claim that requires human review."],
    reason: Annotated[str,"Why it needs review: MISMATCH or UNSUPPORTED."]
)->str:
    """Flag a claim for manual review."""
    return f'flagged: {claim} - reason: {reason}'
