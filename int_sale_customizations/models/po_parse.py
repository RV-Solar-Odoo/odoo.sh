"""Read a purchase order without guessing.

Spreadsheets are matched by the heading row. PDF text is matched against
part numbers we already sell. Nothing here calls Odoo or a language model.
"""
import csv
import io
import re

ROW_LIMIT = 500
QTY_LIMIT = 100000

# First match wins, so a line number called "Item" loses to Material / SKU / MPN.
PART_LABELS = (
    "sku",
    "mpn",
    "manufacturer part number",
    "manufacturers part number",
    "manufacturer part no",
    "manufacturers part no",
    "manufacturer part",
    "mfr part number",
    "mfr part no",
    "mfr part",
    "mfg part number",
    "mfg part no",
    "mfg part",
    "vendor part number",
    "vendor part no",
    "vendor part",
    "vendor item number",
    "vendor item",
    "vendor sku",
    "supplier part number",
    "supplier part no",
    "supplier part",
    "supplier item number",
    "supplier item",
    "supplier sku",
    "source part num",
    "source part number",
    "your part number",
    "your part no",
    "your item number",
    "barcode",
    "upc",
    "ean",
    "gtin",
    "internal reference",
    "product code",
    "product number",
    "item code",
    "item number",
    "item no",
    "catalog number",
    "catalogue number",
    "catalog no",
    "part number",
    "part no",
    "material number",
    "material no",
    "material",
    "part",
    "product service",
    "product",
    "item",
)
QTY_LABELS = (
    "quantity ordered",
    "qty ordered",
    "ordered quantity",
    "order quantity",
    "order qty",
    "ordered qty",
    "po quantity",
    "qty ord",
    "quantity",
    "qty",
    "units",
    "ordered",
)
PO_LABELS = (
    "po number",
    "purchase order number",
    "purchase order no",
    "customer po number",
    "customer po",
    "purchase order",
    "po no",
    "po num",
    "po",
)
PO_LABEL_SET = set(PO_LABELS)
NEIGHBOR_STOP = PO_LABEL_SET | {
    "date", "order date", "document date", "delivery date", "vendor",
    "ship to", "ship via", "bill to",
}
SKIP_PARTS = {
    "subtotal", "total", "grand total", "tax", "sales tax", "shipping",
    "freight", "discount", "balance", "balance due", "amount due",
    "comments", "comment", "notes", "note", "special instructions",
}

PDF_STOP = {
    "QTY", "QUANTITY", "SKU", "ITEM", "PART", "TOTAL", "SUBTOTAL", "TAX",
    "SHIPPING", "PRICE", "AMOUNT", "DESCRIPTION", "DATE", "PAGE", "EACH",
    "UNIT", "UNITS", "PO", "NUMBER", "PURCHASE", "ORDER", "CUSTOMER",
    "INVOICE", "USD", "EXT", "EXTENDED", "SHIP", "BILL", "EA", "PCS",
    "RATE", "MATERIAL", "SERVICE", "PRODUCT",
}
PDF_TOKEN = re.compile(
    r"\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    r"|"
    r"[A-Za-z0-9][A-Za-z0-9._/\-]*"
)
PDF_PO = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"customer[^\S\n]+po(?![A-Za-z])"
    r"|purchase[^\S\n]+order(?![A-Za-z])"
    r"|p\.?[^\S\n]*o\.?(?![A-Za-z])(?![^\S\n]*box\b)"
    r")"
    r"[^\S\n]*(?:number|no\.?|num|#)?"
    r"[^\S\n]*[:#\-]?[^\S\n]*"
    r"([A-Za-z0-9][A-Za-z0-9\-]{1,40})",
    re.IGNORECASE,
)
QTY_TEXT = re.compile(r"-?\d+(?:\.\d+)?")
DATE_TEXT = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
PHONE_TEXT = re.compile(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}")
MONEY_TEXT = re.compile(r"\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})")


