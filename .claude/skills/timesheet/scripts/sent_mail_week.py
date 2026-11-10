# sent_mail_week.py — list Sent Items since a date via Outlook COM (edit the Restrict date).
import sys, win32com.client
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ns = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
items = ns.GetDefaultFolder(5).Items
items.Sort("[SentOn]", True)
items = items.Restrict("[SentOn] >= '11/02/2026 12:00 AM'")
for m in items:
    try:
        to = m.To[:50]
        body = " ".join(m.Body.split())[:160]
        print(f"{m.SentOn:%a %m/%d %H:%M} | {to} | {m.Subject} | {body}")
    except Exception as e: pass
