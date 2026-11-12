# Daily Sales Email Summary

This Windows-based script reads sales and stock CSV files, calculates a daily
summary, and emails it as HTML through Gmail SMTP.

## What it reports

- Total sales revenue in KES
- Number of distinct transactions
- Top-selling item by units sold
- Items below their restock levels

## Files

- `Email_Summary_Script.py` — report, email, and Windows scheduling logic
- `sales.csv` — sample sales data; each row is an item on a transaction
- `inventory.csv` — current stock and restock level for each item
- `.env` — Gmail credentials (kept out of source control)

The script counts distinct `transaction_id` values, so multiple items from one
checkout count as a single transaction. It currently summarizes every row in
`sales.csv`; keep that file limited to the reporting day, or rotate/archive it
daily before adding the next day's sales.

## Setup and use

Use Python 3.10 or later. No third-party Python packages are required. Add these
entries to `.env`:

```dotenv
GMAIL_ADDRESS=your-shop-gmail@gmail.com
GMAIL_APP_PASSWORD=your-16-character-app-password
REPORT_TO_EMAIL=recipient@example.com
```

`REPORT_TO_EMAIL` is optional and defaults to `GMAIL_ADDRESS`. Use a Gmail
App Password, not the account's normal password. Keep `.env` private and never
share or commit it.

Preview the summary without sending:

```powershell
python .\Email_Summary_Script.py --dry-run
```

Send the email immediately:

```powershell
python .\Email_Summary_Script.py
```

Register a Windows Task Scheduler task for 6:00 PM each day:

```powershell
python .\Email_Summary_Script.py --install-schedule
```

The scheduled task uses the computer's local time. Set the Windows time zone to
**(UTC+03:00) Nairobi** for a 6:00 PM East Africa Time run. The computer must be
available and connected to the internet at the scheduled time. Gmail accepting
the SMTP message does not guarantee inbox placement; check Spam if it is not in
the inbox.

## Example build price

For a typical independent Nairobi shop, I would quote **KES 15,000 as a
one-off implementation fee** for this small, local automation. That price
assumes a single shop, one sales CSV format, one inventory CSV, one Gmail
mailbox, a Windows computer, and a short handover. It covers configuring the
report, validating the CSV workflow, setting up the scheduled task, and
documenting how to use it. It excludes computer repairs, internet or Gmail
charges, data cleanup beyond the agreed CSV format, and new features.

I would **not require a monthly retainer** for the basic script: it runs on the
shop's computer and does not need a hosted service. I would offer an optional
**KES 3,000 per month support plan**, covering up to one hour of remote help
with the existing workflow, configuration, or troubleshooting. New features,
additional branches, and major changes would be quoted separately. These are
indicative example rates, not a binding quote; the final price depends on the
shop's actual data and support needs.
