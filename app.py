import csv
import io
import random
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Dynamic Email Dispatcher", page_icon="✉️", layout="wide"
)

st.title("✉️ Inframail Outreach Dispatcher")
st.markdown(
    "Upload your CSV. Emails rotate across active inboxes (capped at **30 sends/day** per inbox)."
)

# ==========================================
# 1. LOAD INFRAMAIL INBOXES & TRACK COUNTS
# ==========================================
SMTP_HOST = "smtp.inframail.io"
SMTP_PORT = 587
DAILY_INBOX_LIMIT = 30  # Safety sending limit per inbox

inboxes = st.secrets.get("inboxes", [])

if not inboxes:
    st.error(
        "⚠️ No Inframail inboxes found! Configure `st.secrets` before running."
    )
    st.stop()

# Initialize daily send counters in session state
if "send_counts" not in st.session_state:
    st.session_state.send_counts = {acc["username"]: 0 for acc in inboxes}

# Sidebar overview of inbox statuses
st.sidebar.subheader("Active Inboxes & Daily Capacities")
for acc in inboxes:
    user = acc["username"]
    count = st.session_state.send_counts.get(user, 0)
    st.sidebar.text(f"• {user}: {count}/{DAILY_INBOX_LIMIT} sent")

if st.sidebar.button("Reset Daily Counters"):
    st.session_state.send_counts = {acc["username"]: 0 for acc in inboxes}
    st.rerun()

# ==========================================
# 2. FILE UPLOADER & PROCESSING
# ==========================================
uploaded_file = st.file_uploader(
    "Choose a CSV file", type=["csv"], help="CSV must contain required columns"
)

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    required_cols = [
        "Recipient_Email",
        "From_Display_Name",
        "Sender_Signature",
        "Subject",
    ]
    missing_cols = [c for c in required_cols if c not in df.columns]

    if missing_cols:
        st.error(
            f"❌ Missing required CSV columns: `{', '.join(missing_cols)}`"
        )
    else:
        st.write("### Data Preview", df.head(5))

        st.sidebar.markdown("---")
        st.sidebar.subheader("Pacing Controls")
        min_delay = st.sidebar.slider("Min Delay (seconds)", 1, 10, 2)
        max_delay = st.sidebar.slider("Max Delay (seconds)", 3, 30, 5)

        if st.button(f"🚀 Start Sending ({len(df)} Emails)"):
            progress_bar = st.progress(0)
            status = st.empty()
            total_leads = len(df)
            success_count = 0
            failed_count = 0

            for i, row in df.iterrows():
                # Filter inboxes that haven't hit the daily cap (30 sends)
                eligible_inboxes = [
                    acc
                    for acc in inboxes
                    if st.session_state.send_counts[acc["username"]]
                    < DAILY_INBOX_LIMIT
                ]

                if not eligible_inboxes:
                    st.error(
                        f"🛑 All inboxes have reached their daily limit of {DAILY_INBOX_LIMIT} emails! Process paused."
                    )
                    break

                # Pick a random eligible inbox to balance sending loads
                selected_inbox = random.choice(eligible_inboxes)
                inbox_user = selected_inbox["username"]
                inbox_pass = selected_inbox["password"]

                recipient = row["Recipient_Email"]
                from_name = row["From_Display_Name"]
                sig_name = row["Sender_Signature"]
                subject = row["Subject"]

                # Email Body with Dynamic Sign-Off
                html_body = f"""
                <p>Hi there,</p>
                <p>I hope this email finds you well.</p>
                <br>
                <p>Best regards,</p>
                <p><b>{sig_name}</b></p>
                """

                # Email Headers with Dynamic From Display Name
                msg = MIMEMultipart()
                msg["From"] = f'"{from_name}" <{inbox_user}>'
                msg["To"] = recipient
                msg["Subject"] = subject
                msg.attach(MIMEText(html_body, "html"))

                try:
                    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
                    server.starttls()
                    server.login(inbox_user, inbox_pass)
                    server.sendmail(inbox_user, recipient, msg.as_string())
                    server.quit()

                    # Increment inbox count on success
                    st.session_state.send_counts[inbox_user] += 1
                    success_count += 1

                    status.info(
                        f"[{i+1}/{total_leads}] Sent to **{recipient}** as **'{from_name}'** via `{inbox_user}` "
                        f"({st.session_state.send_counts[inbox_user]}/{DAILY_INBOX_LIMIT})"
                    )

                except Exception as e:
                    failed_count += 1
                    st.error(f"Failed to send to {recipient}: {e}")

                progress_bar.progress((i + 1) / total_leads)
                time.sleep(random.uniform(min_delay, max_delay))

            st.success(
                f"🎉 Task run complete! Sent: {success_count} | Failed: {failed_count}"
            )
