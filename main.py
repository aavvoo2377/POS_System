#!/usr/bin/env python3
import sys
import os
import tkinter as tk
from tkinter import messagebox
from datetime import datetime

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from license_utils import check_status, scan_license_file, activate_from_file, days_remaining


def _show_expired():
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "انتهاء الترخيص",
        "انتهت صلاحية ترخيص البرنامج.\n"
        "يرجى التواصل مع المورد لتجديد الاشتراك.",
    )
    root.destroy()
    sys.exit(0)


def _show_warning(days: int):
    root = tk.Tk()
    root.withdraw()
    messagebox.showwarning(
        "تنبيه الترخيص",
        f"باقي {days} يوم على انتهاء الترخيص.\n"
        "يرجى التواصل مع المورد للتجديد.",
    )
    root.destroy()


def _run_activation_dialog() -> bool:
    import customtkinter as ctk

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    result = [False]

    def on_close():
        if messagebox.askyesno("خروج", "البرنامج غير مفعل. هل تريد الخروج؟"):
            win.destroy()
            sys.exit(0)

    def try_activate():
        status_label.configure(text="جاري فحص الفلاشات...", text_color="gray")
        win.update()
        path = scan_license_file()
        if not path:
            status_label.configure(
                text="لم يتم العثور على فلاشة فيها ملف التفعيل.\n"
                      "يرجى توصيل الفلاشة التي فيها ملف الترخيص.",
                text_color="red",
            )
            return
        ok, msg = activate_from_file(path)
        if ok:
            status_label.configure(text=msg, text_color="green")
            scan_btn.configure(state="disabled", text="تم التفعيل ✓")
            win.after(1500, lambda: (win.destroy(), result.update([True])))
        else:
            status_label.configure(text=msg, text_color="red")

    win = ctk.CTk()
    win.title("تفعيل البرنامج")
    win.geometry("500x300")
    win.resizable(False, False)
    win.protocol("WM_DELETE_WINDOW", on_close)

    ctk.CTkLabel(
        win, text="POS System - تفعيل الترخيص",
        font=("Arial", 18, "bold"),
    ).pack(pady=(30, 10))

    ctk.CTkLabel(
        win, text="قم بتوصيل الفلاشة التي تحوي ملف التفعيل\nثم اضغط على الزر أدناه",
        font=("Arial", 13),
        justify="center",
    ).pack(pady=(0, 20))

    scan_btn = ctk.CTkButton(
        win, text="🔍 فحص الفلاشة وتفعيل البرنامج",
        font=("Arial", 14),
        width=300, height=45,
        command=try_activate,
        fg_color="#1565c0", hover_color="#0d47a1",
    )
    scan_btn.pack(pady=10)

    status_label = ctk.CTkLabel(
        win, text="", font=("Arial", 12), justify="center",
    )
    status_label.pack(pady=10)

    ctk.CTkLabel(
        win, text="")
    
    ctk.CTkButton(
        win, text="إلغاء", font=("Arial", 13),
        width=100, fg_color="#999999",
        command=on_close,
    ).pack(pady=10)

    win.mainloop()
    return result[0]


def main():
    status, act = check_status()

    if status == "expired":
        _show_expired()
        return

    if status == "not_activated":
        ok = _run_activation_dialog()
        if not ok:
            return
        # Re-check after activation
        status, act = check_status()
        if status != "active":
            _show_expired()
            return

    # Show warning if < 7 days remaining
    if act and (rem := days_remaining(act)) <= 7:
        _show_warning(rem)

    # Normal startup
    from database import Database
    from ui.main_window import MainWindow

    db = Database()
    app = MainWindow(db)
    app.mainloop()


if __name__ == "__main__":
    main()