class PoParseError(Exception):
    """A file we can identify but not turn into rows. ``code`` is header, limit, or csv."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def norm_label(value):
    text = str(value or "").strip().lower().replace("#", " number ").replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = " ".join(text.split())
    text = text.replace("p o ", "po ")
    if text == "p o":
        text = "po"
    return text


def norm_code(value):
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def cell_text(value):
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return str(value).strip()


def parse_quantity(value):
    """Return ``(number, reason_code)``. A whole number comes back as an int."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, "missing_qty"
    if isinstance(value, bool):
        return None, "bad_qty"
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = QTY_TEXT.search(str(value).replace(",", ""))
        if not match:
            return None, "bad_qty"
        number = float(match.group(0))
    if number <= 0:
        return None, "bad_qty"
    if number > QTY_LIMIT:
        return None, "huge"
    if abs(number - round(number)) < 1e-9:
        return int(round(number)), None
    return number, None


def _labels(row):
    return [norm_label(cell) for cell in row]


def _columns(labels, ordered):
    positions = {}
    for index, label in enumerate(labels):
        if label and label not in positions:
            positions[label] = index
    return [positions[label] for label in ordered if label in positions]


def _plausible_po(value):
    text = cell_text(value).strip()
    if not text or len(text) > 30 or any(char.isspace() and char != " " for char in text):
        return ""
    if " " in text and not re.match(r"(?i)^(?:po|p\.?o\.?)\b", text):
        return ""
    if not re.search(r"\d", text):
        return ""
    if DATE_TEXT.fullmatch(text) or PHONE_TEXT.fullmatch(text) or MONEY_TEXT.fullmatch(text):
        return ""
    if norm_label(text) in PO_LABEL_SET:
        return ""
    return text[:80]


def _inline_po(value):
    match = PDF_PO.search(cell_text(value))
    return _plausible_po(match.group(1)) if match else ""


def _neighbor_po(rows, row_index, cell_index):
    """The number beside a PO label, or directly under it on a printed form."""
    row = rows[row_index]
    for offset in range(1, 4):
        if cell_index + offset >= len(row):
            break
        value = cell_text(row[cell_index + offset])
        if not value:
            continue
        if norm_label(value) in NEIGHBOR_STOP:
            break
        found = _plausible_po(value) or _inline_po(value)
        if found:
            return found
        break
    if row_index + 1 < len(rows):
        below = rows[row_index + 1]
        if cell_index < len(below):
            return _plausible_po(below[cell_index])
    return ""


def _po_on_row(rows, row_index):
    row = rows[row_index]
    for cell_index, cell in enumerate(row):
        found = _inline_po(cell)
        if found:
            return found
        if norm_label(cell) in PO_LABEL_SET:
            found = _neighbor_po(rows, row_index, cell_index)
            if found:
                return found
    return ""


def parse_sheet_rows(rows):
    """Return ``(po_number, [{"sku", "qty"}, ...])`` from cell values."""
    po_number = ""
    header_index = None
    part_cols = []
    qty_col = po_col = None
    for index, row in enumerate(rows[:40]):
        labels = _labels(row)
        parts = _columns(labels, PART_LABELS)
        qtys = _columns(labels, QTY_LABELS)
        if parts and qtys:
            header_index = index
            part_cols = parts
            qty_col = qtys[0]
            po_cols = _columns(labels, PO_LABELS)
            po_col = po_cols[0] if po_cols else None
            break
        if not po_number:
            po_number = _po_on_row(rows, index)
    if header_index is None:
        raise PoParseError("header")
    parsed = []
    for row in rows[header_index + 1:]:
        if not row or all(cell in (None, "") or (isinstance(cell, str) and not str(cell).strip()) for cell in row):
            continue
        sku = ""
        for col in part_cols:
            if col < len(row) and cell_text(row[col]):
                sku = cell_text(row[col])
                break
        qty = row[qty_col] if qty_col < len(row) else None
        if norm_label(sku) in SKIP_PARTS:
            continue
        if po_col is not None and not po_number and po_col < len(row):
            value = _plausible_po(row[po_col]) or _inline_po(row[po_col])
            if value:
                po_number = value
        if not sku and (qty is None or qty == ""):
            continue
        parsed.append({"sku": sku, "qty": qty})
        if len(parsed) > ROW_LIMIT:
            raise PoParseError("limit")
    return po_number, parsed


