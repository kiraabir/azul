"""QR code generation for AZUL loyalty cards."""
import io
import os

import qrcode
from PIL import Image, ImageDraw, ImageFont

from .models import LoyaltyCard, ShopSetting

QR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "qr")

COLOR_DARK = (31, 41, 55)
# Azure blue for AZUL. Deliberately dark (luminance ~113 vs white 255 =>
# ~4.5:1 contrast) so the finder patterns stay scannable by phone cameras.
COLOR_ACCENT = (0, 166, 233)
COLOR_LIGHT = (255, 255, 255)
FINDER_SIZE = 7


def _load_font(size):
    for name in ("arialbd.ttf", "Arial Bold.ttf", "arial.ttf", "Arial.ttf",
                 "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _build_qr_image(card: LoyaltyCard):
    """Build the styled QR image (finder patterns + bottom label)."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(card.qr_payload)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color=COLOR_DARK,
        back_color=COLOR_LIGHT,
        mask_pattern=0,
    ).convert("RGB")

    _paint_finder_patterns(img, qr.modules)
    return _overlay_label(img, card)


def _paint_finder_patterns(img, modules):
    """Recolor the three 7x7 corner finder patterns to the accent color."""
    size = img.size[0]
    box = size // len(modules)
    draw = ImageDraw.Draw(img)

    corners = [(0, 0), (0, len(modules) - FINDER_SIZE),
               (len(modules) - FINDER_SIZE, len(modules) - FINDER_SIZE)]
    for r0, c0 in corners:
        for r in range(FINDER_SIZE):
            for c in range(FINDER_SIZE):
                if modules[r0 + r][c0 + c]:
                    x = (c0 + c) * box
                    y = (r0 + r) * box
                    draw.rectangle([x, y, x + box - 1, y + box - 1],
                                   fill=COLOR_ACCENT)


def _overlay_label(img, card):
    """Add a bottom label strip with the shop name and card details."""
    pad = 12
    label_h = 64
    new = Image.new("RGB", (img.size[0], img.size[1] + label_h), COLOR_LIGHT)
    new.paste(img, (0, 0))

    draw = ImageDraw.Draw(new)
    shop_name = ShopSetting.get("shop_name", "AZUL")
    font_big = _load_font(20)
    font_small = _load_font(14)

    y0 = img.size[1]
    draw.text((pad, y0 + 6), shop_name, fill=COLOR_DARK, font=font_big)
    draw.text((pad, y0 + 30), f"Points {card.points_balance}",
              fill=COLOR_DARK, font=font_small)
    serial = card.wallet_serial or ""
    draw.text((img.size[0] - pad - 150, y0 + 30), f"#{serial[-8:]}",
              fill=(100, 100, 100), font=font_small)
    return new


def generate_card_qr(card: LoyaltyCard, output_path=None):
    """Generate a styled QR code image for a loyalty card.

    The QR payload is the opaque token, not the visible card number, so a
    card can't be cloned from a photo of the number.
    """
    img = _build_qr_image(card)
    if output_path is None:
        os.makedirs(QR_DIR, exist_ok=True)
        output_path = os.path.join(QR_DIR, f"card_{card.id}.png")
    img.save(output_path)
    return output_path


def qr_bytes(card: LoyaltyCard):
    """Return the PNG bytes for a card's QR code (for embedding in HTML)."""
    buf = io.BytesIO()
    _build_qr_image(card).save(buf, format="PNG")
    return buf.getvalue()


def _shop_name():
    """Read the current shop name, falling back to AZUL."""
    return ShopSetting.get("shop_name", "AZUL") or "AZUL"


def generate_card_image(card: LoyaltyCard):
    """Generate a styled loyalty card graphic with customer name, points
    balance and wallet serial."""
    width, height = 400, 600
    img = Image.new("RGB", (width, height), COLOR_LIGHT)
    draw = ImageDraw.Draw(img)

    # Outer border
    draw.rectangle([0, 0, width - 1, height - 1], outline=COLOR_DARK, width=2)

    # Shop name banner
    draw.rectangle([0, 0, width, 60], fill=COLOR_ACCENT)
    font_big = _load_font(24)
    draw.text((width // 2 - 55, 15), _shop_name(), fill=COLOR_LIGHT, font=font_big)
    draw.text((width // 2 - 60, 35), "Loyalty Card", fill=COLOR_LIGHT, font=font_big)

    # Customer name
    customer_name = ""
    if card.customer is not None:
        customer_name = card.customer.name
    font_name = _load_font(18)
    draw.text((20, 80), f"Welcome, {customer_name}", fill=COLOR_DARK, font=font_name)

    # Points balance
    font_points = _load_font(32)
    draw.text((width // 2 - 40, 150), f"{card.points_balance}",
              fill=COLOR_DARK, font=font_points)
    draw.text((width // 2 - 20, 185), "points", fill=COLOR_DARK, font=_load_font(12))

    # Wallet serial
    serial = card.wallet_serial or ""
    font_serial = _load_font(10)
    draw.text((20, height - 100), f"Card #{serial[-8:]}", fill=COLOR_DARK, font=font_serial)

    return img


def generate_wallet_pass_image(card: LoyaltyCard):
    """Generate a wallet pass preview image (Apple Wallet style strip)."""
    width, height = 400, 220
    img = Image.new("RGB", (width, height), COLOR_ACCENT)
    draw = ImageDraw.Draw(img)

    customer_name = ""
    if card.customer is not None:
        customer_name = card.customer.name
    serial = card.wallet_serial or ""

    font_title = _load_font(26)
    font_body = _load_font(16)
    font_small = _load_font(12)

    draw.text((20, 20), _shop_name(), fill=COLOR_LIGHT, font=font_title)
    draw.text((20, 55), "Wallet Pass", fill=COLOR_LIGHT, font=font_body)
    draw.text((20, 90), customer_name, fill=COLOR_LIGHT, font=font_body)
    draw.text((20, 120), f"Points: {card.points_balance}", fill=COLOR_LIGHT, font=font_body)
    draw.text((20, 150), f"Serial: {serial[-12:]}", fill=COLOR_LIGHT, font=font_small)
    draw.text((width - 160, height - 40), "Scan to verify",
              fill=COLOR_LIGHT, font=font_small)

    return img