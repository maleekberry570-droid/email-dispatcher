import os
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from supabase import create_client
import spintax

# 1. Connect to Supabase Database
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# 2. Get Inframail SMTP Credentials
inbox_user = os.environ["INBOX_USER"]
inbox_pass = os.environ["INBOX_PASS"]

def parse_spintax_and_vars(text, row):
    text = text.replace("[first_name]", str(row.get("first_name", "")))
    text = text.replace("[sender_name]", str(row.get("sender_name", "")))
    return spintax.spin(text)

# Fetch up to 5 pending leads from the queue
response = supabase.table("campaign_queue").select("*").eq("status", "pending").limit(5).execute()
pending_rows = response.data

if pending_rows:
    for row in pending_rows:
        recipient = row["recipient_email"]
        sender_display_name = str(row.get("sender_name", "")).strip()
        
        msg = MIMEMultipart()
        msg["From"] = f'"{sender_display_name}" <{inbox_user}>' if sender_display_name else inbox_user
        msg["To"] = recipient
        msg["Subject"] = parse_spintax_and_vars(row["subject_template"], row)
        msg.attach(MIMEText(parse_spintax_and_vars(row["body_template"], row), "plain"))
        
        try:
            # Connect directly to Inframail SMTP on port 587
            server = smtplib.SMTP("smtp.inframail.io", 587, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(inbox_user, inbox_pass)
            server.sendmail(inbox_user, recipient, msg.as_string())
            server.quit()
            
            # Update status in database
            supabase.table("campaign_queue").update({"status": "sent"}).eq("id", row["id"]).execute()
            print(f"Successfully sent to {recipient}")
            
            time.sleep(120)  # Enforce 2-minute gap between dispatches
        except Exception as e:
            print(f"Failed sending to {recipient}: {e}")
            supabase.table("campaign_queue").update({"status": f"failed: {e}"}).eq("id", row["id"]).execute()
