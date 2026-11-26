"""Read a purchase order without guessing.

Spreadsheets are matched by the heading row. PDF text is matched against
part numbers we already sell. Nothing here calls Odoo or a language model.
"""
import csv
import io
import re

ROW_LIMIT = 500
QTY_LIMIT = 100000

PART_LABELS = (
    "sku",
    "internal reference",
    "product code",
    "product number",
    "part number",
    "part no",
    "manufacturer part",
    "mfr part",
    "mpn",
    "barcode",
    "upc",
    "vendor part number",
    "vendor part",
    "item number",
    "item no",
    "part",
    "item",
)
QTY_LABELS = (
    "quantity",
    "qty",
    "qty ordered",
    "order qty",
    "order quantity",
    "ordered qty",
    "units",
)
PO_LABELS = (
    "po number",
    "purchase order number",
    "customer po number",
    "customer po",
    "purchase order",
    "po no",
    "po",
)
PO_LABEL_SET = set(PO_LABELS)

PDF_STOP = {
    "QTY", "QUANTITY", "SKU", "ITEM", "PART", "TOTAL", "SUBTOTAL", "TAX",
    "SHIPPING", "PRICE", "AMOUNT", "DESCRIPTION", "DATE", "PAGE", "EACH",
    "UNIT", "UNITS", "PO", "NUMBER", "PURCHASE", "ORDER", "CUSTOMER",
    "INVOICE", "USD", "EXT", "EXTENDED", "SHIP", "BILL",
}
PDF_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/\-]*")
PDF_PO = re.compile(
    r"(?<![A-Za-z])(?:customer\s+po|purchase\s+order|p\.?\s*o\.?)\b"
    r"\s*(?:number|no\.?|#)?\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9\-]{1,40})",
    re.IGNORECASE,
)
QTY_TEXT = re.compile(r"-?\d+(?:\.\d+)?")


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


def _pick(labels, ordered):
    positions = {}
    for index, label in enumerate(labels):
        if label and label not in positions:
            positions[label] = index
    for label in ordered:
        if label in positions:
            return positions[label]
    return None


def parse_sheet_rows(rows):
    """Return ``(po_number, [{"sku", "qty"}, ...])`` from cell values."""
    po_number = ""
    header_index = None
    sku_col = qty_col = po_col = None
    for index, row in enumerate(rows[:30]):
        labels = _labels(row)
        part = _pick(labels, PART_LABELS)
        qty = _pick(labels, QTY_LABELS)
        if part is not None and qty is not None:
            header_index = index
            sku_col, qty_col = part, qty
            po_col = _pick(labels, PO_LABELS)
            break
        if not po_number:
            for cell_index, label in enumerate(labels):
                if label in PO_LABEL_SET and cell_index + 1 < len(row):
                    value = cell_text(row[cell_index + 1])
                    if value:
                        po_number = value[:80]
                        break
    if header_index is None:
        raise PoParseError("header")
    parsed = []
    for row in rows[header_index + 1:]:
        if not row or all(cell in (None, "") or (isinstance(cell, str) and not str(cell).strip()) for cell in row):
            continue
        sku = cell_text(row[sku_col]) if sku_col < len(row) else ""
        qty = row[qty_col] if qty_col < len(row) else None
        if po_col is not None and not po_number and po_col < len(row):
            value = cell_text(row[po_col])
            if value:
                po_number = value[:80]
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
        found = index.get(norm_code(sku)) or []
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


def _unknown_code(key):
    if len(key) < 4 or len(key) > 40 or key in PDF_STOP:
        return False
    return any(character.isdigit() for character in key) and any(character.isalpha() for character in key)


def _classified_tokens(line, index):
    classified = []
    for token in PDF_TOKEN.findall(line):
        key = norm_code(token)
        if not key or key in PDF_STOP:
            continue
        if key in index:
            classified.append(("code", token, index[key]))
        elif re.fullmatch(r"\d+(?:\.\d+)?", token):
            classified.append(("qty", token, float(token)))
        elif _unknown_code(key):
            classified.append(("unknown", token, None))
    return classified


def _nearest_qty(classified, index, used):
    """The number after a part number, or the one before it when the line leads with the quantity."""

    def scan(start, stop, step):
        cursor = start
        while cursor != stop:
            kind = classified[cursor][0]
            if kind in ("code", "unknown"):
                return None
            if kind == "qty" and cursor not in used:
                number, reason = parse_quantity(classified[cursor][2])
                if reason:
                    return None
                used.add(cursor)
                return number
            cursor += step
        return None

    found = scan(index + 1, len(classified), 1)
    if found is not None:
        return found
    return scan(index - 1, -1, -1)


def match_pdf_text(text, products):
    """Return ``(po_number, lines)`` for text extracted from a PDF."""
    index = index_products(products)
    head = "\n".join((text or "").splitlines()[:40])
    po_match = PDF_PO.search(head)
    po_number = po_match.group(1).strip(" -")[:80] if po_match else ""
    lines = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or PDF_PO.search(line):
            continue
        label = norm_label(line)
        if ("qty" in label or "quantity" in label) and ("sku" in label or "part" in label or "item" in label):
            continue
        classified = _classified_tokens(line, index)
        used = set()
        for token_index, item in enumerate(classified):
            kind, token, payload = item
            if kind not in ("code", "unknown"):
                continue
            qty = _nearest_qty(classified, token_index, used)
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
