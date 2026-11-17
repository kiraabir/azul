"""Wallet pass generation for Apple Wallet and Google Pay."""
import json
import base64
import hashlib
import zipfile
import tempfile
import os
from datetime import datetime, timedelta
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont


class WalletPassGenerator:
    """Generate Apple Wallet passes (PKPass format)."""

    # Colors for wallet passes
    COLOR_DARK = (31, 41, 55)
    COLOR_ACCENT = (0, 166, 233)  # Azure blue for AZUL
    COLOR_LIGHT = (255, 255, 255)

    def __init__(self, merchant_name, merchant_id, api_key):
        self.merchant_name = merchant_name
        self.merchant_id = merchant_id
        self.api_key = api_key

    def generate_pass(self, customer, card):
        """Generate a personalized .pass bundle as bytes."""
        pass_data = self._build_pass_data(customer, card)

        # Build the pass zip in memory
        buf = BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('pass.json', json.dumps(pass_data, indent=2))
            zf.writestr('icon.png', self._default_icon_bytes())
            zf.writestr('strip.png', self._default_strip_bytes())
            zf.writestr('logo.png', self._logo_bytes())
        buf.seek(0)
        return buf.getvalue()

    def _build_pass_data(self, customer, card):
        """Build the pass.json content."""
        relevance_date = self._get_relevance_date()

        return {
            "description": f"{self.merchant_name} Loyalty",
            "formatVersion": 1,
            "kind": "passes",
            "organizationName": "AZUL",
            "backgroundColor": "rgb(255,255,255)",
            "labelColor": "rgb(0,166,233)",
            "foregroundColor": "rgb(31,41,55)",
            "logoText": self.merchant_name,
            "stripColor": "rgb(0,166,233)",
            "serialNumber": str(card.wallet_serial or customer.id),
            "teamIdentifier": self.merchant_id,
            "barcode": {
                "format": "pkpass",
                "message": card.qr_payload,
                "messageEncoding": "utf-8",
                "altText": "Tap to verify"
            },
            "primaryContent": {
                "header": customer.name,
                "body": f"Points: {card.points_balance}",
                "foot": ""
            },
            "secondaryContent": {
                "header": "Reward Progress",
                "body": self._get_progress_text(card.points_balance)
            },
            "relevantDate": relevance_date.isoformat(),
            "locations": self._get_locations()
        }

    def _get_progress_text(self, points):
        """Get progress text showing stamps to next reward."""
        remainder = points % 15
        next_threshold = 15 if remainder == 0 else 15
        return f"{next_threshold - remainder}/15 stamps to reward"

    def _get_relevance_date(self):
        """Calculate relevance date for proximity alerts."""
        # Pass will surface when near the shop (within ~100m)
        return datetime.now() + timedelta(days=365)

    def _get_locations(self):
        """Get location data for proximity alerts."""
        # Default location - merchant can override via settings
        return [
            {
                "latitude": 31.9454,
                "longitude": -8.0143,
                "relevantText": "Nearby"
            }
        ]

    def _default_icon_bytes(self):
        """Generate default icon - will be replaced with actual logo."""
        # Return a small transparent PNG
        return base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )

    def _default_strip_bytes(self):
        """Generate default strip background."""
        return base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
        )

    def _logo_bytes(self):
        """Generate logo placeholder."""
        return self._default_icon_bytes()


class GoogleWalletPassGenerator:
    """Generate Google Pay Wallet passes."""

    def __init__(self, merchant_id, api_key):
        self.merchant_id = merchant_id
        self.api_key = api_key

    def generate_pass(self, customer, card):
        """Generate Google Pay Pass API request payload."""
        return {
            "accountBalance": {
                "amount": card.points_balance,
                "balanceTimeUnit": "unknown",
                "currencyCode": "MAD"  # Morocco local pricing
            },
            "accountName": customer.name,
            "barcode": {
                "type": "qrCode",
                "value": f"azul:card:{card.wallet_serial}",
                "integrityCheck": "SHA256"
            },
            "class": f"azul.loyaltycard.{self.merchant_id}",
            "id": str(card.wallet_serial),
            "objectVersion": 1,
            "passTemplateDetails": {
                "elementTemplate": {
                    "firstRowTemplate": {
                        "columns": [
                            {"columnInfo": {" specifier": "cardholderName"}},
                            {"columnInfo": {" specifier": "pointsBalance"}}
                        ]
                    }
                }
            },
            "localWalletRequest": True,
            "programName": "AZUL Loyalty",
            "relevanceOverride": True,
            "savingTmstr": datetime.now().isoformat(),
            "relevantDate": self._get_relevance_date().isoformat(),
            "locations": self._get_locations()
        }

    def _get_relevance_date(self):
        """Calculate relevance date for proximity alerts."""
        return datetime.now() + timedelta(days=365)

    def _get_locations(self):
        """Get location data for proximity."""
        return [
            {
                "latitude": 31.9454,
                "longitude": -8.0143,
                "relevantText": "Nearby"
            }
        ]


class StyledCardGenerator:
    """Generate styled QR cards for physical counter display."""

    COLOR_DARK = (31, 41, 55)
    COLOR_ACCENT = (0, 166, 233)
    COLOR_LIGHT = (255, 255, 255)
    FINDER_SIZE = 7

    def __init__(self, shop_name="AZUL"):
        self.shop_name = shop_name

    def _load_font(self, size):
        """Try to load a nice font, fall back to default."""
        for name in ("arialbd.ttf", "Arial Bold.ttf", "arial.ttf", "Arial.ttf",
                     "DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    def generate_styled_card(self, customer_name, points_balance, wallet_serial):
        """Generate a styled PNG card image."""
        width, height = 400, 600

        # Create base image
        img = Image.new("RGB", (width, height), self.COLOR_LIGHT)
        draw = ImageDraw.Draw(img)

        # Draw border
        draw.rectangle([0, 0, width-1, height-1], outline=self.COLOR_DARK, width=2)

        # Shop name banner
        draw.rectangle([0, 0, width, 60], fill=self.COLOR_ACCENT)
        font_big = self._load_font(24)
        draw.text((width//2 - 80, 15), "AZUL", fill=self.COLOR_LIGHT, font=font_big)
        draw.text((width//2 - 60, 35), "Loyalty Card", fill=self.COLOR_LIGHT, font=font_big)

        # Customer name
        font_name = self._load_font(18)
        draw.text((20, 80), f"Welcome, {customer_name}", fill=self.COLOR_DARK, font=font_name)

        # Points balance
        font_points = self._load_font(32)
        draw.text((width//2 - 40, 150), f"{points_balance}", fill=self.COLOR_DARK, font=font_points)
        draw.text((width//2 - 20, 185), "points", fill=self.COLOR_DARK, font=self._load_font(12))

        # Wallet serial
        font_serial = self._load_font(10)
        draw.text((20, height - 100), f"Card #{wallet_serial[-8:]}", fill=self.COLOR_DARK, font=font_serial)

        return img


def generate_qr_code(data, size=200):
    """Generate a QR code image for a token."""
    import qrcode
    from PIL import Image

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(
        fill_color=(31, 41, 55),
        back_color=(255, 255, 255),
        mask_pattern=0,
    ).convert("RGB")

    # Resize to desired size
    if img.size[0] != size:
        img = img.resize((size, size), Image.Resampling.LANCZOS)

    return img