"""
Email parser — KTC and KBank only.

KTC email format  (from: Onlineservice@ktc.co.th):
    Multipart/alternative, both parts base64-encoded UTF-8.
    Plain-text section contains the English block:
        KTC Credit Card Number: X-2437
        Merchant Name:  LINEPAY *PF_LINE MAN
        Amount: 195.00 THB

KBank QR email format  (from: KPLUS@kasikornbank.com):
    Subject: "Result of Bill Payment (Success)"
    Plain text, bilingual (Thai then English).
    English block:
        Transaction Date: 20/03/2026  09:41:28
        Company Name: Moo Hot Head (A/C Name: MS. Ratchita Yodyiam)
        Amount (THB): 69.00

Anything that isn't KTC or KBank is ignored.
"""

import re
import email
import email.message
import logging
from email.header import decode_header
from html.parser import HTMLParser
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sender / subject constants
# ---------------------------------------------------------------------------

KTC_SENDERS    = {"onlineservice@ktc.co.th"}
KBANK_SENDERS  = {"kplus@kasikornbank.com"}

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# KTC
_KTC_MERCHANT_EN = re.compile(
    r"Merchant Name\s*:?\s*&?n?b?s?p?;?\s*(.+?)(?:\.|<|\n|$)", re.IGNORECASE
)
_KTC_MERCHANT_TH = re.compile(
    r"ร้านค้า\s*:?\s*&?n?b?s?p?;?\s*(.+?)(?:<|\n|$)"
)
_KTC_AMOUNT_EN = re.compile(
    r"Amount\s*:?\s*&?n?b?s?p?;?\s*([\d,]+\.?\d*)\s*THB", re.IGNORECASE
)
_KTC_AMOUNT_TH = re.compile(
    r"จำนวน\s*:?\s*&?n?b?s?p?;?\s*([\d,]+\.?\d*)\s*THB", re.IGNORECASE
)
_KTC_CARD = re.compile(
    r"(?:KTC Credit Card Number|หมายเลขบัตรเครดิต KTC)\s*:?\s*(.+?)(?:<|\n|$)",
    re.IGNORECASE,
)

# KBank
_KB_AMOUNT_EN = re.compile(
    r"Amount\s*\(THB\)\s*:\s*([\d,]+\.?\d*)", re.IGNORECASE
)
_KB_AMOUNT_TH = re.compile(
    r"จำนวนเงิน\s*\(บาท\)\s*:\s*([\d,]+\.?\d*)"
)
_KB_COMPANY_EN = re.compile(
    r"Company Name\s*:\s*(.+?)(?:\s*\(A/C Name:\s*(.+?)\))?\s*(?:\n|$)",
    re.IGNORECASE,
)
_KB_COMPANY_TH = re.compile(
    r"เพื่อเข้าบัญชีบริษัท\s*:\s*(.+?)(?:\n|$)"
)
_KB_DATE_EN = re.compile(
    r"Transaction Date\s*:\s*(.+?)(?:\n|$)", re.IGNORECASE
)

# Person-name indicators (triggers clarification for KBank)
_PERSON_RE = re.compile(
    r"\b(MR\.|MS\.|MRS\.|นาย|นาง|นางสาว)\b", re.IGNORECASE
)

