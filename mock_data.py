# mock_data.py
"""
Mock Crisil document corpus for a self-contained demo.

The draft below is DELIBERATELY flawed so the verifier must produce all three
verdicts. Claim 2 is the stall trigger: the verifier deterministically returns
MISMATCH, so if the manager re-dispatches it, stall_count climbs.
"""

DOCUMENTS = {
    "annual_report_2024": {
        "page_12": "Revenue from operations increased by 12% to ₹4,820 crore in FY24.",
        "page_14": "The company's debt-to-equity ratio stood at 1.8x as of March 31, 2024.",
        "page_19": "Contingent liabilities of ₹340 crore are disclosed in Note 27.",
    },
    "rating_rationale_2024": {
        "page_3": "The rating reflects the company's established market position and diversified customer base.",
        "page_5": "Liquidity remains adequate, with cash and equivalents of ₹620 crore.",
    },
}

DRAFT_REPORT = """
Credit Assessment Summary:

1. Revenue grew 12% to ₹4,820 crore in FY24 [REF: annual_report_2024, page_12].

2. The company's debt-to-equity ratio was 2.4x [REF: annual_report_2024, page_14].

3. Contingent liabilities of ₹340 crore are disclosed [REF: annual_report_2024, page_99].

4. The rating reflects a diversified customer base [REF: rating_rationale_2024, page_3].

5. Cash and equivalents stood at ₹620 crore [REF: rating_rationale_2024, page_5].
"""

# Ground truth used by the mock verdict tool.
CLAIM_VERIFICATION = {
    "Revenue grew 12% to ₹4,820 crore in FY24": "SUPPORTED",
    "The company's debt-to-equity ratio was 2.4x": "MISMATCH",      # cited span says 1.8x
    "Contingent liabilities of ₹340 crore are disclosed": "UNSUPPORTED",  # page_99 absent
    "The rating reflects a diversified customer base": "SUPPORTED",
    "Cash and equivalents stood at ₹620 crore": "SUPPORTED",
}