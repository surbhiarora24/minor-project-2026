import pymupdf
from pathlib import Path

STATEMENT_HEADERS = (
    "balance sheet",
    "statement of profit and loss",
    "profit and loss",
    "statement of financial position",
    "income statement",
)

LINE_ITEM_KEYWORDS = (
    "total income",
    "total revenue",
    "total assets",
    "total equity",
    "profit for the year",
    "profit before tax",
    "total liabilities",
)


def _is_financial_statement_page(text_lower):
    """True only for actual Balance Sheet or P&L pages, skipping narrative mentions."""
    has_header = any(h in text_lower for h in STATEMENT_HEADERS)
    line_item_hits = sum(1 for kw in LINE_ITEM_KEYWORDS if kw in text_lower)
    return (has_header and line_item_hits >= 2) or line_item_hits >= 3


def read_pdf(path):
    path = Path(path)

    if path.suffix.lower() != ".pdf":
        raise ValueError("Input file must be a PDF.")

    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {path}")

    pages = []

    with pymupdf.open(path) as pdf:
        if len(pdf) == 0:
            raise ValueError("PDF contains no pages.")

        for number, page in enumerate(pdf, start=1):
            text = page.get_text("text")
            text_lower = text.lower()
            tables = []

            if _is_financial_statement_page(text_lower):
                for table in page.find_tables().tables:
                    tables.append(table.extract())

            pages.append({
                "page": number,
                "text": text,
                "tables": tables,
                "images": 0,
            })

    return pages
