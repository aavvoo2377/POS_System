import json
import os
import sys
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from barcode.writer import ImageWriter
from utils import CURRENCY_SYM

if getattr(sys, "frozen", False):
    CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "POS_System", "config")
else:
    CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
CONFIG_PATH = os.path.join(CONFIG_DIR, "invoice_config.json")

DEFAULT_CONFIG = {
    "font_family": "Arial",
    "font_sizes": {"header": 14, "body": 11, "totals": 14},
    "line_spacing": 1.0,
    "receipt_alignment": "right",
    "separator_char": "-",
    "separator_length": 100,
    "columns": {
        "show_name": True,
        "show_quantity": True,
        "show_price": True,
        "show_vat": False,
        "show_total": True,
        "widths": {"name": 35, "quantity": 20, "price": 20, "vat": 15},
    },
    "header_notes": "",
    "header_notes_alignment": "right",
    "header_notes_bold": False,
    "footer_notes": "",
    "footer_notes_alignment": "right",
    "footer_notes_bold": False,
    "canvas_width": 400,
    "canvas_min_height": 0,  # 0 = auto-calculate from content
    "side_margin": 16,
    "table_offset": 0,
    "open_drawer_on_sale": True,
    "show_barcode": True,
    "barcode_type": "code128",
    "qrcode_size": 200,
    "logo_width": 120,
    "logo_x_offset": 0,
    "logo_path": "",
    "barcode_scale": 1.8,
    "barcode_height": 80,
    "items_bold": False,
    "table_mode": False,
    "show_receipt_border": False,
    "show_separators": True,
    "show_header_notes": True,
    "show_footer_notes": True,
    "print_threshold": 160,
    "show_weight_unit": True,
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _resolve_font(family, size, bold=False):
    """Resolve a font, falling back through guaranteed Arabic-safe fonts."""
    assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
    font_dir = "C:\\Windows\\Fonts"
    candidates = []
    if family == "Tajawal":
        b = "Bold.ttf" if bold else "Regular.ttf"
        candidates.append(os.path.join(assets_dir, f"Tajawal-{b}"))
        candidates.append(os.path.join(font_dir, f"Tajawal-{b}"))
        candidates.append(os.path.join(font_dir, f"TAJAWAL-{b.replace('ttf','TTF')}"))
    elif family == "Courier New":
        fname = "COURBD.TTF" if bold else "COUR.TTF"
        candidates.append(os.path.join(font_dir, fname))
        candidates.append(os.path.join(font_dir, fname.lower()))
    else:
        style = "BD" if bold else ""
        for nm in [f"ARIAL{style}.TTF", f"ARIAL{style}.ttf"]:
            candidates.append(os.path.join(assets_dir, nm))
            candidates.append(os.path.join(font_dir, nm))
        candidates.append(os.path.join(font_dir, "SEGOEUIB.TTF" if bold else "SEGOEUI.TTF"))

    # Arabic-safe fallbacks — these always include Arabic glyphs on Windows
    for safe_pair in [("tahomabd.ttf", "tahoma.ttf"), ("TAHOMABD.TTF", "TAHOMA.TTF")]:
        candidates.append(os.path.join(font_dir, safe_pair[0] if bold else safe_pair[1]))

    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _reshape(text):
    """Reshape Arabic text so Pillow can render it legibly instead of tofu."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def _contains_arabic(text):
    """Return True if *text* contains any Arabic-range character."""
    for ch in text:
        if '\u0600' <= ch <= '\u06FF' or '\u0750' <= ch <= '\u077F' or \
           '\u08A0' <= ch <= '\u08FF' or '\uFB50' <= ch <= '\uFDFF' or \
           '\uFE70' <= ch <= '\uFEFF':
            return True
    return False


# ── Receipt text generation (mirrors invoice_printer logic with config) ──

def _calc_col_widths(chars_wide, config):
    cfg_col = config["columns"]
    col_keys = ["name", "quantity", "price", "vat"]
    visible = [(k, cfg_col["widths"].get(k, 20)) for k in col_keys
               if cfg_col.get(f"show_{k}", k == "name")]
    if cfg_col.get("show_total", True):
        visible.append(("total", cfg_col["widths"].get("total", 20)))
    if not visible:
        visible = [("name", chars_wide)]
    total_w = sum(w for _, w in visible)
    avail = chars_wide - 4 * max(len(visible) - 1, 0)
    out = {}
    for k, w in visible:
        out[k] = max(2, int(avail * w / total_w))
    return out


def _generate_receipt_lines(config, shop_info, items, invoice_number, total):
    w = int(shop_info.get("receipt_width", 58))
    if w >= 80:
        chars = 44
    elif w >= 58:
        chars = 36
    else:
        chars = 28

    col_w = _calc_col_widths(chars, config)
    master_align = config.get("receipt_alignment", "right")
    sep_char = (config.get("separator_char", "-") or "-")[0]
    sep_len_pct = max(10, min(100, int(config.get("separator_length", 100))))
    sep_len = max(1, int(chars * sep_len_pct / 100))
    sep = sep_char * sep_len
    eq = "=" * sep_len
    ls = float(config.get("line_spacing", 1.0))
    fs = config["font_sizes"]
    col_show = config["columns"]

    lines = []  # each item: (text, font_key, bold, alignment)

    def add(text, font_key="body", bold=False, alignment=None):
        lines.append((text, font_key, bold, alignment or master_align))

    # Header
    shop_name = shop_info.get("shop_name", "")
    if shop_name:
        add(shop_name, "header", bold=True, alignment="center")
    phone = shop_info.get("shop_phone", "")
    if phone:
        add(f"تلفون: {phone}", "body", alignment="center")
    tax = shop_info.get("shop_tax_number", "")
    if shop_info.get("vat_enabled", "1") == "1" and tax:
        add(f"الرقم الضريبي: {tax}", "body", alignment="center")

    # Header notes
    hn = config.get("header_notes", "").strip()
    if hn:
        add("", "body")
        for line in hn.split("\n"):
            add(line.strip(), "notes",
                bold=config.get("header_notes_bold", False),
                alignment=config.get("header_notes_alignment", "right"))

    add(sep, "body")

    # Invoice info
    add(f"الفاتورة: {invoice_number}", "body")
    add(f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "body")

    # Column headers
    col_labels = {"name": "الصنف", "quantity": "الكمية",
                  "price": "السعر", "vat": "الضريبة", "total": "الإجمالي"}
    col_keys = [k for k in ("name", "quantity", "price", "vat", "total")
                if k != "total" and col_show.get(f"show_{k}", k == "name")
                or k == "total" and col_show.get("show_total", True)]
    header_parts = []
    for k in col_keys:
        header_parts.append((col_labels.get(k, k), col_w.get(k, 10)))
    add("  ".join(f"{label:>{wr}}" for label, wr in header_parts), "body")

    # Items
    items_are_bold = config.get("items_bold", False)
    vat_rate_rows = float(shop_info.get("vat_rate", 15)) if shop_info.get("vat_enabled", "1") == "1" else 0
    for item in items:
        parts = []
        for k in col_keys:
            if k == "name":
                parts.append((item.get("product_name", "")[:col_w.get(k, 10)], col_w.get(k, 10)))
            elif k == "quantity":
                qty = f"{item.get('quantity', 0):.2f}"
                if config.get("show_weight_unit", True):
                    qty += " kg"
                parts.append((qty, col_w.get(k, 6)))
            elif k == "price":
                parts.append((f"{item.get('price_per_kg', item.get('price', 0)):,.2f}", col_w.get(k, 6)))
            elif k == "vat":
                t = item.get("total", 0)
                v = t - (t / (1 + vat_rate_rows / 100))
                parts.append((f"{v:,.2f}", col_w.get(k, 6)))
            elif k == "total":
                parts.append((f"{item.get('total', 0):,.2f}", col_w.get(k, 6)))
        add("  ".join(f"{p:>{wr}}" for p, wr in parts), "body", bold=items_are_bold)

    add(sep, "body")

    # Totals
    vat_enabled = shop_info.get("vat_enabled", "1") == "1"
    vat_rate = float(shop_info.get("vat_rate", 15)) if vat_enabled else 0
    vat_amount = total - (total / (1 + vat_rate / 100))
    subtotal = total - vat_amount

    def total_line(label, amount):
        return f"{label} {amount:>6}".rjust(chars)

    if vat_enabled:
        add(total_line("المجموع الخاضع للضريبة:", subtotal), "totals")
        add(total_line(f"ضريبة القيمة المضافة ({vat_rate:.0f}%):", vat_amount), "totals")
        add(f"{'الإجمالي شامل الضريبة:':>{chars-8}} {total:>6,.2f} {CURRENCY_SYM}".rjust(chars), "totals", bold=True)
    else:
        add(f"{'الإجمالي:':>{chars-8}} {total:>6,.2f} {CURRENCY_SYM}".rjust(chars), "totals", bold=True)

    add(eq, "body")

    # Footer notes
    fn = config.get("footer_notes", "").strip()
    if fn:
        for line in fn.split("\n"):
            add(line.strip(), "notes",
                bold=config.get("footer_notes_bold", False),
                alignment=config.get("footer_notes_alignment", "right"))

    add("شكراً لتسوقكم", "header", alignment="center")

    return lines, chars, ls, fs


# ── Preview rendering (Pillow) ──

STUDIO_BG = "#EAE6DF"      # warm sand/earth tone simulating a design desk
PAPER_FILL = "#FFFFFF"
PAPER_BORDER = "#C8C8C8"
PAPER_GAP = 4               # px gap between studio bg edge and paper roll


def _build_column_layout(canvas_width, side_margin, config):
    """Return (col_keys, col_centers_dict, content_left, usable_w).

    Columns are mapped in traditional RTL order so that the BiDi rendering
    algorithm (which mirrors horizontal positioning for Arabic runs) produces
    the correct receipt layout:

        Pixel X≈margin ← الإجمالي | الضريبة | السعر | الكمية | الصنف → X≈cw-margin
        Visual RTL    → Total       VAT      Price    Qty      Name
    """
    col_cfg = config["columns"]
    widths_pct = col_cfg.get("widths", {})
    col_keys = [k for k in ("name", "quantity", "price", "vat", "total")
                if k != "total" and col_cfg.get(f"show_{k}", k == "name")
                or k == "total" and col_cfg.get("show_total", True)]
    visible_pct = sum(widths_pct.get(k, 20) for k in col_keys)
    content_left = PAPER_GAP + side_margin
    content_right = canvas_width - PAPER_GAP - side_margin
    usable_w = max(50, content_right - content_left)
    centers = {}
    # Iterate reversed (total → name) so physical coordinates place الإجمالي
    # at the left edge and الصّنف at the right edge.  The BiDi engine's
    # right-edge anchor then flips them visually to the correct RTL order.
    x = content_left
    for k in reversed(col_keys):
        w = max(20, int(usable_w * widths_pct.get(k, 20) / max(1, visible_pct)))
        centers[k] = x + w // 2
        x += w
    return col_keys, centers, content_left, usable_w


def generate_barcode_image_1x(config, invoice_number, cw, margin):
    """Generate a razor-sharp Code128 barcode at 1x (final) resolution.
    Returns (PIL.Image, height_in_px) or (None, 0) on failure.
    """
    show_bc = config.get("show_barcode", True)
    bc_type = config.get("barcode_type", "code128")
    if not show_bc:
        return None, 0
    try:
        if bc_type == "qrcode":
            import qrcode as _qr
            qr = _qr.QRCode(box_size=10, border=2)
            qr.add_data(invoice_number or "1234")
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            qr_img = qr_img.convert("RGBA")
            qr_size = int(config.get("qrcode_size", 200))
            qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
            max_bc_w = cw - margin * 2
            if qr_size > max_bc_w:
                ratio = max_bc_w / qr_size
                new_sz = int(qr_size * ratio)
                qr_img = qr_img.resize((new_sz, new_sz), Image.NEAREST)
                return qr_img, new_sz
            return qr_img, qr_size
        else:
            clean_data = "".join(c for c in str(invoice_number or "1234") if c.isdigit())
            if not clean_data:
                clean_data = "0"
            from barcode import Code128
            bc_img = Code128(clean_data, writer=ImageWriter()).render(
                writer_options={
                    "module_width": 0.25,
                    "module_height": 12.0,
                    "quiet_zone": 6.0,
                    "write_text": True,
                    "font_size": 9,
                    "text_distance": 3.0,
                }
            )
            bc_img = bc_img.convert("L").point(lambda x: 0 if x < 128 else 255, "1")
            return bc_img, bc_img.height
    except Exception as e:
        print(f"Barcode error: {e}")
        return None, 0


def render_invoice_preview(config, shop_info,
                           sample_items=None,
                           canvas_width=None,
                           invoice_number=None,
                           invoice_total=None,
                           skip_barcode=False):
    if sample_items is None:
        sample_items = [
            {"product_name": "جزر بلدي", "quantity": 2.00, "price": 4.50, "total": 9.00},
            {"product_name": "تفاح أحمر", "quantity": 1.50, "price": 12.00, "total": 18.00},
            {"product_name": "موز مستورد", "quantity": 3.00, "price": 7.50, "total": 22.50},
            {"product_name": "عنب أسود", "quantity": 0.75, "price": 15.00, "total": 11.25},
        ]
    total = invoice_total if invoice_total is not None else sum(it["total"] for it in sample_items)

    family = config.get("font_family", "Arial")
    fs = config["font_sizes"]
    ls = float(config.get("line_spacing", 1.0))
    line_gap = 4
    cw = canvas_width or int(config.get("canvas_width", 400))
    margin = int(config.get("side_margin", 16))
    min_h = max(400, int(config.get("canvas_min_height", 0)))

    col_labels = {"name": "الصنف", "quantity": "الكمية",
                  "price": "السعر", "vat": "الضريبة", "total": "الإجمالي"}
    col_keys, col_centers, content_left, usable_w = _build_column_layout(cw, margin, config)

    # ── Build structured preview lines ──────────────────────
    # entry: (text_or_cols, font_key, bold, alignment, is_table)
    #   is_table=True  → text_or_cols is a dict {col_key: str_value}
    #   is_table=False → text_or_cols is a plain str

    lines_buf = []

    def add_line(text, font_key="body", bold=False, alignment=None, col_data=None):
        is_table = col_data is not None
        align = alignment or config.get("receipt_alignment", "right")
        lines_buf.append((text if not is_table else col_data, font_key, bold, align, is_table))

    # Header
    shop_name = shop_info.get("shop_name", "")
    if shop_name:
        add_line(shop_name, "header", bold=True, alignment="center")
    phone = shop_info.get("shop_phone", "")
    if phone:
        add_line(f"تلفون: {phone}", "body", alignment="center")
    tax = shop_info.get("shop_tax_number", "")
    if shop_info.get("vat_enabled", "1") == "1" and tax:
        add_line(f"الرقم الضريبي: {tax}", "body", alignment="center")

    # Header notes
    show_hn = config.get("show_header_notes", True)
    hn = config.get("header_notes", "").strip()
    if show_hn and hn:
        add_line("", "body")
        for ln in hn.split("\n"):
            add_line(ln.strip(), "header",
                     bold=config.get("header_notes_bold", False),
                     alignment=config.get("header_notes_alignment", "center"))

    # Separator
    show_sep = config.get("show_separators", True)
    if show_sep:
        _append_sep(lines_buf, add_line, config, usable_w, fs, family)

    # Invoice info
    inv_no = invoice_number or "1234"
    add_line(f"الفاتورة: {inv_no}", "body")
    add_line(f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}", "body")

    # ── Table header ──
    add_line("", "body", col_data={k: col_labels.get(k, k) for k in col_keys})

    # ── Table rows ──
    items_are_bold = config.get("items_bold", False)
    vat_enabled_rows = shop_info.get("vat_enabled", "1") == "1"
    vat_rate = float(shop_info.get("vat_rate", 15)) if vat_enabled_rows else 0
    for item in sample_items:
        row = {}
        for k in col_keys:
            if k == "name":
                row[k] = item.get("product_name", "")
            elif k == "quantity":
                qty = f"{item.get('quantity', 0):.2f}"
                if config.get("show_weight_unit", True):
                    qty += " kg"
                row[k] = qty
            elif k == "price":
                row[k] = f"{item.get('price_per_kg', item.get('price', 0)):,.2f}"
            elif k == "vat":
                t = item.get("total", 0)
                v = t - (t / (1 + vat_rate / 100))
                row[k] = f"{v:,.2f}"
            elif k == "total":
                row[k] = f"{item.get('total', 0):,.2f}"
        add_line("", "body", col_data=row, bold=items_are_bold)

    # ── Totals section ──
    if show_sep:
        _append_sep(lines_buf, add_line, config, usable_w, fs, family)

    vat_enabled = shop_info.get("vat_enabled", "1") == "1"
    vat_rate_eff = float(shop_info.get("vat_rate", 15)) if vat_enabled else 0
    vat_amount = total - (total / (1 + vat_rate_eff / 100))
    subtotal = total - vat_amount

    if vat_enabled:
        add_line(f"المجموع الخاضع للضريبة:  {subtotal:,.2f}",
                 "totals", alignment="center")
        add_line(f"ضريبة القيمة المضافة ({vat_rate_eff:.0f}%):  {vat_amount:,.2f}",
                 "totals", alignment="center")
        add_line(f"الإجمالي شامل الضريبة:  {total:,.2f} {CURRENCY_SYM}",
                 "totals", bold=True, alignment="center")
    else:
        add_line(f"الإجمالي:  {total:,.2f} {CURRENCY_SYM}",
                 "totals", bold=True, alignment="center")

    if show_sep:
        eq_len = max(1, int(usable_w / max(6, fs.get("body", 11)) * config.get("separator_length", 100) / 100))
        eq_char = (config.get("separator_char", "-") or "-")[0]
        add_line("=" * eq_len, "body")

    # Footer notes
    show_fn = config.get("show_footer_notes", True)
    fn = config.get("footer_notes", "").strip()
    if show_fn and fn:
        for ln in fn.split("\n"):
            add_line(ln.strip(), "header",
                     bold=config.get("footer_notes_bold", False),
                     alignment=config.get("footer_notes_alignment", "center"))

    add_line("شكراً لتسوقكم", "header", alignment="center")

    # ── Compute line heights ────────────────────────────────
    line_heights = []
    for item, font_key, bold, alignment, is_table in lines_buf:
        fsize = fs.get(font_key, fs["body"])
        use_font = _resolve_font(family, fsize, bold)
        bbox = use_font.getbbox("Agh") if hasattr(use_font, "getbbox") else None
        fh = (bbox[3] - bbox[1]) if bbox else fsize
        lh = int(fh * ls + line_gap)
        line_heights.append((lh, use_font))

    text_h = sum(lh for lh, _ in line_heights)

    # ── Logo ────────────────────────────────────────────────
    logo_img = None
    logo_h = 0
    logo_w_actual = 0
    logo_path = config.get("logo_path", "") or shop_info.get("report_logo", "")
    logo_cfg_w = int(config.get("logo_width", 120))
    logo_offset = int(config.get("logo_x_offset", 0))
    if logo_path and os.path.isfile(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            aspect = logo_img.height / logo_img.width if logo_img.width else 1
            logo_w_actual = min(logo_cfg_w, cw - PAPER_GAP * 2 - margin * 2)
            logo_h = int(logo_w_actual * aspect)
            logo_img = logo_img.resize((logo_w_actual, logo_h), Image.LANCZOS)
        except Exception:
            logo_img = None

    # ── Barcode / QR Code ────────────────────────────────────
    barcode_img = None
    bc_h = 0
    show_bc = config.get("show_barcode", True) and not skip_barcode
    bc_type = config.get("barcode_type", "code128")
    if show_bc and not skip_barcode:
        try:
            if bc_type == "qrcode":
                import qrcode as _qr
                qr = _qr.QRCode(box_size=10, border=2)
                qr.add_data(invoice_number or "1234")
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                qr_img = qr_img.convert("RGBA")
                qr_size = int(config.get("qrcode_size", 200))
                qr_img = qr_img.resize((qr_size, qr_size), Image.NEAREST)
                max_bc_w = cw - PAPER_GAP * 2 - margin * 2
                if qr_size > max_bc_w:
                    ratio = max_bc_w / qr_size
                    new_sz = int(qr_size * ratio)
                    qr_img = qr_img.resize((new_sz, new_sz), Image.NEAREST)
                    bc_h = new_sz
                else:
                    bc_h = qr_size
                barcode_img = qr_img
            else:
                clean_data = "".join(c for c in str(invoice_number or "1234") if c.isdigit())
                if not clean_data:
                    clean_data = "0"
                from barcode import Code128
                barcode_img = Code128(clean_data, writer=ImageWriter()).render(
                    writer_options={
                        "module_width": 0.25,
                        "module_height": 12.0,
                        "quiet_zone": 6.0,
                        "write_text": True,
                        "font_size": 9,
                        "text_distance": 3.0,
                    }
                )
                barcode_img = barcode_img.convert("L").point(lambda x: 0 if x < 128 else 255, "1")
                bc_h = barcode_img.height
            bc_h += 10  # padding after barcode
        except Exception:
            barcode_img = None

    total_text_h = text_h + margin
    top_extra = logo_h + 12 if logo_img else 0  # logo + gap after it
    bottom_extra = bc_h + 10 if barcode_img else 0
    total_h = max(min_h, PAPER_GAP * 2 + margin + top_extra + total_text_h + bottom_extra)

    # ── Canvas setup ────────────────────────────────────────
    img = Image.new("RGB", (cw, total_h), STUDIO_BG)
    draw = ImageDraw.Draw(img)

    # Draw white paper roll with border (configurable thickness)
    paper_rect = [PAPER_GAP, PAPER_GAP,
                  cw - PAPER_GAP - 1, total_h - PAPER_GAP - 1]
    border_w = 2 if config.get("show_receipt_border", False) else 1
    border_clr = "#222222" if config.get("show_receipt_border", False) else PAPER_BORDER
    draw.rectangle(paper_rect, fill=PAPER_FILL, outline=border_clr, width=border_w)

    y = PAPER_GAP + margin

    # ── Logo at top ─────────────────────────────────────────
    if logo_img:
        center_x = (cw - logo_w_actual) // 2 + logo_offset
        # clamp so logo stays within paper bounds
        max_x = cw - PAPER_GAP - margin - logo_w_actual
        min_x = PAPER_GAP + margin
        center_x = max(min_x, min(center_x, max_x))
        # paste with alpha
        if logo_img.mode == "RGBA":
            paper = img.crop((center_x, y, center_x + logo_w_actual, y + logo_h))
            paper.paste(logo_img, (0, 0), logo_img)
            img.paste(paper, (center_x, y))
        else:
            img.paste(logo_img, (center_x, y))
        y += logo_h + 12

    # ── Table mode: pre-compute column physical boundaries ──
    table_mode_active = config.get("table_mode", False)
    col_left = {}
    col_right = {}
    if table_mode_active:
        widths_pct = config["columns"].get("widths", {})
        visible_pct = sum(widths_pct.get(k, 20) for k in col_keys)
        tx = content_left
        for k in reversed(col_keys):
            tw = max(20, int(usable_w * widths_pct.get(k, 20) / max(1, visible_pct)))
            col_left[k] = tx
            col_right[k] = tx + tw
            tx += tw
        table_left = content_left
        table_right = tx

    # ── Render lines ────────────────────────────────────────
    for i, (item, font_key, bold, alignment, is_table) in enumerate(lines_buf):
        use_font = line_heights[i][1]
        lh = line_heights[i][0]

        if is_table:
            toff = config.get("table_offset", 0)

            if table_mode_active:
                draw.line([(table_left, y), (table_right, y)], fill="#333333", width=1)
                # Vertical column separators + left border
                for k in col_keys:
                    draw.line([(col_right[k], y), (col_right[k], y + lh)], fill="#666666", width=1)
                draw.line([(table_left, y), (table_left, y + lh)], fill="#666666", width=1)

            for k in col_keys:
                txt = item.get(k, "")
                if not txt:
                    continue
                display = _reshape(txt)
                tw = draw.textlength(display, font=use_font)
                if table_mode_active:
                    cx = (col_left[k] + col_right[k]) // 2 + toff
                else:
                    cx = col_centers.get(k, content_left) + toff
                draw.text((cx - tw // 2, y), display, fill="#111111", font=use_font)

            y += lh

            if table_mode_active:
                draw.line([(table_left, y), (table_right, y)], fill="#333333", width=1)
        else:
            text = item
            display = _reshape(text)
            tw = draw.textlength(display, font=use_font)
            if alignment == "center":
                x = (cw - tw) // 2
            elif alignment == "left":
                x = content_left
            else:
                x = cw - PAPER_GAP - margin - tw
            draw.text((x, y), display, fill="#111111", font=use_font)

            y += lh

    # ── Barcode at bottom ────────────────────────────────────
    if barcode_img:
        y += 10
        bc_center_x = (cw - barcode_img.width) // 2
        if barcode_img.mode == "RGBA":
            paper_area = img.crop((bc_center_x, y, bc_center_x + barcode_img.width, y + barcode_img.height))
            paper_area.paste(barcode_img, (0, 0), barcode_img)
            img.paste(paper_area, (bc_center_x, y))
        else:
            img.paste(barcode_img, (bc_center_x, y))

    return img


def render_summary_preview(config, shop_info, summary, title="ملخص المبيعات اليومية",
                           canvas_width=None):
    """Render a daily-sales summary image using the same template config."""
    family = config.get("font_family", "Arial")
    fs = config["font_sizes"]
    ls = float(config.get("line_spacing", 1.0))
    line_gap = 4
    cw = canvas_width or int(config.get("canvas_width", 400))
    margin = int(config.get("side_margin", 16))
    min_h = max(400, int(config.get("canvas_min_height", 0)))

    col_labels = {"name": "الصنف", "quantity": "الكمية",
                  "price": "السعر", "vat": "الضريبة", "total": "الإجمالي"}
    col_keys, col_centers, content_left, usable_w = _build_column_layout(cw, margin, config)

    lines_buf = []
    def add_line(text, font_key="body", bold=False, alignment=None, col_data=None):
        is_table = col_data is not None
        align = alignment or config.get("receipt_alignment", "right")
        lines_buf.append((text if not is_table else col_data, font_key, bold, align, is_table))

    # Header
    shop_name = shop_info.get("shop_name", "")
    if shop_name:
        add_line(shop_name, "header", bold=True, alignment="center")
    phone = shop_info.get("shop_phone", "")
    if phone:
        add_line(f"تلفون: {phone}", "body", alignment="center")
    tax = shop_info.get("shop_tax_number", "")
    if shop_info.get("vat_enabled", "1") == "1" and tax:
        add_line(f"الرقم الضريبي: {tax}", "body", alignment="center")

    show_sep = config.get("show_separators", True)
    if show_sep:
        _append_sep(lines_buf, add_line, config, usable_w, fs, family)
    add_line(title, "header", bold=True, alignment="center")
    if show_sep:
        _append_sep(lines_buf, add_line, config, usable_w, fs, family)

    add_line(f"التاريخ: {datetime.now().strftime('%Y-%m-%d')}", "body")

    count = summary.get("count", 0)
    subtotal = summary.get("total_subtotal", 0)
    vat_amt = summary.get("total_vat", 0)
    total = summary.get("total_sales", 0)
    vat_rate = float(shop_info.get("vat_rate", 15)) if shop_info.get("vat_enabled", "1") == "1" else 0

    add_line(f"عدد الفواتير:  {count}", "body")
    add_line(f"صافي المبيعات:  {subtotal:,.2f} {CURRENCY_SYM}", "body")
    add_line(f"الضريبة ({vat_rate:.0f}%):  {vat_amt:,.2f} {CURRENCY_SYM}", "body")
    if show_sep:
        _append_sep(lines_buf, add_line, config, usable_w, fs, family)
    add_line(f"الإجمالي:  {total:,.2f} {CURRENCY_SYM}", "totals", bold=True, alignment="center")

    if show_sep:
        eq_len = max(1, int(usable_w / max(6, fs.get("body", 11)) * config.get("separator_length", 100) / 100))
        eq_char = (config.get("separator_char", "-") or "-")[0]
        add_line(eq_char * eq_len, "body")

    add_line("شكراً لتسوقكم", "header", alignment="center")

    # Compute line heights
    line_heights = []
    for item, font_key, bold, alignment, is_table in lines_buf:
        fsize = fs.get(font_key, fs["body"])
        use_font = _resolve_font(family, fsize, bold)
        bbox = use_font.getbbox("Agh") if hasattr(use_font, "getbbox") else None
        fh = (bbox[3] - bbox[1]) if bbox else fsize
        lh = int(fh * ls + line_gap)
        line_heights.append((lh, use_font))
    text_h = sum(lh for lh, _ in line_heights)

    # Logo
    logo_img = None
    logo_h = 0
    logo_w_actual = 0
    logo_path = config.get("logo_path", "") or shop_info.get("report_logo", "")
    logo_cfg_w = int(config.get("logo_width", 120))
    logo_offset = int(config.get("logo_x_offset", 0))
    if logo_path and os.path.isfile(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            aspect = logo_img.height / logo_img.width if logo_img.width else 1
            logo_w_actual = min(logo_cfg_w, cw - 4 - margin * 2)
            logo_h = int(logo_w_actual * aspect)
            logo_img = logo_img.resize((logo_w_actual, logo_h), Image.LANCZOS)
        except Exception:
            logo_img = None

    total_h = max(min_h, 4 + margin + (logo_h + 12 if logo_img else 0) + text_h + margin + 10)

    # Canvas
    img = Image.new("RGB", (cw, total_h), STUDIO_BG)
    draw = ImageDraw.Draw(img)
    paper_rect = [4, 4, cw - 5, total_h - 5]
    border_w = 2 if config.get("show_receipt_border", False) else 1
    border_clr = "#222222" if config.get("show_receipt_border", False) else PAPER_BORDER
    draw.rectangle(paper_rect, fill=PAPER_FILL, outline=border_clr, width=border_w)

    y = 4 + margin

    if logo_img:
        center_x = (cw - logo_w_actual) // 2 + logo_offset
        max_x = cw - 4 - margin - logo_w_actual
        min_x = 4 + margin
        center_x = max(min_x, min(center_x, max_x))
        if logo_img.mode == "RGBA":
            paper = img.crop((center_x, y, center_x + logo_w_actual, y + logo_h))
            paper.paste(logo_img, (0, 0), logo_img)
            img.paste(paper, (center_x, y))
        else:
            img.paste(logo_img, (center_x, y))
        y += logo_h + 12

    # Render lines
    for i, (item, font_key, bold, alignment, is_table) in enumerate(lines_buf):
        use_font = line_heights[i][1]
        lh = line_heights[i][0]
        if not is_table:
            text = item
            display = _reshape(text)
            tw = draw.textlength(display, font=use_font)
            if alignment == "center":
                x = (cw - tw) // 2
            elif alignment == "left":
                x = content_left
            else:
                x = cw - 4 - margin - tw
            draw.text((x, y), display, fill="#111111", font=use_font)
            y += lh

    return img


def render_monthly_preview(config, shop_info, daily_rows, month_name, year,
                           canvas_width=None, include_returns=False,
                           returns_data=None):
    """Render a monthly-sales summary image with totals only."""
    family = config.get("font_family", "Arial")
    fs = config["font_sizes"]
    ls = float(config.get("line_spacing", 1.0))
    line_gap = 4
    cw = canvas_width or int(config.get("canvas_width", 400))
    margin = int(config.get("side_margin", 16))
    min_h = max(400, int(config.get("canvas_min_height", 0)))
    usable_w = cw - 4 - margin * 2
    content_left = 4 + margin

    lines_buf = []
    def add_line(text, font_key="body", bold=False, alignment=None):
        align = alignment or config.get("receipt_alignment", "right")
        lines_buf.append((text, font_key, bold, align))

    # Header
    shop_name = shop_info.get("shop_name", "")
    if shop_name:
        add_line(shop_name, "header", bold=True, alignment="center")
    phone = shop_info.get("shop_phone", "")
    if phone:
        add_line(f"تلفون: {phone}", "body", alignment="center")
    tax = shop_info.get("shop_tax_number", "")
    if shop_info.get("vat_enabled", "1") == "1" and tax:
        add_line(f"الرقم الضريبي: {tax}", "body", alignment="center")

    show_sep = config.get("show_separators", True)
    if show_sep:
        _append_sep(lines_buf, add_line, config, usable_w, fs, family)

    add_line(f"التقرير الشهري - {month_name} {year}", "header", bold=True, alignment="center")
    if show_sep:
        _append_sep(lines_buf, add_line, config, usable_w, fs, family)

    total_count = 0
    total_sub = 0.0
    total_vat = 0.0
    total_all = 0.0

    for d in daily_rows:
        total_count += d.get("count", 0)
        total_sub += d.get("subtotal", 0.0)
        total_vat += d.get("vat", 0.0)
        total_all += d.get("total", 0.0)

    # Totals (vertical layout)
    if show_sep:
        _append_sep(lines_buf, add_line, config, usable_w, fs, family)

    add_line(f"إجمالي الفواتير:  {total_count}", "body")
    if include_returns:
        ret_data = returns_data or {}
        ret_count = ret_data.get("count", 0)
        add_line(f"إجمالي المرتجعات:  {ret_count}", "body")
    add_line(f"إجمالي الضريبة:  {total_vat:,.2f} {CURRENCY_SYM}", "body")
    add_line(f"إجمالي المبيعات:  {total_all:,.2f} {CURRENCY_SYM}", "body")
    add_line(f"صافي الربح:  {total_sub:,.2f} {CURRENCY_SYM}", "totals", bold=True, alignment="center")

    if show_sep:
        eq_len = max(1, int(usable_w / max(6, fs.get("body", 11)) * config.get("separator_length", 100) / 100))
        eq_char = (config.get("separator_char", "-") or "-")[0]
        add_line(eq_char * eq_len, "body")

    add_line("شكراً لتسوقكم", "header", alignment="center")

    # Compute line heights
    line_heights = []
    for item, font_key, bold, alignment in lines_buf:
        fsize = fs.get(font_key, fs["body"])
        use_font = _resolve_font(family, fsize, bold)
        bbox = use_font.getbbox("Agh") if hasattr(use_font, "getbbox") else None
        fh = (bbox[3] - bbox[1]) if bbox else fsize
        lh = int(fh * ls + line_gap)
        line_heights.append((lh, use_font))
    text_h = sum(lh for lh, _ in line_heights)

    # Logo
    logo_img = None
    logo_h = 0
    logo_w_actual = 0
    logo_path = config.get("logo_path", "") or shop_info.get("report_logo", "")
    logo_cfg_w = int(config.get("logo_width", 120))
    logo_offset = int(config.get("logo_x_offset", 0))
    if logo_path and os.path.isfile(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            aspect = logo_img.height / logo_img.width if logo_img.width else 1
            logo_w_actual = min(logo_cfg_w, cw - 4 - margin * 2)
            logo_h = int(logo_w_actual * aspect)
            logo_img = logo_img.resize((logo_w_actual, logo_h), Image.LANCZOS)
        except Exception:
            logo_img = None

    total_h = max(min_h, 4 + margin + (logo_h + 12 if logo_img else 0) + text_h + margin + 10)

    img = Image.new("RGB", (cw, total_h), STUDIO_BG)
    draw = ImageDraw.Draw(img)
    paper_rect = [4, 4, cw - 5, total_h - 5]
    border_w = 2 if config.get("show_receipt_border", False) else 1
    border_clr = "#222222" if config.get("show_receipt_border", False) else PAPER_BORDER
    draw.rectangle(paper_rect, fill=PAPER_FILL, outline=border_clr, width=border_w)

    y = 4 + margin

    if logo_img:
        center_x = (cw - logo_w_actual) // 2 + logo_offset
        max_x = cw - 4 - margin - logo_w_actual
        min_x = 4 + margin
        center_x = max(min_x, min(center_x, max_x))
        if logo_img.mode == "RGBA":
            paper = img.crop((center_x, y, center_x + logo_w_actual, y + logo_h))
            paper.paste(logo_img, (0, 0), logo_img)
            img.paste(paper, (center_x, y))
        else:
            img.paste(logo_img, (center_x, y))
        y += logo_h + 12

    for i, (item, font_key, bold, alignment) in enumerate(lines_buf):
        use_font = line_heights[i][1]
        lh = line_heights[i][0]
        text = item
        display = _reshape(text)
        tw = draw.textlength(display, font=use_font)
        if alignment == "center":
            x = (cw - tw) // 2
        elif alignment == "left":
            x = content_left
        else:
            x = cw - 4 - margin - tw
        draw.text((x, y), display, fill="#111111", font=use_font)
        y += lh

    return img


def _append_sep(lines_buf, add_line, config, usable_w, fs, family):
    """Append a separator line whose character repeat count is scaled to pixel width."""
    sep_char = (config.get("separator_char", "-") or "-")[0]
    pct = max(10, min(100, int(config.get("separator_length", 100))))
    body_font = _resolve_font(config.get("font_family", "Arial"),
                              fs.get("body", 11))
    try:
        avg_w = body_font.getbbox("0")[2]  # pixel width of one digit
    except Exception:
        avg_w = max(4, int(fs.get("body", 11) * 0.55))
    count = max(1, int(usable_w * pct / 100 / max(1, avg_w)))
    add_line(sep_char * count, "body")


def build_escpos_from_config(config, shop_info, invoice_data):
    """Build ESC/POS bytes using the config for future use."""
    items = invoice_data.get("items", [])
    total = invoice_data.get("total", 0)
    inv_no = invoice_data.get("invoice_number", "")
    lines, chars, ls, fs = _generate_receipt_lines(
        config, shop_info, items, inv_no, total
    )

    data = bytearray()
    data.extend([0x1B, 0x40])        # Initialize
    data.extend([0x1B, 0x61, 0x01])  # Center alignment

    for text, font_key, bold, alignment in lines:
        line = _reshape(text)
        data.extend(line.encode("utf-8"))
        data.extend([0x0A])

    data.extend([0x1B, 0x61, 0x00])  # Left
    data.extend([0x1D, 0x56, 0x00])  # Cut
    return bytes(data)
