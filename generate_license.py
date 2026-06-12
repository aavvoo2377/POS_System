#!/usr/bin/env python
"""
License generation tool for POS_System.
Produces a signed license file on a USB flash drive or local path.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from license_utils import list_removable_drives, _sign


def generate_license(
    customer: str,
    months: int = 3,
    days: int = 0,
    license_id: str = "",
    output: str = "",
    filename: str = "pos_license.lic",
) -> str:
    if not license_id:
        now = datetime.now()
        license_id = f"LIC-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}"

    expires = datetime.now() + timedelta(days=days or months * 30)

    data = {
        "license_id": license_id,
        "product": "POS_System",
        "created_at": datetime.now().isoformat(),
        "expires_at": expires.isoformat(),
        "issued_to": customer.strip(),
    }

    data["signature"] = _sign(data)

    if output:
        out_path = output
    else:
        drives = list_removable_drives()
        if not drives:
            print("[!] No removable drives found.")
            print("    Plug in a USB flash drive or use --output to specify a path.")
            return ""
        out_path = os.path.join(drives[0], filename)
        print(f"[i] Writing to first removable drive: {drives[0]}")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[OK] License saved to: {out_path}")
    print(f"     License ID: {data['license_id']}")
    print(f"     Customer:   {data['issued_to']}")
    print(f"     Expires:    {data['expires_at']}")
    return out_path


def list_usb():
    drives = list_removable_drives()
    if drives:
        print("Removable drives found:")
        for d in drives:
            print(f"  {d}")
    else:
        print("No removable drives found.")


def interactive_mode():
    """Interactive prompts when run without arguments."""
    print("=" * 50)
    print("     POS_System – License Generator")
    print("=" * 50)
    print()

    while True:
        customer = input("Customer name: ").strip()
        if customer:
            break
        print("  [!] Customer name is required.")

    while True:
        try:
            m = input("Duration in months (default 3): ").strip()
            months = int(m) if m else 3
            if months > 0:
                break
            print("  [!] Must be > 0.")
        except ValueError:
            print("  [!] Enter a number.")

    drives = list_removable_drives()
    if drives:
        print("\nAvailable USB drives:")
        for i, d in enumerate(drives):
            print(f"  [{i + 1}] {d}")
        print(f"  [0] Specify a different path")
        choice = input(f"\nSelect drive [1] or 0 for custom path: ").strip()
        if choice == "0" or not choice:
            out = input("Output path (full path + filename): ").strip()
            output = out if out else ""
        else:
            try:
                idx = int(choice) - 1
                output = os.path.join(drives[idx], "pos_license.lic")
                print(f"  -> {output}")
            except (ValueError, IndexError):
                output = ""
                print("  Invalid, using custom path.")
                out = input("Output path: ").strip()
                output = out if out else ""
    else:
        print("\n[!] No USB drives detected.")
        output = input("Output path (full path + filename): ").strip()

    print()
    generate_license(customer=customer, months=months, output=output)

    print()
    input("Press Enter to exit...")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        interactive_mode()
        sys.exit(0)

    parser = argparse.ArgumentParser(description="Generate POS_System license file")
    parser.add_argument("--customer", "-c", help="Customer name")
    parser.add_argument("--months", "-m", type=int, default=3, help="Duration in months (default: 3)")
    parser.add_argument("--days", "-d", type=int, default=0, help="Extra days")
    parser.add_argument("--id", help="License ID (auto if omitted)")
    parser.add_argument("--output", "-o", help="Output path (default: first USB drive)")
    parser.add_argument("--filename", "-f", default="pos_license.lic", help="Filename on USB (default: pos_license.lic)")
    parser.add_argument("--list-usb", "-l", action="store_true", help="List removable drives")

    args = parser.parse_args()

    if args.list_usb:
        list_usb()
        input("\nPress Enter to exit...")
        sys.exit(0)

    if not args.customer:
        parser.print_help()
        print("\n[!] --customer is required")
        input("\nPress Enter to exit...")
        sys.exit(1)

    generate_license(
        customer=args.customer,
        months=args.months,
        days=args.days,
        license_id=args.id or "",
        output=args.output or "",
        filename=args.filename,
    )

    print()
    input("Press Enter to exit...")
