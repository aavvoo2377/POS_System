import os
import sys
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont


def _get_assets_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "assets")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


ASSETS_DIR = _get_assets_dir()
DEFAULT_IMAGE_PATH = os.path.join(ASSETS_DIR, "default_product.png")


def _create_default_image():
    if not os.path.exists(DEFAULT_IMAGE_PATH):
        os.makedirs(ASSETS_DIR, exist_ok=True)
        img = Image.new("RGB", (200, 200), color=(240, 240, 240))
        draw = ImageDraw.Draw(img)
        draw.text((60, 80), "No\nImage", fill=(180, 180, 180))
        img.save(DEFAULT_IMAGE_PATH)


_create_default_image()


def load_image(path, size=(120, 120)):
    try:
        if path and os.path.isfile(path):
            img = Image.open(path).convert("RGBA")
        else:
            img = Image.open(DEFAULT_IMAGE_PATH).convert("RGBA")
    except Exception:
        img = Image.open(DEFAULT_IMAGE_PATH).convert("RGBA")
    img = img.resize(size, Image.LANCZOS)
    return img


CURRENCY_SYM = "\ufdfc"  # ﷼ Saudi Riyal

def format_currency(amount):
    return f"{amount:,.2f}"

def fmt_cur(amount):
    """Format with BiDi-safe Riyal symbol (for GUI + PDF)."""
    return f"\u200E{amount:,.2f}\u200F {CURRENCY_SYM}"


def calculate_vat(amount, vat_rate):
    if vat_rate <= 0:
        return 0
    return amount * vat_rate / (100 + vat_rate)


def get_today_date():
    return datetime.now().strftime("%Y-%m-%d")


def get_current_time():
    return datetime.now().strftime("%H:%M:%S")


def get_current_datetime():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _get_font(size, bold=False):
    from PIL import ImageFont
    # Try bundled Tajawal-Bold first (Arabic-optimised if available)
    bundled_name = "Tajawal-Bold.ttf" if bold else "Tajawal-Regular.ttf"
    try:
        return ImageFont.truetype(os.path.join(ASSETS_DIR, bundled_name), size)
    except Exception:
        pass
    try:
        return ImageFont.truetype(os.path.join(ASSETS_DIR, "arial.ttf"), size)
    except Exception:
        pass
    # Try Windows Fonts
    font_dir = "C:\\Windows\\Fonts"
    style = "BD" if bold else ""
    for name in [
        f"TAJAWAL-{'Bold' if bold else 'Regular'}.ttf",
        f"ARIAL{style}.TTF", f"ARIAL{style}.ttf",
        "SEGOEUIB.TTF" if bold else "SEGOEUI.TTF",
    ]:
        try:
            return ImageFont.truetype(os.path.join(font_dir, name), size)
        except Exception:
            continue
    return ImageFont.load_default()


def _reshape_arabic(text):
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        return text


