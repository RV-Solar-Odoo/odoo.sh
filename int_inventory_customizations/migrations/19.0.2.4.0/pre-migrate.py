"""Convert the millimetre product dimensions into inches before the mm fields go away.

Shippo only ever read length_in / width_in / height_in, so any product filled in
millimetres was quoting against a fallback parcel. Runs before the ORM drops the
mm fields, while their columns still hold data.
"""

import logging

_logger = logging.getLogger(__name__)

MM_PER_INCH = 25.4
PAIRS = (
    ("length_in", "length_mm"),
    ("width_in", "width_mm"),
    ("height_in", "height_mm"),
)


def _has_column(cr, table, column):
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
        """,
        (table, column),
    )
    return bool(cr.fetchone())


def migrate(cr, version):
    for inch_col, mm_col in PAIRS:
        if not _has_column(cr, "product_template", mm_col):
            continue
        if not _has_column(cr, "product_template", inch_col):
            cr.execute(f'ALTER TABLE product_template ADD COLUMN "{inch_col}" double precision')
        # Never overwrite a value someone already entered in inches. Round so the
        # form shows 24 rather than 24.000000000000004.
        cr.execute(
            f"""
            UPDATE product_template
               SET "{inch_col}" = ROUND(("{mm_col}" / %s)::numeric, 2)::double precision
             WHERE "{mm_col}" IS NOT NULL
               AND "{mm_col}" != 0
               AND COALESCE("{inch_col}", 0) = 0
            """,
            (MM_PER_INCH,),
        )
        _logger.info("Converted %s product(s) from %s to %s.", cr.rowcount, mm_col, inch_col)
