import os
from datetime import datetime
import os
from utils import format_currency, CURRENCY_SYM

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    HAS_ARABIC_SHAPE = True
except ImportError:
    HAS_ARABIC_SHAPE = False


class InvoiceGenerator:
    def __init__(self, db, shop_name="", shop_phone="", shop_email="",
                 shop_tax="", vat_rate=15, width_mm=58, config=None):
        self.db = db
        self.shop_name = shop_name
        self.shop_phone = shop_phone
        self.shop_email = shop_email
        self.shop_tax = shop_tax
        self.vat_rate = vat_rate
        self.width_mm = width_mm
        self.config = config
        self._load_settings()
        if self.config is None:
            self._load_config()

    def _load_settings(self):
        settings = self.db.get_all_settings()
        self.shop_name = settings.get("shop_name", self.shop_name)
        self.shop_phone = settings.get("shop_phone", self.shop_phone)
        self.shop_email = settings.get("shop_email", self.shop_email)
        self.shop_tax = settings.get("shop_tax_number", self.shop_tax)
        self.vat_enabled = settings.get("vat_enabled", "1") == "1"
        self.vat_rate = float(settings.get("vat_rate", str(self.vat_rate)))
        self.width_mm = int(settings.get("receipt_width", "58"))

    def _load_config(self):
        try:
            from invoice_config import load_config, DEFAULT_CONFIG
            loaded = load_config()
            # Merge with defaults so missing keys never crash downstream code
            cfg = DEFAULT_CONFIG.copy()
            cfg.update(loaded)
            self.config = cfg
        except Exception:
            try:
                from invoice_config import DEFAULT_CONFIG
                self.config = DEFAULT_CONFIG.copy()
            except Exception:
                self.config = None

    @property
    def width(self):
        if self.width_mm >= 80:
            return 44
        if self.width_mm >= 58:
            return 36
        return 28

    @property
    def _col(self):
        """Legacy column sizes for the fallback path only."""
        w = self.width
        if w >= 44:
            return (26, 7, 7)
        if w >= 36:
            return (20, 6, 6)
        return (14, 5, 5)

    @staticmethod
    def _center_in(text, width):
        """Centre text within a fixed character width for monospace output."""
        if len(text) >= width:
            return text[:width]
        left = (width - len(text)) // 2
        return " " * left + text

    def _sep(self, char="-"):
        if self.config:
            cfg_char = (self.config.get("separator_char", "-") or "-")[0]
            pct = max(10, min(100, int(self.config.get("separator_length", 100))))
            length = max(1, int(self.width * pct / 100))
            return cfg_char * length
        return char * self.width

    def _center(self, text):
        w = self.width
        if len(text) >= w:
            return text[:w]
        return " " * ((w - len(text)) // 2) + text

    def _reshape(self, text):
        if HAS_ARABIC_SHAPE:
            try:
                return get_display(arabic_reshaper.reshape(text))
            except Exception:
                return text
        return text

    def _align_text(self, text, alignment):
        """Pad *text* to ``self.width`` using *alignment* (right/center/left)."""
        w = self.width
        if alignment == "center":
            return self._center(text)
        elif alignment == "left":
            return text.ljust(w)
        return text.rjust(w)

    def generate_text(self, invoice_data, for_printer=False, use_config=True):
        if use_config and self.config:
            return self._generate_text_with_config(invoice_data, for_printer)
        return self._generate_text_fallback(invoice_data, for_printer)

    def _generate_text_fallback(self, invoice_data, for_printer=False):
        w = self.width
        nc, qc, pc = self._col

        def add(line):
            lines.append(self._reshape(line) if for_printer else line)

        lines = []

        add(self._center(self.shop_name))
        if self.shop_phone:
            add(self._center(f"تلفون: {self.shop_phone}"))
        if self.vat_enabled and self.shop_tax:
            add(self._center(f"الرقم الضريبي: {self.shop_tax}"))
        add(self._sep())
        add(f"الفاتورة: {invoice_data['invoice_number']}")
        add(f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        # Table offset for fallback
        w2 = self.width
        toff = max(-w2 // 4, min(w2 // 4,
                   (self.config.get("table_offset", 0) if self.config else 0) // 10))
        def add_tbl(txt):
            if toff > 0:
                add(" " * toff + txt)
            elif toff < 0:
                add(txt[max(-toff):])
            else:
                add(txt)
        # Centred column headers, reversed order for RTL sync
        add_tbl(f"{self._center_in('السعر', pc)}  "
            f"{self._center_in('الكمية', qc)}  "
            f"{self._center_in('الصنف', nc)}")

        for item in invoice_data["items"]:
            name = item["product_name"][:nc]
            qty = f"{item['quantity']:.2f}"
            price = format_currency(item["total"])
            add_tbl(f"{self._center_in(price, pc)}  "
                f"{self._center_in(qty, qc)}  "
                f"{self._center_in(name, nc)}")

        add(self._sep())

        vat_rate = self.vat_rate if self.vat_enabled else 0
        total = invoice_data["total"]
        vat_amount = total - (total / (1 + vat_rate / 100))
        subtotal = total - vat_amount
        master_align = self.config.get("receipt_alignment", "right") if self.config else "right"

        def tot(label, amount):
            return self._align_text(
                f"{label} {format_currency(amount):>6}", master_align)

        if self.vat_enabled:
            add(tot("المجموع الخاضع للضريبة:", subtotal))
            add(tot(f"ضريبة القيمة المضافة ({vat_rate:.0f}%):", vat_amount))
            total_val = f"{format_currency(total):>6} {CURRENCY_SYM}"
            add(self._align_text(
                f"{'الإجمالي شامل الضريبة:'} {total_val}", master_align))
        else:
            total_val = f"{format_currency(total):>6} {CURRENCY_SYM}"
            add(self._align_text(
                f"{'الإجمالي:'} {total_val}", master_align))
        add(self._sep("="))
        add(self._center("شكراً لتسوقكم"))

        return "\n".join(lines)

    def _generate_text_with_config(self, invoice_data, for_printer=False):
        cfg = self.config
        w = self.width
        cfg_col = cfg["columns"]
        col_widths = cfg_col.get("widths", {})

        # Determine visible column keys
        data_keys = [k for k in ("name", "quantity", "price", "vat")
                     if cfg_col.get(f"show_{k}", k == "name")]
        if cfg_col.get("show_total", True):
            data_keys.append("total")
        if not data_keys:
            data_keys = ["name", "quantity", "price"]

        # Calculate column widths in characters from percentage weights
        all_pct = sum(col_widths.get(k, 20) for k in data_keys)
        if all_pct <= 0:
            all_pct = 100
        gaps = 4 * max(len(data_keys) - 1, 0)
        avail = w - gaps
        col_chars = {}
        for k in data_keys:
            col_chars[k] = max(2, int(avail * col_widths.get(k, 20) / all_pct))

        def add(line):
            lines.append(self._reshape(line) if for_printer else line)

        lines = []

        # Header
        add(self._center(self.shop_name))
        if self.shop_phone:
            add(self._center(f"تلفون: {self.shop_phone}"))
        if self.vat_enabled and self.shop_tax:
            add(self._center(f"الرقم الضريبي: {self.shop_tax}"))

        # Header notes — bake alignment into text with padding
        hn = cfg.get("header_notes", "").strip()
        if hn:
            add("")
            for ln in hn.split("\n"):
                txt = ln.strip()
                al = cfg.get("header_notes_alignment", "right")
                if al == "center":
                    add(self._center(txt))
                elif al == "left":
                    add(txt.ljust(w))
                else:
                    add(txt.rjust(w))

        add(self._sep())
        add(f"الفاتورة: {invoice_data['invoice_number']}")
        add(f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Table offset — convert pixels to approximate char offset
        toff = max(-w // 4, min(w // 4, cfg.get("table_offset", 0) // 10))

        def add_table_line(text):
            if toff > 0:
                add(" " * toff + text)
            elif toff < 0:
                add(text[max(-toff):])
            else:
                add(text)

        # Column headers — centred in their slots, reversed order to match
        # the physical coordinate fix in invoice_config._build_column_layout.
        col_labels = {"name": "الصنف", "quantity": "الكمية",
                      "price": "السعر", "vat": "الضريبة", "total": "الإجمالي"}
        hdr_parts = []
        for k in reversed(data_keys):
            hdr_parts.append(self._center_in(col_labels.get(k, k), col_chars[k]))
        add_table_line("  ".join(hdr_parts))

        # Items — centred values in each column, reversed order
        vat_rate = self.vat_rate
        for item in invoice_data["items"]:
            parts = []
            for k in reversed(data_keys):
                if k == "name":
                    val = item["product_name"][:col_chars[k]]
                elif k == "quantity":
                    val = f"{item['quantity']:.2f}"
                elif k == "price":
                    t = item["total"]
                    q = item["quantity"]
                    unit = t / q if q else 0
                    val = format_currency(unit)
                elif k == "vat":
                    t = item["total"]
                    vat_amt = t - (t / (1 + vat_rate / 100))
                    val = format_currency(vat_amt)
                else:
                    val = format_currency(item["total"])
                parts.append(self._center_in(val, col_chars[k]))
            add_table_line("  ".join(parts))

        add_table_line(self._sep())

        vat_rate = self.vat_rate if self.vat_enabled else 0
        total = invoice_data["total"]
        vat_amount = total - (total / (1 + vat_rate / 100))
        subtotal = total - vat_amount
        master_align = cfg.get("receipt_alignment", "right")

        def tot(label, amount):
            return self._align_text(
                f"{label} {format_currency(amount):>6}", master_align)

        if self.vat_enabled:
            add(tot("المجموع الخاضع للضريبة:", subtotal))
            add(tot(f"ضريبة القيمة المضافة ({vat_rate:.0f}%):", vat_amount))
            total_val = f"{format_currency(total):>6} {CURRENCY_SYM}"
            add(self._align_text(
                f"{'الإجمالي شامل الضريبة:'} {total_val}", master_align))
        else:
            total_val = f"{format_currency(total):>6} {CURRENCY_SYM}"
            add(self._align_text(
                f"{'الإجمالي:'} {total_val}", master_align))
        add(self._sep("="))

        # Footer notes — bake alignment into text with padding
        fn = cfg.get("footer_notes", "").strip()
        if fn:
            for ln in fn.split("\n"):
                txt = ln.strip()
                al = cfg.get("footer_notes_alignment", "right")
                if al == "center":
                    add(self._center(txt))
                elif al == "left":
                    add(txt.ljust(w))
                else:
                    add(txt.rjust(w))

        add(self._center("شكراً لتسوقكم"))

        return "\n".join(lines)

    def print_to_file(self, invoice_data, filepath=None):
        text = self.generate_text(invoice_data, for_printer=False)
        if not filepath:
            filepath = self._invoice_filename(invoice_data)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        return filepath

    def _generate_print_image(self, invoice_data):
        from invoice_config import render_invoice_preview, generate_barcode_image_1x, DEFAULT_CONFIG
        import PIL.Image as PILImage

        cfg = DEFAULT_CONFIG.copy()
        if self.config:
            cfg.update(self.config)
        settings = self.db.get_all_settings()
        shop_info = {
            "shop_name": self.shop_name,
            "shop_phone": self.shop_phone,
            "shop_tax_number": self.shop_tax,
            "report_logo": settings.get("report_logo", ""),
            "vat_enabled": "1" if self.vat_enabled else "0",
            "vat_rate": str(self.vat_rate),
            "receipt_width": str(self.width_mm),
        }
        items = invoice_data.get("items", [])
        inv_no = invoice_data.get("invoice_number", "")
        inv_total = invoice_data.get("total", 0)
        if self.width_mm >= 80:
            cw = 576
        elif self.width_mm >= 58:
            cw = 384
        else:
            cw = 320

        # Render at 2x resolution for smoother font curves, then downscale
        scale = 2
        cfg_hi = cfg.copy()
        cfg_hi["font_sizes"] = {k: v * scale for k, v in cfg["font_sizes"].items()}
        cfg_hi["canvas_width"] = cw * scale
        cfg_hi["side_margin"] = cfg.get("side_margin", 16) * scale
        cfg_hi["canvas_min_height"] = 0  # auto-height: let content drive total height
        cfg_hi["logo_width"] = cfg.get("logo_width", 120) * scale
        cfg_hi["barcode_height"] = cfg.get("barcode_height", 50) * scale
        cfg_hi["barcode_scale"] = cfg.get("barcode_scale", 1.0) * scale
        if cfg.get("barcode_type", "code128") == "qrcode":
            cfg_hi["qrcode_size"] = cfg.get("qrcode_size", 200) * scale
        # 1. Render the entire receipt without the barcode at 2x
        img_hi = render_invoice_preview(
            cfg_hi, shop_info,
            sample_items=items,
            canvas_width=cw * scale,
            invoice_number=inv_no,
            invoice_total=inv_total,
            skip_barcode=True,
        )
        new_h = max(1, round(img_hi.height / scale)) + 1
        img = img_hi.resize((cw, new_h), PILImage.LANCZOS)

        # Generate barcode FIRST so we know its height for canvas sizing
        bc_img, bc_h = generate_barcode_image_1x(cfg, inv_no, cw, cfg.get("side_margin", 16))

        # Top padding so printer top-of-form doesn't clip the logo
        pad_top = 30
        bc_gap = 10
        pad_bot = 80
        if bc_img and bc_h > 0:
            pad_bot = max(pad_bot, bc_h + bc_gap * 2)
        padded = PILImage.new("RGB", (img.width, img.height + pad_top + pad_bot), "white")
        padded.paste(img, (0, pad_top))

        # Binary threshold (gentle — no aggressive contrast pass)
        gray = padded.convert("L")
        threshold_val = int(cfg.get("print_threshold", 160))
        bw = gray.point(lambda x: 0 if x < threshold_val else 255, "1")

        # 2. Overlay razor-sharp barcode BELOW the content (never overlapping)
        if bc_img and bc_h > 0:
            bc_x = (cw - bc_img.width) // 2
            bc_y = pad_top + new_h + bc_gap  # below content with gap
            bc_1bit = bc_img.convert("L").point(lambda x: 0 if x < 128 else 255, "1")
            bw.paste(bc_1bit, (bc_x, bc_y))
        return bw

    def _generate_summary_image(self, summary, title="ملخص المبيعات اليومية"):
        from invoice_config import render_summary_preview, DEFAULT_CONFIG
        import PIL.Image as PILImage

        cfg = DEFAULT_CONFIG.copy()
        if self.config:
            cfg.update(self.config)
        settings = self.db.get_all_settings()
        shop_info = {
            "shop_name": self.shop_name,
            "shop_phone": self.shop_phone,
            "shop_tax_number": self.shop_tax,
            "report_logo": settings.get("report_logo", ""),
            "vat_enabled": "1" if self.vat_enabled else "0",
            "vat_rate": str(self.vat_rate),
            "receipt_width": str(self.width_mm),
        }
        if self.width_mm >= 80:
            cw = 576
        elif self.width_mm >= 58:
            cw = 384
        else:
            cw = 320

        scale = 2
        cfg_hi = cfg.copy()
        cfg_hi["font_sizes"] = {k: v * scale for k, v in cfg["font_sizes"].items()}
        cfg_hi["canvas_width"] = cw * scale
        cfg_hi["side_margin"] = cfg.get("side_margin", 16) * scale
        cfg_hi["canvas_min_height"] = 0
        cfg_hi["logo_width"] = cfg.get("logo_width", 120) * scale

        img_hi = render_summary_preview(
            cfg_hi, shop_info, summary, title=title, canvas_width=cw * scale,
        )
        new_h = max(1, round(img_hi.height / scale)) + 1
        img = img_hi.resize((cw, new_h), PILImage.LANCZOS)

        pad_top = 30
        pad_bot = 80
        padded = PILImage.new("RGB", (img.width, img.height + pad_top + pad_bot), "white")
        padded.paste(img, (0, pad_top))
        gray = padded.convert("L")
        threshold_val = int(cfg.get("print_threshold", 160))
        bw = gray.point(lambda x: 0 if x < threshold_val else 255, "1")
        return bw

    def _generate_monthly_image(self, daily_rows, month_name, year,
                                include_returns=False, returns_data=None):
        from invoice_config import render_monthly_preview, DEFAULT_CONFIG
        import PIL.Image as PILImage

        cfg = DEFAULT_CONFIG.copy()
        if self.config:
            cfg.update(self.config)
        settings = self.db.get_all_settings()
        shop_info = {
            "shop_name": self.shop_name,
            "shop_phone": self.shop_phone,
            "shop_tax_number": self.shop_tax,
            "report_logo": settings.get("report_logo", ""),
            "vat_enabled": "1" if self.vat_enabled else "0",
            "vat_rate": str(self.vat_rate),
            "receipt_width": str(self.width_mm),
        }
        if self.width_mm >= 80:
            cw = 576
        elif self.width_mm >= 58:
            cw = 384
        else:
            cw = 320

        scale = 2
        cfg_hi = cfg.copy()
        cfg_hi["font_sizes"] = {k: v * scale for k, v in cfg["font_sizes"].items()}
        cfg_hi["canvas_width"] = cw * scale
        cfg_hi["side_margin"] = cfg.get("side_margin", 16) * scale
        cfg_hi["canvas_min_height"] = 0
        cfg_hi["logo_width"] = cfg.get("logo_width", 120) * scale

        img_hi = render_monthly_preview(
            cfg_hi, shop_info, daily_rows, month_name, year,
            canvas_width=cw * scale,
            include_returns=include_returns,
            returns_data=returns_data,
        )
        new_h = max(1, round(img_hi.height / scale)) + 1
        img = img_hi.resize((cw, new_h), PILImage.LANCZOS)

        pad_top = 30
        pad_bot = 80
        padded = PILImage.new("RGB", (img.width, img.height + pad_top + pad_bot), "white")
        padded.paste(img, (0, pad_top))
        gray = padded.convert("L")
        threshold_val = int(cfg.get("print_threshold", 160))
        bw = gray.point(lambda x: 0 if x < threshold_val else 255, "1")
        return bw

    def print_monthly(self, daily_rows, month_name, year,
                      include_returns=False, returns_data=None):
        try:
            img = self._generate_monthly_image(
                daily_rows, month_name, year,
                include_returns=include_returns,
                returns_data=returns_data,
            )
            import win32print
            import win32ui
            from PIL import ImageWin
            printer_name = win32print.GetDefaultPrinter()
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)
            iw, ih = img.size
            offset_x = hdc.GetDeviceCaps(112)
            offset_y = hdc.GetDeviceCaps(113)
            page_w = hdc.GetDeviceCaps(110)
            left = offset_x + (page_w - 2 * offset_x - iw) // 2
            target_x = max(0, left)
            target_y = max(0, offset_y)
            hdc.StartDoc("POS_Monthly_Image")
            hdc.StartPage()
            dib = ImageWin.Dib(img)
            dib.draw(hdc.GetHandleOutput(), (target_x, target_y, target_x + iw, target_y + ih))
            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()
            self._send_cut(printer_name)
            return True, "تمت طباعة التقرير الشهري على الطابعة الحرارية"
        except Exception as e:
            return False, str(e)

    def print_summary(self, summary, title="ملخص المبيعات اليومية"):
        """Print a daily/monthly summary report using the same image pipeline."""
        try:
            img = self._generate_summary_image(summary, title)
            import win32print
            import win32ui
            from PIL import ImageWin
            printer_name = win32print.GetDefaultPrinter()
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)
            iw, ih = img.size
            offset_x = hdc.GetDeviceCaps(112)
            offset_y = hdc.GetDeviceCaps(113)
            page_w = hdc.GetDeviceCaps(110)
            left = offset_x + (page_w - 2 * offset_x - iw) // 2
            target_x = max(0, left)
            target_y = max(0, offset_y)
            hdc.StartDoc("POS_Summary_Image")
            hdc.StartPage()
            dib = ImageWin.Dib(img)
            dib.draw(hdc.GetHandleOutput(), (target_x, target_y, target_x + iw, target_y + ih))
            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()
            self._send_cut(printer_name)
            return True, "تمت طباعة التقرير على الطابعة الحرارية"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _send_cut(printer_name=None):
        try:
            import win32print
            if printer_name is None:
                printer_name = win32print.GetDefaultPrinter()
            p_handle = win32print.OpenPrinter(printer_name)
            try:
                win32print.StartDocPrinter(p_handle, 1, ("Cutter Job", None, "RAW"))
                win32print.StartPagePrinter(p_handle)
                win32print.WritePrinter(p_handle, b"\x1b\x64\x04")
                win32print.WritePrinter(p_handle, b"\x1d\x56\x41\x00")
                win32print.EndPagePrinter(p_handle)
                win32print.EndDocPrinter(p_handle)
            finally:
                win32print.ClosePrinter(p_handle)
        except Exception:
            pass

    def print_to_printer(self, invoice_data, printer_name=None):
        try:
            img = self._generate_print_image(invoice_data)
            if printer_name is None:
                import win32print
                printer_name = win32print.GetDefaultPrinter()
            from PIL import ImageWin
            import win32ui
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)
            iw, ih = img.size
            # Centre image on printable area
            offset_x = hdc.GetDeviceCaps(112)  # PHYSICALOFFSETX
            offset_y = hdc.GetDeviceCaps(113)  # PHYSICALOFFSETY
            page_w = hdc.GetDeviceCaps(110)    # PHYSICALWIDTH
            left = offset_x + (page_w - 2 * offset_x - iw) // 2
            target_x = max(0, left)
            target_y = max(0, offset_y)
            hdc.StartDoc("POS_Invoice_Image")
            hdc.StartPage()
            dib = ImageWin.Dib(img)
            dib.draw(hdc.GetHandleOutput(), (target_x, target_y, target_x + iw, target_y + ih))
            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()
            self._send_cut(printer_name)
            return True, "تمت الطباعة على الطابعة الحرارية"
        except Exception as e:
            return False, str(e)

    def _invoices_dir(self):
        docs = os.path.join(os.path.expanduser("~"), "Documents", "الفواتير")
        os.makedirs(docs, exist_ok=True)
        return docs

    def _invoice_filename(self, invoice_data):
        name = invoice_data["invoice_number"].replace("/", "-").replace("\\", "-")
        return os.path.join(self._invoices_dir(), f"{name}.txt")

    def direct_print(self, invoice_data, filepath=None):
        # Always save the file first
        text = self.generate_text(invoice_data, for_printer=False)
        if not filepath:
            filepath = self._invoice_filename(invoice_data)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)

        # Try image-based thermal printing
        try:
            img = self._generate_print_image(invoice_data)
            import win32print
            import win32ui
            from PIL import ImageWin
            printer_name = win32print.GetDefaultPrinter()
            hdc = win32ui.CreateDC()
            hdc.CreatePrinterDC(printer_name)
            iw, ih = img.size
            # Centre image on printable area
            offset_x = hdc.GetDeviceCaps(112)  # PHYSICALOFFSETX
            offset_y = hdc.GetDeviceCaps(113)  # PHYSICALOFFSETY
            page_w = hdc.GetDeviceCaps(110)    # PHYSICALWIDTH
            left = offset_x + (page_w - 2 * offset_x - iw) // 2
            target_x = max(0, left)
            target_y = max(0, offset_y)
            hdc.StartDoc("POS_Invoice_Image")
            hdc.StartPage()
            dib = ImageWin.Dib(img)
            dib.draw(hdc.GetHandleOutput(), (target_x, target_y, target_x + iw, target_y + ih))
            hdc.EndPage()
            hdc.EndDoc()
            hdc.DeleteDC()
            self._send_cut(printer_name)
            self._auto_drawer_kick()
            return True, f"تمت الطباعة وحفظ الفاتورة في: {filepath}"
        except Exception:
            # Fallback: open with default app for manual print
            try:
                import ctypes
                ctypes.windll.shell32.ShellExecuteW(
                    None, "print", filepath, None, None, 0
                )
                self._auto_drawer_kick()
                return True, f"تم حفظ الفاتورة في: {filepath}"
            except Exception as e:
                return True, f"تم حفظ الفاتورة في: {filepath}"

    def _auto_drawer_kick(self):
        open_drawer = self.db.get_setting("open_drawer_on_sale", "1") == "1"
        if open_drawer:
            self.kick_cash_drawer()

    @staticmethod
    def kick_cash_drawer():
        from utils import open_cash_drawer
        open_cash_drawer()