def parse_csv_bytes(raw):
    text = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise PoParseError("csv")
    return parse_sheet_rows(list(csv.reader(io.StringIO(text))))


def index_products(products):
    """Map a normalized part number to the products that use it."""
    index = {}
    for product in products:
        for raw in (product.get("default_code"), product.get("barcode")):
            key = norm_code(raw)
            if len(key) < 2:
                continue
            bucket = index.setdefault(key, [])
            if all(item["id"] != product["id"] for item in bucket):
                bucket.append(product)
    return index


def _lookup(sku, index):
    """Exact part number, or the longest catalog code inside a longer item name."""
    key = norm_code(sku)
    if not key:
        return []
    if key in index:
        return index[key]
    if len(key) < 6:
        return []
    best_len = 0
    found = []
    for candidate, products in index.items():
        if len(candidate) < 6 or candidate not in key:
            continue
        if len(candidate) > best_len:
            best_len = len(candidate)
            found = list(products)
        elif len(candidate) == best_len:
            for product in products:
                if all(item["id"] != product["id"] for item in found):
                    found.append(product)
    return found


def _line(sku, qty, product, reason):
    return {
        "sku": sku,
        "qty": qty,
        "product_id": product["id"] if product and not reason else False,
        "name": product["name"] if product and not reason else (product["name"] if product else ""),
        "reason": reason or "",
    }


def _finish(product, qty, qty_reason):
    if qty_reason:
        return product, None, qty_reason
    if product and product.get("whole") and isinstance(qty, float):
        return product, None, "whole"
    return product, qty, ""


def match_sheet_rows(parsed, products):
    index = index_products(products)
    lines = []
    for item in parsed:
        sku = (item.get("sku") or "").strip()
        if not sku:
            lines.append(_line("", None, None, "missing_sku"))
            continue
        found = _lookup(sku, index)
        qty, qty_reason = parse_quantity(item.get("qty"))
        if len(found) > 1:
            lines.append(_line(sku, None, None, "ambiguous"))
            continue
        product = found[0] if found else None
        if not product:
            lines.append(_line(sku, None, None, "unknown"))
            continue
        product, qty, reason = _finish(product, qty, qty_reason)
        # Keep the product on a bad quantity so the dealer can type a new one.
        lines.append({
            "sku": sku,
            "qty": qty,
            "product_id": product["id"],
            "name": product["name"],
            "reason": reason,
        })
    return lines


def _unknown_code(token):
    key = norm_code(token)
    if len(key) < 4 or len(key) > 40 or key in PDF_STOP:
        return False
    # 120V, 2x120V, and 12/4k/160-50 are ratings in a description, including when a
    # PDF reader puts them on their own line.
    if re.fullmatch(r"\d+V", key) or re.fullmatch(r"\d+X\d+V", key):
        return False
    if "/" in str(token):
        return False
    return any(character.isdigit() for character in key) and any(character.isalpha() for character in key)


def join_positioned_text(snippets, tolerance=3.0):
    """Turn ``(x, y, text)`` pieces into visual rows.

    A PDF reader often returns one cell at a time. Pieces on the same baseline
    belong on one line, so the part number stays with its quantity.
    """
    items = []
    for x, y, text in snippets:
        text = " ".join(str(text or "").split())
        if text:
            items.append((float(x), float(y), text))
    if not items:
        return ""
    items.sort(key=lambda item: (-item[1], item[0]))
    rows = []
    for x, y, text in items:
        if rows and abs(y - rows[-1][0]) <= tolerance:
            rows[-1][1].append((x, text))
        else:
            rows.append([y, [(x, text)]])
    lines = []
    for _y, parts in rows:
        parts.sort()
        lines.append(" ".join(part for _x, part in parts))
    return "\n".join(lines)