# Digital / subscription-like merchant indicators (triggers subscription check for KTC)
_DIGITAL_MERCHANT_RE = re.compile(
    r"\b(LINE|NETFLIX|SPOTIFY|APPLE|GOOGLE|YOUTUBE|MICROSOFT|ADOBE|AMAZON|"
    r"GRAB|SHOPEE|LAZADA|STEAM|DISCORD|TWITCH|DROPBOX|NOTION|FIGMA|CANVA|"
    r"GITHUB|OPENAI|ANTHROPIC|CHATGPT|CLAUDE|META|FACEBOOK|INSTAGRAM|"
    r"TIKTOK|TWITTER|LINKEDIN|ZOOM|SLACK|TEAMS|PAYPAL|"
    r"LINEPAY|LINE\s*PAY|TRUEMONEY|RABBIT|AIRPAY|"
    r"ICLOUD|APPSTORE|APP\s*STORE|PLAYSTORE|PLAY\s*STORE|"
    r"DISNEY|HBO|PRIMEVIDEO|PRIME\s*VIDEO|CRUNCHYROLL|"
    r"OFFICE\s*365|OFFICE365|GSUITE|GOOGLE\s*ONE|"
    r"CANVA|GRAMMARLY|LASTPASS|DASHLANE|NORDVPN|EXPRESSVPN)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self.chunks.append(data)

    def get_text(self) -> str:
        return " ".join(self.chunks)


def _strip_html(html: str) -> str:
    import html as html_lib
    s = _HTMLStripper()
    s.feed(html)
    text = s.get_text()
    return html_lib.unescape(text)


def _decode_header_value(val: str) -> str:
    parts = decode_header(val or "")
    result = []
    for chunk, enc in parts:
        if isinstance(chunk, bytes):
            result.append(chunk.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(chunk)
    return "".join(result)


_HTML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")


def _normalise(text: str) -> str:
    """Strip HTML if present, unescape entities, collapse whitespace."""
    import html as html_lib
    if _HTML_TAG_RE.search(text):
        text = _strip_html(text)
    text = html_lib.unescape(text)
    # Replace non-breaking spaces and other whitespace variants
    text = text.replace("\xa0", " ").replace("\u200b", "")
    return text


def _get_body(msg: email.message.Message) -> str:
    """Return the best plain-text representation of an email body."""
    html_fallback = None

    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = payload.decode("utf-8", errors="replace")
            if ct == "text/plain":
                return _normalise(text)
            if ct == "text/html":
                html_fallback = _normalise(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            text = payload.decode("utf-8", errors="replace")
            return _normalise(text)

    return html_fallback or ""


def _parse_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def _clean(s: str) -> str:
    """Strip regular + non-breaking whitespace from a extracted value."""
    return s.strip().strip("\xa0").strip()


# ---------------------------------------------------------------------------
# Type detection
# ---------------------------------------------------------------------------

def is_ktc(sender: str, _subject: str = "") -> bool:
    return sender.lower().strip("<>").split()[-1].strip("<>") in KTC_SENDERS


def is_kbank(sender: str, _subject: str = "") -> bool:
    return sender.lower().strip("<>").split()[-1].strip("<>") in KBANK_SENDERS



# ---------------------------------------------------------------------------
# KTC parser
# ---------------------------------------------------------------------------

def parse_ktc(raw: bytes) -> dict | None:
    msg = email.message_from_bytes(raw)
    body = _get_body(msg)

    m_merchant = _KTC_MERCHANT_EN.search(body) or _KTC_MERCHANT_TH.search(body)
    m_amount   = _KTC_AMOUNT_EN.search(body)   or _KTC_AMOUNT_TH.search(body)

    if not m_merchant or not m_amount:
        logger.warning("KTC: could not extract merchant/amount from body")
        return None

    merchant = _clean(m_merchant.group(1)).rstrip(".")
    amount   = _parse_amount(m_amount.group(1))

    # Check if merchant looks like a digital / subscription service
    is_digital = bool(_DIGITAL_MERCHANT_RE.search(merchant))

    snippet = (
        f"Source: KTC Credit Card\n"
        f"Merchant: {merchant}\n"
        f"Amount: {amount:.2f} THB"
    )
    if is_digital:
        snippet += "\nNote: Merchant looks like a digital service — subscription check needed"

    return {
        "source":              "KTC",
        "merchant":            merchant,
        "amount":              amount,
        "currency":            "THB",
        "snippet":             snippet,
        "raw_text":            body[:600],
        "needs_clarification_hint": is_digital,
        "clarification_type":  "subscription_check" if is_digital else None,
    }


# ---------------------------------------------------------------------------
# KBank parser
# ---------------------------------------------------------------------------

def parse_kbank(raw: bytes) -> dict | None:
    msg = email.message_from_bytes(raw)
    body = _get_body(msg)

    m_amount  = _KB_AMOUNT_EN.search(body) or _KB_AMOUNT_TH.search(body)
    m_company = _KB_COMPANY_EN.search(body) or _KB_COMPANY_TH.search(body)

    if not m_amount or not m_company:
        logger.warning("KBank: could not extract amount/company from body")
        return None

    amount = _parse_amount(m_amount.group(1))

    company_raw = _clean(m_company.group(1))
    ac_name = None
    try:
        ac_name = m_company.group(2).strip() if m_company.lastindex >= 2 else None
    except IndexError:
        pass

    merchant = company_raw
    if ac_name:
        merchant = f"{company_raw} ({ac_name})"

    # Detect person-to-person transfers (QR to individual)
    is_person = bool(_PERSON_RE.search(company_raw + " " + (ac_name or "")))

    snippet = (
        f"Source: KBank QR Payment\n"
        f"Recipient: {merchant}\n"
        f"Amount: {amount:.2f} THB"
    )
    if is_person:
        snippet += "\nNote: Recipient appears to be a person — clarification likely needed"

    return {
        "source":   "KBank",
        "merchant": merchant,
        "amount":   amount,
        "currency": "THB",
        "snippet":  snippet,
        "raw_text": body[:600],
        "needs_clarification_hint": is_person,
    }



# ---------------------------------------------------------------------------
# Main router
# ---------------------------------------------------------------------------

def route(raw: bytes, config: dict = None) -> tuple[str | None, dict | None]:
    """
    Given raw email bytes, detect type and return (type, parsed_dict).
    Only KTC and KBank are tracked — everything else returns (None, None).
    """
    msg    = email.message_from_bytes(raw)
    sender = msg.get("From", "")

    if is_ktc(sender):
        return "KTC", parse_ktc(raw)

    if is_kbank(sender):
        return "KBank", parse_kbank(raw)

    return None, None