def generate_barcode_label(code_str, product_name, price, output_path, size=(500, 300)):
    """Generate a customer-friendly label image with name, barcode, and price.

    Size 500x300 gives ~62x37mm at 203 DPI (common thermal printer),
    or ~50x30mm at ~254 DPI (suitable for 50x30mm / 40x30mm labels).

    The layout is computed dynamically from font bounding boxes so that
    every element stays perfectly centred regardless of text length.
    """
    from PIL import Image, ImageDraw
    from barcode.writer import ImageWriter

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    w, h = size
    canvas = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(canvas)

    # ── Generate barcode (internal text OFF — draw manually below) ─
    clean_data = "".join(c for c in str(code_str) if c.isdigit())
    if not clean_data:
        clean_data = "0"
    from barcode import Code128
    bc_img = Code128(clean_data, writer=ImageWriter()).render(
        writer_options={
            "module_width": 0.3,
            "module_height": 12.0,
            "quiet_zone": 8.0,
            "write_text": False,
        }
    )
    bc_img = bc_img.convert("L").point(lambda x: 0 if x < 128 else 255, "1")
    bc_w_native, bc_h_native = bc_img.size

    # ── Cursor-based layout (no overlap, clean stacking) ──────────
    try:
        try:
            font_name = ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", 28)
        except Exception:
            font_name = _get_font(28, bold=True)
        font_sku = _get_font(18, bold=False)
        font_price = _get_font(40, bold=True)

        name_display = _reshape_arabic(product_name)
        sku_display = _reshape_arabic(clean_data)
        price_display = _reshape_arabic(f"السعر: {price:.2f} {CURRENCY_SYM}")

        bb_name = draw.textbbox((0, 0), name_display, font=font_name)
        name_w, name_h = bb_name[2] - bb_name[0], bb_name[3] - bb_name[1]

        bb_sku = draw.textbbox((0, 0), sku_display, font=font_sku)
        sku_w, sku_h = bb_sku[2] - bb_sku[0], bb_sku[3] - bb_sku[1]

        bb_price = draw.textbbox((0, 0), price_display, font=font_price)
        price_w, price_h = bb_price[2] - bb_price[0], bb_price[3] - bb_price[1]

        y_cursor = 12

        # 1. Product name
        draw.text(((w - name_w) // 2, y_cursor), name_display,
                  fill="black", font=font_name)

        # 2. Safe gap before barcode
        y_cursor += 45

        # 3. Paste barcode image (keep exact generation logic)
        bc_x = (w - bc_w_native) // 2
        canvas.paste(bc_img, (bc_x, y_cursor))

        # 4. Advance past barcode height
        y_cursor += bc_h_native + 8

        # 5. SKU digits
        draw.text(((w - sku_w) // 2, y_cursor), sku_display,
                  fill="black", font=font_sku)
        y_cursor += sku_h + 4

        # 6. Price
        draw.text(((w - price_w) // 2, y_cursor), price_display,
                  fill="black", font=font_price)

    except Exception:
        pass

    canvas.save(output_path, "PNG")


def print_label_image(image_path, printer_name=None):
    """Print a label image via the Windows printer driver (win32ui + PIL).

    Accepts a file path or a PIL Image object. Works with any label printer
    that has a Windows driver installed (Xprinter, Zebra, Star, etc.).
    The image is converted to 1-bit monochrome with no dither,
    preserving the exact binary shape of every bar and space.

    The printer driver must already have the correct label size configured
    (e.g. 50x30mm). This function does not alter image dimensions.
    """
    import win32ui
    import win32print
    from PIL import ImageWin

    if isinstance(image_path, Image.Image):
        img = image_path.convert("1", dither=Image.Dither.NONE)
    else:
        img = Image.open(image_path).convert("1", dither=Image.Dither.NONE)
    iw, ih = img.size

    try:
        dc = win32ui.CreateDC()
        dc.CreatePrinterDC(printer_name or win32print.GetDefaultPrinter())
        dc.StartDoc("barcode_label")
        dc.StartPage()
        dib = ImageWin.Dib(img)
        dib.draw(dc.GetHandleOutput(), (0, 0, iw, ih))
        dc.EndPage()
        dc.EndDoc()
        dc.DeleteDC()
    except Exception:
        return False
    return True


def print_label_escpos(image_path, printer_name=None):
    """Send a label bitmap directly to an ESC/POS thermal printer queue.

    Converts the PIL image to ESC/POS raster format (GS v 0) and writes it
    directly to the printer via ``win32print.WritePrinter`` without going
    through the Windows driver.  This is useful when the printer has no
    dedicated Windows driver or when you need to bypass driver scaling.

    Compatible printers: Xprinter XP-365B, XP-420B, Star TSP143, and any
    ESC/POS thermal printer that supports the GS v 0 raster graphics command.
    """
    import win32print

    if isinstance(image_path, Image.Image):
        img = image_path.convert("1", dither=Image.Dither.NONE)
    else:
        img = Image.open(image_path).convert("1", dither=Image.Dither.NONE)
    iw, ih = img.size

    # --- build ESC/POS raster bitmap (GS v 0) ---
    # Raster format: each row is padded to a multiple of 8 bits
    row_bytes = (iw + 7) // 8
    data = bytearray()
    data.extend([0x1B, 0x40])                     # Initialize printer
    data.extend([0x1D, 0x76, 0x30, 0x00])        # GS v 0 (normal)
    data.extend([row_bytes & 0xFF, (row_bytes >> 8) & 0xFF])   # width in bytes
    data.extend([ih & 0xFF, (ih >> 8) & 0xFF])                 # height in dots

    pixels = img.load()
    for y in range(ih):
        for xb in range(row_bytes):
            byte_val = 0
            for b in range(8):
                bit = 7 - b
                x = xb * 8 + bit
                if x < iw:
                    # pixel is black if value == 0 in a "1" mode image
                    if pixels[x, y] == 0:
                        byte_val |= (1 << b)
            data.append(byte_val)

    data.extend([0x1D, 0x56, 0x00])               # Cut paper

    try:
        hprinter = win32print.OpenPrinter(printer_name or win32print.GetDefaultPrinter())
        try:
            win32print.StartDocPrinter(hprinter, 1, ("barcode_label", None, "RAW"))
            win32print.StartPagePrinter(hprinter)
            win32print.WritePrinter(hprinter, bytes(data))
            win32print.EndPagePrinter(hprinter)
            win32print.EndDocPrinter(hprinter)
        finally:
            win32print.ClosePrinter(hprinter)
    except Exception:
        return False
    return True


def set_window_icon(window):
    """Set the program icon on a CTkToplevel or CTk window."""
    search = []
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        meipass = getattr(sys, "_MEIPASS", "")
        search = [
            os.path.join(exe_dir, "icon.ico"),
            os.path.join(exe_dir, "icon.png"),
            os.path.join(meipass, "icon.ico"),
            os.path.join(meipass, "icon.png"),
        ]
    else:
        root = os.path.dirname(os.path.abspath(__file__))
        search = [
            os.path.join(root, "icon.ico"),
            os.path.join(root, "icon.png"),
        ]
    for path in search:
        if os.path.isfile(path):
            try:
                if path.endswith(".ico"):
                    window.iconbitmap(path)
                    try:
                        window.iconbitmap(default=path)
                    except Exception:
                        pass
                else:
                    from tkinter import PhotoImage
                    img = PhotoImage(file=path)
                    window.iconphoto(True, img)
                    try:
                        window.iconphoto(True, default=img)
                    except Exception:
                        pass
                return
            except Exception:
                continue


def open_cash_drawer():
    """Send ESC/POS cash drawer kick command to default printer."""
    try:
        import win32print
        printer = win32print.OpenPrinter(win32print.GetDefaultPrinter())
        try:
            win32print.StartDocPrinter(printer, 1, ("cashdrawer", None, "RAW"))
            win32print.StartPagePrinter(printer)
            # ESC/POS command: ESC p 0 25 250
            win32print.WritePrinter(printer, b"\x1b\x70\x00\x19\xfa")
            win32print.EndPagePrinter(printer)
            win32print.EndDocPrinter(printer)
        finally:
            win32print.ClosePrinter(printer)
        return True
    except Exception:
        return False
