#!/usr/bin/env python
"""
GUI tool for generating POS_System license files.
"""

import json
import os
import sys
import threading
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import customtkinter as ctk
from license_utils import list_removable_drives, _sign

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")


class LicenseGeneratorGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        # تم إعادتها للوضع الصحيح تماماً لتقرأ بشكل سليم في شريط العنوان
        self.title("أداة توليد مفاتيح التفعيل – POS_System")
        self.resizable(False, False)

        w, h = 520, 600
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self._build_ui()
        self._refresh_drives()
        self.after(2000, self._refresh_drives_loop)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(padx=25, pady=20, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)

        # Title - تم إعادتها للترتيب الطبيعي لتقرأ بشكل صحيح في الواجهة
        ctk.CTkLabel(main, text="توليد مفتاح التفعيل", font=("Arial", 22, "bold")).grid(row=0, pady=(0, 5))
        ctk.CTkLabel(main, text="برنامج نظام البيع", font=("Arial", 13), text_color="gray").grid(row=1, pady=(0, 20))

        # Customer - تعديل التسمية والـ placeholder ليكون مضبوطاً حسب رغبتك
        ctk.CTkLabel(main, text="*الزبون اسم", anchor="e").grid(row=2, sticky="ew")
        self.entry_customer = ctk.CTkEntry(main, placeholder_text="للتجارة النور مؤسسة :مثال", justify="right")
        self.entry_customer.grid(row=3, sticky="ew", pady=(0, 12))

        # Duration
        ctk.CTkLabel(main, text="الترخيص مدة", anchor="e").grid(row=4, sticky="ew")
        dur_frame = ctk.CTkFrame(main, fg_color="transparent")
        dur_frame.grid(row=5, sticky="ew", pady=(0, 5))
        dur_frame.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.dur_var = ctk.StringVar(value="3")
        self.dur_var.trace_add("write", lambda *_: self.entry_days.delete(0, "end") if self.dur_var.get() != "days" else None)
        
        duration_options = [
            ("شهر", "1"),
            ("أشهر ٣", "3"),
            ("أشهر ٦", "6"),
            ("سنة", "12"),
            ("أيام", "days")
        ]
        
        for i, (label, val) in enumerate(duration_options):
            rb = ctk.CTkRadioButton(dur_frame, text=label, variable=self.dur_var, value=val)
            rb.grid(row=0, column=4 - i, padx=2, sticky="w")

        # Custom days row
        self.days_frame = ctk.CTkFrame(main, fg_color="transparent")
        self.days_frame.grid(row=6, sticky="ew", pady=(5, 12))
        self.days_frame.grid_columnconfigure(0, weight=1)

        self.entry_days = ctk.CTkEntry(self.days_frame, placeholder_text="45 :مثال", justify="right")
        self.entry_days.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        ctk.CTkLabel(self.days_frame, text=":الأيام عدد", width=80, anchor="e").grid(row=0, column=1)
        self.entry_days.bind("<KeyRelease>", lambda e: self.dur_var.set("days") if self.entry_days.get().strip() else None)

        # License ID - تم ضبط صياغة النص هنا لكي يظهر متناسقاً ولا يتداخل
        ctk.CTkLabel(main, text="(تلقائياً يُولد – اختياري) الترخيص معرف", anchor="e").grid(row=7, sticky="ew")
        self.entry_id = ctk.CTkEntry(main, placeholder_text="LIC-20260607-001 :مثال", justify="right")
        self.entry_id.grid(row=8, sticky="ew", pady=(0, 12))

        # USB Drive
        ctk.CTkLabel(main, text="الوجهة", anchor="e").grid(row=9, sticky="ew")
        drive_frame = ctk.CTkFrame(main, fg_color="transparent")
        drive_frame.grid(row=10, sticky="ew", pady=(0, 12))
        drive_frame.grid_columnconfigure(1, weight=1)

        self.btn_refresh = ctk.CTkButton(drive_frame, text="تحديث", width=70, command=self._refresh_drives)
        self.btn_refresh.grid(row=0, column=0, padx=(0, 8))

        self.drive_combo = ctk.CTkOptionMenu(drive_frame, values=["-- اختر --"], dynamic_resizing=False)
        self.drive_combo.grid(row=0, column=1, sticky="ew")

        # Status / Log
        self.log_box = ctk.CTkTextbox(main, height=80, wrap="word", state="disabled", font=("Consolas", 11))
        self.log_box.grid(row=11, sticky="ew", pady=(10, 12))

        # Generate button - تم إعادتها للترتيب الطبيعي لتظهر صحيحة على الزر
        self.btn_generate = ctk.CTkButton(
            main, text="توليد مفتاح التفعيل", height=42,
            font=("Arial", 15, "bold"), command=self._generate
        )
        self.btn_generate.grid(row=12, sticky="ew")

    def _log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _refresh_drives(self):
        drives = list_removable_drives()
        current = self.drive_combo.get()

        if drives:
            items = [f"{d}\\ -> pos_license.lic" for d in drives]
            self.drive_combo.configure(values=items)
            if current not in items:
                self.drive_combo.set(items[0])
        else:
            # تم إعادتها طبيعية لتقرأ داخل القائمة بشكل سليم
            self.drive_combo.configure(values=["-- فلاشة توجد لا --"])
            self.drive_combo.set("-- فلاشة توجد لا --")

        # Color removed; the values text is sufficient feedback

    def _refresh_drives_loop(self):
        self._refresh_drives()
        self.after(3000, self._refresh_drives_loop)

    def _generate(self):
        customer = self.entry_customer.get().strip()
        if not customer:
            self._log("[!] الرجاء إدخال اسم الزبون.")
            return

        dur_val = self.dur_var.get()
        if dur_val == "days":
            try:
                days = int(self.entry_days.get().strip())
            except ValueError:
                self._log("[!] الرجاء إدخال عدد أيام صحيح.")
                return
        else:
            try:
                days = int(dur_val) * 30
            except ValueError:
                days = 90

        license_id = self.entry_id.get().strip()
        if not license_id:
            license_id = f"LIC-{datetime.now().strftime('%Y%m%d')}-{datetime.now().strftime('%H%M%S')}"

        drive_sel = self.drive_combo.get()
        if not drive_sel or "لا توجد" in drive_sel:
            self._log("[!] لا توجد فلاشة USB متصلة.")
            return

        drive_letter = drive_sel.split("\\")[0] + "\\"
        out_path = os.path.join(drive_letter, "pos_license.lic")

        self.btn_generate.configure(state="disabled", text="جاري التوليد...")

        def task():
            try:
                expires = datetime.now() + timedelta(days=days)
                data = {
                    "license_id": license_id,
                    "product": "POS_System",
                    "created_at": datetime.now().isoformat(),
                    "expires_at": expires.isoformat(),
                    "issued_to": customer,
                    "duration_days": days,
                }
                data["signature"] = _sign(data)

                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                msg = (
                    "[OK] تم حفظ الترخيص على " + out_path + "\n"
                    "     المعرف: " + license_id + "\n"
                    "     الزبون:  " + customer + "\n"
                    "     ينتهي:   " + expires.strftime('%Y-%m-%d')
                )
                self.after(0, lambda: self._log(msg))
            except Exception as e:
                self.after(0, lambda: self._log(f"[خطأ] {e}"))
            finally:
                self.after(0, lambda: self.btn_generate.configure(state="normal", text="توليد مفتاح التفعيل"))

        threading.Thread(target=task, daemon=True).start()


if __name__ == "__main__":
    LicenseGeneratorGUI().mainloop()