def _code_in_token(token, index):
    """A catalog code, including one glued to the description by a PDF reader."""
    key = norm_code(token)
    if not key or key in PDF_STOP:
        return "", []
    if key in index:
        return key, index[key]
    if len(key) < 6:
        return "", []
    best = ""
    found = []
    for candidate, products in index.items():
        if len(candidate) < 6 or candidate not in key or candidate == key:
            continue
        if len(candidate) > len(best):
            best = candidate
            found = list(products)
        elif len(candidate) == best:
            for product in products:
                if all(item["id"] != product["id"] for item in found):
                    found.append(product)
    return best, found


def _classified_tokens(line, index):
    classified = []
    for token in PDF_TOKEN.findall(line):
        key = norm_code(token)
        if not key or key in PDF_STOP:
            continue
        if "," in token:
            classified.append(("qty", token, float(token.replace(",", ""))))
            continue
        code, products = _code_in_token(token, index)
        if code:
            shown = token if norm_code(token) == code else code
            classified.append(("code", shown, products))
        elif re.fullmatch(r"\d+(?:\.\d+)?", token):
            classified.append(("qty", token, float(token)))
        elif _unknown_code(token):
            classified.append(("unknown", token, None))
    return classified


def _span_qty(classified, index):
    """The whole number before the price.

    Printed lines run part, description, quantity, price. Voltages inside the
    description are earlier whole numbers. The price is the first decimal.
    A line with no price and one whole number keeps that number.
    """
    integers = []
    saw_price = False
    for cursor in range(index + 1, len(classified)):
        kind, token, value = classified[cursor]
        if kind == "code":
            break
        if kind != "qty":
            continue
        number, reason = parse_quantity(value)
        if reason:
            continue
        # 1,249.00 is a price even though it is a whole number of dollars.
        if "." in token or "," in token:
            saw_price = True
            break
        integers.append(number)
    if saw_price and integers:
        return integers[-1]
    if not saw_price and len(integers) == 1:
        return integers[0]
    for cursor in range(index - 1, -1, -1):
        kind, _token, value = classified[cursor]
        if kind in ("code", "unknown"):
            break
        if kind != "qty":
            continue
        number, reason = parse_quantity(value)
        if reason or isinstance(number, float):
            continue
        return number
    return None


def match_pdf_text(text, products):
    """Return ``(po_number, lines)`` for text extracted from a PDF."""
    index = index_products(products)
    head = "\n".join((text or "").splitlines()[:40])
    po_number = ""
    for po_match in PDF_PO.finditer(head):
        po_number = _plausible_po(po_match.group(1))
        if po_number:
            break
    lines = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or PDF_PO.search(line):
            continue
        label = norm_label(line)
        if ("qty" in label or "quantity" in label) and ("sku" in label or "part" in label or "item" in label or "material" in label):
            continue
        classified = _classified_tokens(line, index)
        known = any(item[0] == "code" for item in classified)
        for token_index, item in enumerate(classified):
            kind, token, payload = item
            if kind not in ("code", "unknown"):
                continue
            if kind == "unknown" and (known or norm_code(token) == norm_code(po_number)):
                continue
            qty = _span_qty(classified, token_index)
            if kind == "unknown":
                lines.append(_line(token, qty, None, "unknown"))
                continue
            if len(payload) > 1:
                lines.append(_line(token, None, None, "ambiguous"))
                continue
            product, qty, reason = _finish(payload[0], qty, "missing_qty" if qty is None else "")
            lines.append({
                "sku": token,
                "qty": qty,
                "product_id": product["id"],
                "name": product["name"],
                "reason": reason,
            })
            if len(lines) > ROW_LIMIT:
                raise PoParseError("limit")
    return po_number, lines
