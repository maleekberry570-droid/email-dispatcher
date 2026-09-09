import os
import json
import random
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from supabase import create_client
import spintax

# 1. Connect to Supabase
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# 2. Load Multiple Inboxes from JSON secret
inboxes = json.loads(os.environ["INBOXES_JSON"])
DAILY_LIMIT = 30

def parse_spintax_and_vars(text, row):
    text = text.replace("[first_name]", str(row.get("first_name", "")))
    text = text.replace("[sender_name]", str(row.get("sender_name", "")))
    return spintax.spin(text)

# Fetch pending leads
response = supabase.table("campaign_queue").select("*").eq("status", "pending").limit(5).execute()
pending_rows = response.data

if pending_rows:
    for row in pending_rows:
        # Pick a random inbox from your configured list
        selected_inbox = random.choice(inboxes)
        inbox_user = selected_inbox["username"]
        inbox_pass = selected_inbox["password"]
        
        recipient = row["recipient_email"]
        sender_display_name = str(row.get("sender_name", "")).strip()
        
        msg = MIMEMultipart()
        msg["From"] = f'"{sender_display_name}" <{inbox_user}>' if sender_display_name else inbox_user
        msg["To"] = recipient
        msg["Subject"] = parse_spintax_and_vars(row["subject_template"], row)
        msg.attach(MIMEText(parse_spintax_and_vars(row["body_template"], row), "plain"))
        
        try:
            server = smtplib.SMTP("smtp.inframail.io", 587, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(inbox_user, inbox_pass)
            server.sendmail(inbox_user, recipient, msg.as_string())
            server.quit()
            
            supabase.table("campaign_queue").update({"status": "sent"}).eq("id", row["id"]).execute()
            print(f"Sent to {recipient} using {inbox_user}")
            
            time.sleep(120)  # 2-minute gap
        except Exception as e:
            print(f"Failed sending to {recipient}: {e}")
            supabase.table("campaign_queue").update({"status": f"failed: {e}"}).eq("id", row["id"]).execute()
