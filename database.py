import sqlite3
import os
import sys
import shutil
from datetime import datetime


def _get_data_dir():
    if getattr(sys, "frozen", False):
        data_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "POS_System")
    else:
        data_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(data_dir, exist_ok=True)
    return data_dir


DB_PATH = os.path.join(_get_data_dir(), "pos_data.db")


class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                barcode TEXT UNIQUE,
                image_path TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT UNIQUE NOT NULL,
                subtotal REAL NOT NULL DEFAULT 0,
                vat_rate REAL NOT NULL DEFAULT 15,
                vat_amount REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                product_id INTEGER,
                product_name TEXT NOT NULL,
                quantity REAL NOT NULL,
                price_per_kg REAL NOT NULL,
                total REAL NOT NULL,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS backup_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS product_barcodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER NOT NULL,
                barcode TEXT NOT NULL UNIQUE,
                quantity REAL NOT NULL DEFAULT 1.0,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
            );
        """)
        default_settings = {
            "shop_name": "متجر الخضار والفواكه",
            "shop_phone": "05xxxxxxxx",
            "shop_email": "shop@example.com",
            "shop_tax_number": "3XXXXXXXXXXX",
            "vat_rate": "15",
            "vat_enabled": "1",
            "last_invoice_number": "0",
            "receipt_width": "58",
            "open_drawer_on_sale": "1",
            "lock_password": "",
            "lock_sales": "0",
            "lock_products": "0",
            "lock_reports": "0",
        }
        for key, value in default_settings.items():
            c.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        # ── Migration: add status column if missing ──
        try:
            c.execute("ALTER TABLE invoices ADD COLUMN status TEXT NOT NULL DEFAULT 'active'")
        except Exception:
            pass
        # ── Migration: add label column to product_barcodes ──
        try:
            c.execute("ALTER TABLE product_barcodes ADD COLUMN label TEXT DEFAULT ''")
        except Exception:
            pass

        conn.commit()
        conn.close()

    # ─────────── Settings ───────────

    def get_setting(self, key, default=""):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = c.fetchone()
        conn.close()
        return row["value"] if row else default

    def set_setting(self, key, value):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        conn.commit()
        conn.close()

    def get_all_settings(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT key, value FROM settings")
        rows = c.fetchall()
        conn.close()
        return {row["key"]: row["value"] for row in rows}

    def get_locks(self):
        return {
            "password": self.get_setting("lock_password", ""),
            "sales": self.get_setting("lock_sales", "0") == "1",
            "products": self.get_setting("lock_products", "0") == "1",
            "reports": self.get_setting("lock_reports", "0") == "1",
        }

    def save_locks(self, password, lock_sales, lock_products, lock_reports):
        self.set_setting("lock_password", password)
        self.set_setting("lock_sales", "1" if lock_sales else "0")
        self.set_setting("lock_products", "1" if lock_products else "0")
        self.set_setting("lock_reports", "1" if lock_reports else "0")

    def update_shop_settings(self, name, phone, email, tax_number, vat_rate):
        self.set_setting("shop_name", name)
        self.set_setting("shop_phone", phone)
        self.set_setting("shop_email", email)
        self.set_setting("shop_tax_number", tax_number)
        self.set_setting("vat_rate", vat_rate)

    # ─────────── Products ───────────

    def add_product(self, name, price, barcode="", image_path="", copy_image=True):
        conn = self._get_conn()
        c = conn.cursor()
        final_path = ""
        if image_path and os.path.isfile(image_path) and copy_image:
            assets_dir = os.path.join(os.path.dirname(self.db_path), "assets")
            os.makedirs(assets_dir, exist_ok=True)
            ext = os.path.splitext(image_path)[1] or ".jpg"
            dest = os.path.join(assets_dir, f"prod_{int(datetime.now().timestamp())}{ext}")
            try:
                shutil.copy2(image_path, dest)
                final_path = dest
            except Exception:
                final_path = image_path
        elif image_path:
            final_path = image_path

        c.execute(
            """INSERT INTO products (name, price, barcode, image_path)
               VALUES (?, ?, ?, ?)""",
            (name, price, barcode or None, final_path or None),
        )
        conn.commit()
        pid = c.lastrowid
        conn.close()
        return pid

    def update_product(self, pid, name, price, barcode="", image_path="", copy_image=True):
        conn = self._get_conn()
        c = conn.cursor()
        final_path = ""
        if image_path and os.path.isfile(image_path) and copy_image:
            assets_dir = os.path.join(os.path.dirname(self.db_path), "assets")
            os.makedirs(assets_dir, exist_ok=True)
            ext = os.path.splitext(image_path)[1] or ".jpg"
            dest = os.path.join(assets_dir, f"prod_{int(datetime.now().timestamp())}{ext}")
            try:
                shutil.copy2(image_path, dest)
                final_path = dest
            except Exception:
                final_path = image_path
        elif image_path:
            final_path = image_path

        if final_path:
            c.execute(
                """UPDATE products SET name=?, price=?, barcode=?, image_path=?,
                   updated_at=datetime('now','localtime') WHERE id=?""",
                (name, price, barcode or None, final_path, pid),
            )
        else:
            c.execute(
                """UPDATE products SET name=?, price=?, barcode=?,
                   updated_at=datetime('now','localtime') WHERE id=?""",
                (name, price, barcode or None, pid),
            )
        conn.commit()
        conn.close()

    def delete_product(self, pid):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM products WHERE id=?", (pid,))
        conn.commit()
        conn.close()

    def get_product(self, pid):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM products WHERE id=?", (pid,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_product_by_barcode(self, barcode):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """SELECT p.*, pb.quantity AS preset_qty FROM product_barcodes pb
               JOIN products p ON pb.product_id = p.id WHERE pb.barcode=?""",
            (barcode,),
        )
        row = c.fetchone()
        if row:
            d = dict(row)
            qty = d.pop("preset_qty")
            conn.close()
            return (d, qty)
        c.execute("SELECT * FROM products WHERE barcode=?", (barcode,))
        row = c.fetchone()
        conn.close()
        if row:
            return (dict(row), 1.0)
        return None

    def get_all_products(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM products ORDER BY name")
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search_products(self, query):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM products WHERE name LIKE ? OR barcode LIKE ? ORDER BY name",
            (f"%{query}%", f"%{query}%"),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ─────────── Product Barcodes ───────────

    def get_product_barcodes(self, product_id):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM product_barcodes WHERE product_id=? ORDER BY quantity",
            (product_id,),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_product_barcode(self, product_id, barcode, quantity, label=""):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO product_barcodes (product_id, barcode, quantity, label) VALUES (?, ?, ?, ?)",
            (product_id, barcode, quantity, label),
        )
        conn.commit()
        pid = c.lastrowid
        conn.close()
        return pid

    def delete_product_barcode(self, barcode_id):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM product_barcodes WHERE id=?", (barcode_id,))
        conn.commit()
        conn.close()

    def delete_product_barcodes(self, product_id):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM product_barcodes WHERE product_id=?", (product_id,))
        conn.commit()
        conn.close()

    # ─────────── Invoices ───────────

    def _next_invoice_number(self):
        last = self.get_setting("last_invoice_number", "0")
        num = int(last) + 1
        self.set_setting("last_invoice_number", str(num))
        now = datetime.now()
        return f"INV-{now.strftime('%Y%m%d')}-{num:04d}"

    def create_invoice(self, items, vat_rate=None):
        if vat_rate is None:
            vat_rate = float(self.get_setting("vat_rate", "15"))
        invoice_number = self._next_invoice_number()
        total = sum(item["total"] for item in items)
        vat_amount = total * vat_rate / (100 + vat_rate)
        subtotal = total - vat_amount

        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """INSERT INTO invoices (invoice_number, subtotal, vat_rate, vat_amount, total)
               VALUES (?, ?, ?, ?, ?)""",
            (invoice_number, subtotal, vat_rate, vat_amount, total),
        )
        invoice_id = c.lastrowid
        for item in items:
            c.execute(
                """INSERT INTO invoice_items (invoice_id, product_id, product_name, quantity, price_per_kg, total)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    invoice_id,
                    item.get("product_id"),
                    item["product_name"],
                    item["quantity"],
                    item["price_per_kg"],
                    item["total"],
                ),
            )
        conn.commit()
        conn.close()
        return {
            "id": invoice_id,
            "invoice_number": invoice_number,
            "subtotal": subtotal,
            "vat_rate": vat_rate,
            "vat_amount": vat_amount,
            "total": total,
            "items": items,
        }

    def get_invoice(self, invoice_id):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,))
        inv = c.fetchone()
        if not inv:
            conn.close()
            return None
        inv = dict(inv)
        c.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=?", (invoice_id,)
        )
        inv["items"] = [dict(r) for r in c.fetchall()]
        conn.close()
        return inv

    def get_invoice_by_number(self, number):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM invoices WHERE invoice_number=?", (number,))
        inv = c.fetchone()
        if not inv:
            conn.close()
            return None
        inv = dict(inv)
        c.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=?", (inv["id"],)
        )
        inv["items"] = [dict(r) for r in c.fetchall()]
        conn.close()
        return inv

    def get_all_invoices(self, limit=500):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM invoices ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _status_condition(self, include_returns=False):
        """Return (sql_fragment, params_extra) for status filtering."""
        if include_returns:
            return "status IN ('active', 'returned')", ()
        return "status='active'", ()

    def search_invoices(self, query="", date_from="", date_to="", include_returns=False):
        conn = self._get_conn()
        c = conn.cursor()
        status_sql, _ = self._status_condition(include_returns)
        conditions = [status_sql]
        params = []
        if query:
            conditions.append("(invoice_number LIKE ? OR EXISTS (SELECT 1 FROM invoice_items WHERE invoice_items.invoice_id = invoices.id AND product_name LIKE ?))")
            params.extend([f"%{query}%", f"%{query}%"])
        if date_from:
            conditions.append("DATE(created_at) >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("DATE(created_at) <= ?")
            params.append(date_to)
        limit = 500 if query else 200
        sql = "SELECT * FROM invoices"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        c.execute(sql, params)
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_sales_summary(self, date_from="", date_to="", include_returns=False):
        conn = self._get_conn()
        c = conn.cursor()
        status_sql, _ = self._status_condition(include_returns)
        conditions = [status_sql]
        params = []
        if date_from:
            conditions.append("DATE(created_at) >= ?")
            params.append(date_from)
        if date_to:
            conditions.append("DATE(created_at) <= ?")
            params.append(date_to)
        sql = "SELECT COUNT(*) as count, COALESCE(SUM(subtotal),0) as total_subtotal, COALESCE(SUM(vat_amount),0) as total_vat, COALESCE(SUM(total),0) as total_sales FROM invoices"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        c.execute(sql, params)
        row = c.fetchone()
        conn.close()
        return dict(row) if row else {"count": 0, "total_subtotal": 0, "total_vat": 0, "total_sales": 0}

    def get_daily_sales_for_month(self, year, month, include_returns=False):
        conn = self._get_conn()
        c = conn.cursor()
        from calendar import monthrange
        first = f"{year:04d}-{month:02d}-01"
        last = f"{year:04d}-{month:02d}-{monthrange(year, month)[1]}"
        status_sql, _ = self._status_condition(include_returns)
        c.execute(
            f"""SELECT DATE(created_at) as day,
                      COUNT(*) as count,
                      COALESCE(SUM(subtotal),0) as subtotal,
                      COALESCE(SUM(vat_amount),0) as vat,
                      COALESCE(SUM(total),0) as total
               FROM invoices
               WHERE {status_sql} AND DATE(created_at) >= ? AND DATE(created_at) <= ?
               GROUP BY DATE(created_at)
               ORDER BY day""",
            (first, last),
        )
        rows = c.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_return_totals_for_month(self, year, month):
        from calendar import monthrange
        first = f"{year:04d}-{month:02d}-01"
        last = f"{year:04d}-{month:02d}-{monthrange(year, month)[1]}"
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(
            """SELECT COUNT(*) as count,
                      COALESCE(SUM(subtotal),0) as subtotal,
                      COALESCE(SUM(vat_amount),0) as vat,
                      COALESCE(SUM(total),0) as total
               FROM invoices
               WHERE status='returned' AND DATE(created_at) >= ? AND DATE(created_at) <= ?""",
            (first, last),
        )
        row = c.fetchone()
        conn.close()
        return dict(row) if row else {"count": 0, "subtotal": 0, "vat": 0, "total": 0}

    def update_invoice_status(self, invoice_id, status):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("UPDATE invoices SET status=? WHERE id=?", (status, invoice_id))
        conn.commit()
        conn.close()

    def hard_delete_invoice(self, invoice_id):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM invoice_items WHERE invoice_id=?", (invoice_id,))
        c.execute("DELETE FROM invoices WHERE id=?", (invoice_id,))
        conn.commit()
        conn.close()

    # ─────────── Backup ───────────

    def backup_database(self, dest_path):
        if os.path.exists(self.db_path):
            shutil.copy2(self.db_path, dest_path)
            conn = self._get_conn()
            c = conn.cursor()
            c.execute(
                "INSERT INTO backup_log (file_path) VALUES (?)", (dest_path,)
            )
            conn.commit()
            conn.close()
            return True
        return False

    def restore_database(self, src_path):
        if os.path.exists(src_path):
            shutil.copy2(src_path, self.db_path)
            return True
        return False
