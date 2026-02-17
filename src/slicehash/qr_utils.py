"""QR code generation utilities with logo overlay support.

This module provides reusable QR code generation for LNURL-auth and Lightning invoices.
"""

import io
from pathlib import Path
from typing import Optional

import qrcode
from PIL import Image
from quart import Response, current_app, send_file


async def generate_qr_with_logo(
    data: str,
    logo_path: Optional[Path] = None,
    logo_size_ratio: float = 0.2,
    box_size: int = 8,
    border: int = 2,
) -> io.BytesIO:
    """Generate QR code image with optional logo overlay.

    Args:
        data: The data to encode in the QR code (LNURL, invoice, etc.)
        logo_path: Path to logo image file. If None, no logo is added.
        logo_size_ratio: Logo size as ratio of QR code size (default 0.2 = 20%)
        box_size: Size of each QR code box in pixels
        border: Border size in boxes

    Returns:
        BytesIO buffer containing PNG image data
    """
    # Generate QR code
    qr = qrcode.QRCode(
        version=None,  # Auto-select version based on data
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction for logo overlay
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img = img.convert("RGB")  # Convert to RGB for logo overlay

    # Load and embed logo in center if provided
    if logo_path and logo_path.exists():
        logo = Image.open(logo_path)

        # Calculate logo size
        qr_width, qr_height = img.size
        logo_size = int(min(qr_width, qr_height) * logo_size_ratio)
        logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

        # Add white background to logo if it has transparency
        if logo.mode in ("RGBA", "LA"):
            background = Image.new("RGB", logo.size, (255, 255, 255))
            if logo.mode == "RGBA":
                background.paste(logo, mask=logo.split()[3])
            else:
                background.paste(logo, mask=logo.split()[1])
            logo = background

        # Calculate center position and paste logo
        logo_pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
        img.paste(logo, logo_pos)

    # Save to buffer
    img_io = io.BytesIO()
    img.save(img_io, "PNG")
    img_io.seek(0)

    return img_io


async def serve_qr_image(
    data: str, logo_filename: Optional[str] = "favicon-32x32.png"
) -> Response:
    """Helper to generate QR code and return as HTTP response.

    Args:
        data: The data to encode in the QR code
        logo_filename: Filename of logo in static folder, or None for no logo

    Returns:
        Quart Response with PNG image
    """
    logo_path = None
    if logo_filename:
        logo_path = Path(current_app.static_folder) / logo_filename

    img_io = await generate_qr_with_logo(data, logo_path=logo_path)
    return await send_file(img_io, mimetype="image/png")
