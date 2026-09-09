import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from supabase import create_client

# Initialize Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Collect all configured inboxes from environment variables
INBOXES = []
for i in range(1, 11):
    user = os.environ.get(f"INBOX_{i}_EMAIL")
    pwd = os.environ.get(f"INBOX_{i}_PASS")
    if user and pwd:
        INBOXES.append({"username": user.strip(), "password": pwd.strip()})

if not INBOXES:
    raise ValueError("No valid inboxes configured in environment variables!")

def send_email(to_email, subject, body, inbox):
    msg = MIMEMultipart()
    msg['From'] = inbox['username']
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))

    # Inframail SMTP Server Settings
    server = smtplib.SMTP('smtp.inframail.io', 587)
    server.starttls()
    server.login(inbox['username'], inbox['password'])
    server.sendmail(inbox['username'], to_email, msg.as_string())
    server.quit()

def process_queue():
    # Fetch pending leads from Supabase queue
    response = supabase.table("email_queue").select("*").eq("status", "pending").limit(50).execute()
    leads = response.data

    if not leads:
        print("No pending emails to send.")
        return

    print(f"Found {len(leads)} pending emails.")
    
    inbox_index = 0
    for lead in leads:
        inbox = INBOXES[inbox_index % len(INBOXES)]
        try:
            send_email(lead['email'], lead['subject'], lead['body'], inbox)
            supabase.table("email_queue").update({"status": "sent"}).eq("id", lead['id']).execute()
            print(f"Successfully sent email to {lead['email']} via {inbox['username']}")
        except Exception as e:
            print(f"Failed to send to {lead['email']}: {e}")
            supabase.table("email_queue").update({"status": "failed", "error": str(e)}).eq("id", lead['id']).execute()
            
        inbox_index += 1

if __name__ == "__main__":
    process_queue()
