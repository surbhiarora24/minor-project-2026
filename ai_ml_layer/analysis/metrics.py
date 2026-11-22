import re

_NUMBER = re.compile(r"(?<![A-Za-z])\(?-?\d[\d,]*(?:\.\d+)?\)?")


def to_number(value):
    if value is None:
        return None
    text = str(value).strip().replace("₹", "").replace("INR", "").replace(" ", "")
    if not text or text in {"-", "—", "–"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return -abs(number) if negative else number


def _numbers(text):
    found = []
    for match in _NUMBER.finditer(str(text)):
        raw = match.group(0)
        value = to_number(raw)
        if value is not None:
            found.append((raw, value))
    return found


def _filter_note_column(raw_val_pairs):
    """If the first number is a small integer Note reference (e.g. '21') followed by 2+ larger figures, skip it."""
    if len(raw_val_pairs) >= 3:
        first_raw, first_val = raw_val_pairs[0]
        _, second_val = raw_val_pairs[1]
        if (
            "," not in first_raw
            and "." not in first_raw
            and 1 <= abs(first_val) <= 65
            and abs(second_val) > 100
        ):
            return [v for _, v in raw_val_pairs[1:]]
    return [v for _, v in raw_val_pairs]


def _normalise(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower()).strip(" :.")


def _section_pages(pages, basis):
    basis = (basis or "Unspecified").strip().lower()
    if basis not in {"standalone", "consolidated"}:
        raise ValueError("Select Standalone or Consolidated figures before analysing this report.")

    other = "consolidated" if basis == "standalone" else "standalone"
    statement_markers = (
        "balance sheet",
        "statement of profit and loss",
        "statement of financial position",
        "income statement",
    )

    # First pass: find actual financial statement pages (not Table of Contents or Board's Report mentions)
    matched = []
    for i, page in enumerate(pages):
        text = _normalise(page.get("text", ""))
        if basis in text and any(sm in text for sm in statement_markers):
            # Include this statement page and the next 6 pages (covers Balance Sheet + P&L)
            matched.extend(pages[i : min(len(pages), i + 7)])

    if matched:
        # Deduplicate preserving page order
        seen = set()
        unique_pages = []
        for p in matched:
            if p["page"] not in seen:
                seen.add(p["page"])
                unique_pages.append(p)
        return unique_pages

    # Fallback: original marker scan skipping early Table of Contents pages
    marker = basis + " financial"
    other_marker = other + " financial"
    starts = [
        i for i, p in enumerate(pages)
        if marker in _normalise(p.get("text", "")) and p.get("page", 0) > 15
    ]
    if not starts:
        raise ValueError(f"Could not find the {basis.title()} Financial Statements section in this PDF.")

    start = starts[0]
    end = len(pages)
    for i in range(start + 1, len(pages)):
        text = _normalise(pages[i].get("text", ""))
        if other_marker in text and not text.startswith("notes to"):
            end = i
            break
    return pages[start:end]


def _pair_from_table(page, labels):
    for table in page.get("tables", []):
        for row in table or []:
            cells = [str(cell or "").strip() for cell in row]
            for i, cell in enumerate(cells):
                cell_label = _normalise(cell)
                if any(cell_label == lbl or cell_label.startswith(lbl + " ") for lbl in labels):
                    values = _filter_note_column(_numbers(" ".join(cells[i + 1 :])))
                    if len(values) >= 2:
                        return values[0], values[1]
    return None


def _pair_from_text(page, labels):
    lines = [line.strip() for line in str(page.get("text", "")).splitlines() if line.strip()]
    for i, line in enumerate(lines):
        normal = _normalise(line)
        if any(normal == lbl or normal.startswith(lbl + " ") for lbl in labels):
            nearby = " ".join(lines[i : i + 5])
            values = _filter_note_column(_numbers(nearby))
            if len(values) >= 2:
                return values[0], values[1]
    return None


def find_two_values(pages, labels):
    norm_labels = [_normalise(lbl) for lbl in labels]
    for page in pages:
        pair = _pair_from_table(page, norm_labels)
        if pair is None:
            pair = _pair_from_text(page, norm_labels)
        if pair is not None:
            return {"page": page["page"], "this_year": pair[0], "last_year": pair[1]}
    return None


def change_percent(now, before):
    if before is None or before == 0:
        return None
    return (now - before) / abs(before) * 100


def extract_metrics(pages, basis="Unspecified"):
    selected_pages = _section_pages(pages, basis)
    label_groups = {
        "Total income": ["total income", "revenue from operations", "revenue"],
        "Profit for the year": ["profit for the year", "profit attributable to equity holders", "net profit"],
        "Total assets": ["total assets"],
        "Total equity": ["total equity"],
    }
    return {name: find_two_values(selected_pages, lbls) for name, lbls in label_groups.items()}
