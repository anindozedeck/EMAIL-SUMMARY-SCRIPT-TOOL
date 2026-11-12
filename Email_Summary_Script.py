"""Email a daily retail sales summary using Gmail SMTP."""

from __future__ import annotations

import argparse
import csv
import html
import os
import smtplib
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
SALES_FILE = BASE_DIR / "sales.csv"
INVENTORY_FILE = BASE_DIR / "inventory.csv"
EAT = timezone(timedelta(hours=3), name="EAT")
GMAIL_SMTP_HOST = "smtp.gmail.com"
GMAIL_SMTP_PORT = 465


@dataclass(frozen=True)
class InventoryItem:
    stock_on_hand: int
    restock_level: int


@dataclass(frozen=True)
class DailySummary:
    revenue: Decimal
    transaction_count: int
    top_item: str
    top_item_quantity: int
    restock_items: list[tuple[str, int, int]]


def load_env(env_path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding process environment."""
    if not env_path.exists():
        return

    with env_path.open(encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if value[:1] == value[-1:] and value.startswith(("'", '"')):
                value = value[1:-1]
            os.environ.setdefault(key, value)


def read_inventory(path: Path) -> dict[str, InventoryItem]:
    inventory: dict[str, InventoryItem] = {}
    with path.open(newline="", encoding="utf-8-sig") as inventory_file:
        reader = csv.DictReader(inventory_file)
        required = {"item_name", "stock_on_hand", "restock_level"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"{path.name} must contain columns: "
                + ", ".join(sorted(required))
            )
        for line_number, row in enumerate(reader, start=2):
            name = (row["item_name"] or "").strip()
            if not name:
                raise ValueError(f"{path.name}:{line_number}: item_name is required")
            if name in inventory:
                raise ValueError(f"{path.name}:{line_number}: duplicate item {name!r}")
            try:
                stock = int(row["stock_on_hand"])
                level = int(row["restock_level"])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{path.name}:{line_number}: stock and restock level must be integers"
                ) from error
            if stock < 0 or level < 0:
                raise ValueError(
                    f"{path.name}:{line_number}: stock and restock level cannot be negative"
                )
            inventory[name] = InventoryItem(stock, level)
    return inventory


def summarize_sales(sales_path: Path, inventory_path: Path) -> DailySummary:
    inventory = read_inventory(inventory_path)
    item_quantities: defaultdict[str, int] = defaultdict(int)
    transactions: set[str] = set()
    revenue = Decimal("0")

    with sales_path.open(newline="", encoding="utf-8-sig") as sales_file:
        reader = csv.DictReader(sales_file)
        required = {"transaction_id", "item_name", "quantity_sold", "price"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(
                f"{sales_path.name} must contain columns: "
                + ", ".join(sorted(required))
            )
        for line_number, row in enumerate(reader, start=2):
            transaction_id = (row["transaction_id"] or "").strip()
            name = (row["item_name"] or "").strip()
            if not transaction_id or not name:
                raise ValueError(
                    f"{sales_path.name}:{line_number}: transaction_id and item_name are required"
                )
            try:
                quantity = int(row["quantity_sold"])
                price = Decimal(row["price"])
            except (TypeError, ValueError, InvalidOperation) as error:
                raise ValueError(
                    f"{sales_path.name}:{line_number}: quantity_sold must be an integer "
                    "and price must be a number"
                ) from error
            if quantity <= 0 or not price.is_finite() or price < 0:
                raise ValueError(
                    f"{sales_path.name}:{line_number}: quantity must be positive "
                    "and price must be a non-negative number"
                )
            if name not in inventory:
                raise ValueError(
                    f"{sales_path.name}:{line_number}: {name!r} is missing from "
                    f"{inventory_path.name}"
                )

            transactions.add(transaction_id)
            item_quantities[name] += quantity
            revenue += quantity * price

    if not transactions:
        raise ValueError(f"{sales_path.name} contains no sales rows")

    top_item = min(item_quantities, key=lambda name: (-item_quantities[name], name))
    restock_items = sorted(
        (
            (name, item.stock_on_hand, item.restock_level)
            for name, item in inventory.items()
            if item.stock_on_hand < item.restock_level
        ),
        key=lambda item: item[0].casefold(),
    )
    return DailySummary(
        revenue=revenue,
        transaction_count=len(transactions),
        top_item=top_item,
        top_item_quantity=item_quantities[top_item],
        restock_items=restock_items,
    )


def build_email(summary: DailySummary, report_date: str) -> tuple[str, str, str]:
    subject = f"Daily Sales Summary — {report_date}"
    if summary.restock_items:
        restock_html = "<ul>" + "".join(
            "<li>{}: {} left (restock at {})</li>".format(
                html.escape(name), stock, level
            )
            for name, stock, level in summary.restock_items
        ) + "</ul>"
        restock_text = "; ".join(
            f"{name}: {stock} left (restock at {level})"
            for name, stock, level in summary.restock_items
        )
        restock_status = "RESTOCK REQUIRED"
    else:
        restock_html = "<p>All items are at or above their restock levels.</p>"
        restock_text = "All items are at or above their restock levels."
        restock_status = "No restock needed"

    content = f"""\
    <html>
      <body style="font-family: Arial, sans-serif; color: #222;">
        <h2>Daily Sales Summary</h2>
        <p>{html.escape(report_date)} (East Africa Time)</p>
        <table style="border-collapse: collapse;">
          <tr><th align="left" style="padding: 6px;">Metric</th>
              <th align="left" style="padding: 6px;">Today's result</th></tr>
          <tr><td style="padding: 6px;">Total revenue</td>
              <td style="padding: 6px;">KES {summary.revenue:,.2f}</td></tr>
          <tr><td style="padding: 6px;">Number of transactions</td>
              <td style="padding: 6px;">{summary.transaction_count}</td></tr>
          <tr><td style="padding: 6px;">Top-selling item</td>
              <td style="padding: 6px;">{html.escape(summary.top_item)}
              ({summary.top_item_quantity} units)</td></tr>
          <tr><td style="padding: 6px;">Restock flag</td>
              <td style="padding: 6px;">{restock_status}</td></tr>
        </table>
        <h3>Items below restock level</h3>
        {restock_html}
      </body>
    </html>
    """
    plain_text = (
        f"Daily Sales Summary — {report_date} (East Africa Time)\n"
        f"Total revenue: KES {summary.revenue:,.2f}\n"
        f"Number of transactions: {summary.transaction_count}\n"
        f"Top-selling item: {summary.top_item} ({summary.top_item_quantity} units)\n"
        f"Restock flag: {restock_status}\n"
        f"Items below restock level: {restock_text}\n"
    )
    return subject, plain_text, content


def send_email(subject: str, plain_text: str, html_content: str) -> None:
    sender = os.environ.get("GMAIL_ADDRESS", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
    recipient = os.environ.get("REPORT_TO_EMAIL", sender).strip()
    if not sender or not password:
        raise ValueError("Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the .env file")
    parsed_recipient = parseaddr(recipient)[1]
    if not parsed_recipient or "@" not in parsed_recipient:
        raise ValueError("Set a valid REPORT_TO_EMAIL or GMAIL_ADDRESS in the .env file")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = parsed_recipient
    message.set_content(plain_text)
    message.add_alternative(html_content, subtype="html")

    with smtplib.SMTP_SSL(
        GMAIL_SMTP_HOST, GMAIL_SMTP_PORT, timeout=30
    ) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
    print("Gmail accepted the sales-summary email for delivery.")


def install_daily_schedule() -> None:
    if sys.platform != "win32":
        raise RuntimeError("The built-in daily schedule installer requires Windows.")
    task_command = f'"{sys.executable}" "{Path(__file__).resolve()}"'
    subprocess.run(
        [
            "schtasks.exe",
            "/Create",
            "/SC",
            "DAILY",
            "/ST",
            "18:00",
            "/TN",
            "Nairobi Daily Sales Summary",
            "/TR",
            task_command,
            "/F",
        ],
        check=True,
    )
    print("Scheduled for 6:00 PM computer-local time each day.")
    print("Set the computer's time zone to (UTC+03:00) Nairobi for 6:00 PM EAT.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="calculate and print the summary without sending email",
    )
    mode.add_argument(
        "--install-schedule",
        action="store_true",
        help="schedule this script to run daily at 6:00 PM local time on Windows",
    )
    args = parser.parse_args()

    if args.install_schedule:
        install_daily_schedule()
        return

    load_env(BASE_DIR / ".env")
    summary = summarize_sales(SALES_FILE, INVENTORY_FILE)
    report_date = datetime.now(EAT).strftime("%Y-%m-%d")
    subject, plain_text, html_content = build_email(summary, report_date)

    if args.dry_run:
        print(plain_text, end="")
        return
    send_email(subject, plain_text, html_content)


if __name__ == "__main__":
    main()