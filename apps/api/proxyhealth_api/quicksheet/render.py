"""``render(req) -> bytes`` (BUILD_PLAN §5.0): one-page reportlab PDF with the title only."""

import io
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from proxyhealth_api.contracts.quicksheet import QuickSheetRequest
from proxyhealth_api.settings import DATA_DIR

_FONT_NAME = "NotoSans"
_FONT_FILE = DATA_DIR / "fonts" / "NotoSans-Regular.ttf"


def _font() -> str:
    if _FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return _FONT_NAME
    if Path(_FONT_FILE).is_file():
        pdfmetrics.registerFont(TTFont(_FONT_NAME, str(_FONT_FILE)))
        return _FONT_NAME
    return "Helvetica"


def render(req: QuickSheetRequest) -> bytes:
    """Nothing is stored: the PDF is built in memory and returned."""
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=letter)
    width, height = letter
    font = _font()
    pdf.setTitle(req.title)
    pdf.setFont(font, 20)
    x = width - 54 if req.direction == "rtl" else 54
    if req.direction == "rtl":
        pdf.drawRightString(x, height - 90, req.title)
    else:
        pdf.drawString(x, height - 90, req.title)
    pdf.setFont(font, 9)
    pdf.drawString(54, 40, f"{req.generated_on.isoformat()}  ·  {req.footer[:120]}")
    pdf.showPage()
    pdf.save()
    return buf.getvalue()
