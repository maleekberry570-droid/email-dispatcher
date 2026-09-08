import csv
import io
import random
import re
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Dynamic Email Dispatcher", page_icon="✉️", layout="wide"
)

st.title("✉️ Outreach Dispatcher with Spintax")
st.markdown(
    "Upload your CSV containing `email`, `first_name`, and `sender_name` columns."
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

# Initialize dynamic session variables for tracking across reruns
if "send_counts" not in st.session_state:
    st.session_state.send_counts = {acc["username"]: 0 for acc in inboxes}
if "sending_active" not in st.session_state:
    st.session_state.sending_active = False
if "current_index" not in st.session_state:
    st.session_state.current_index = 0
if "success_count" not in st.session_state:
    st.session_state.success_count = 0
if "failed_count" not in st.session_state:
    st.session_state.failed_count = 0

# Sidebar overview of inbox statuses
st.sidebar.subheader("Active Inboxes & Daily Capacities")
for acc in inboxes:
    user = acc["username"]
    count = st.session_state.send_counts.get(user, 0)
    st.sidebar.text(f"• {user}: {count}/{DAILY_INBOX_LIMIT} sent")

if st.sidebar.button("Reset Daily Counters"):
    st.session_state.send_counts = {acc["username"]: 0 for acc in inboxes}
    st.session_state.sending_active = False
    st.session_state.current_index = 0
    st.session_state.success_count = 0
    st.session_state.failed_count = 0
    st.rerun()

# Spintax Parser Helper
def spin(text):
    """Recursively parses {option1|option2} spintax patterns."""
    pattern = r"\{([^{}]*\|[^{}]*)\}"
    while re.search(pattern, text):
        text = re.sub(pattern, lambda m: random.choice(m.group(1).split('|')), text)
    return text

# Safe CSV Placeholder Substitution Engine
def replace_csv_placeholders(text, row_dict):
    """Replaces [variable] format to prevent conflicting with Spintax {brackets}."""
    for key, value in row_dict.items():
        text = re.sub(r'\[\s*' + re.escape(str(key)) + r'\s*\]', str(value), text)
    return text

# ==========================================
# 2. FILE UPLOADER & PROCESSING
# ==========================================
uploaded_file = st.file_uploader(
    "Choose a CSV file", type=["csv"], help="CSV must contain required columns"
)

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)

    # Required CSV columns for your leads
    required_cols = ["email", "first_name", "sender_name"]
    missing_cols = [c for c in required_cols if c not in df.columns]

    if missing_cols:
        st.error(
            f"❌ Missing required CSV columns: `{', '.join(missing_cols)}`"
        )
    else:
        st.write("### Data Preview", df.head(5))

        st.sidebar.markdown("---")
        st.sidebar.subheader("Pacing Controls")
        
        # Delay preset to exactly 120 seconds (2 minutes)
        delay_seconds = st.sidebar.number_input(
            "Delay between sends (seconds)", 
            min_value=1, 
            max_value=600, 
            value=120, 
            step=5,
            help="Set to 120 seconds for a 2-minute gap between every sent email."
        )

        subject_template = st.text_input("Subject Line", value="Project Inquiry")
        
        body_template = st.text_area(
            "Email Body Template (Supports [CSV variables] & {Spintax})", 
            value="{Hello|Hi|Hey} [first_name]\n\n{Are you available for a project, let's discuss by email.|Do you have capacity for a quick project? Can we chat via email?|Are you taking on new projects right now? Let's connect over email.}\n\n{Best Regards|Best|Kind Regards|Regards}\n[sender_name]",
            height=220
        )

        # Execution Controls
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Start / Resume Sending", disabled=st.session_state.sending_active, use_container_width=True):
                st.session_state.sending_active = True
                st.rerun()
        with col2:
            if st.button("🛑 Pause Campaign", disabled=not st.session_state.sending_active, use_container_width=True):
                st.session_state.sending_active = False
                st.rerun()

        # State-driven dispatch processing
        if st.session_state.sending_active:
            total_leads = len(df)
            progress_bar = st.progress(st.session_state.current_index / total_leads)
            status = st.empty()

            while st.session_state.current_index < total_leads and st.session_state.sending_active:
                i = st.session_state.current_index
                row = df.iloc[i]

                # Filter inboxes that haven't hit the daily cap (30 sends)
                eligible_inboxes = [
                    acc
                    for acc in inboxes
                    if st.session_state.send_counts[acc["username"]] < DAILY_INBOX_LIMIT
                ]

                if not eligible_inboxes:
                    st.error(
                        f"🛑 All inboxes have reached their daily limit of {DAILY_INBOX_LIMIT} emails! Process paused."
                    )
                    st.session_state.sending_active = False
                    break

                # Pick a random eligible inbox to balance sending loads
                selected_inbox = random.choice(eligible_inboxes)
                inbox_user = selected_inbox["username"]
                inbox_pass = selected_inbox["password"]

                recipient = row.get("email")
                sender_display_name = row.get("sender_name", "")
                row_dict = row.to_dict()

                # 1. Substitute CSV placeholders using square brackets [first_name], [sender_name]
                formatted_body = replace_csv_placeholders(body_template, row_dict)
                formatted_subject = replace_csv_placeholders(subject_template, row_dict)

                # 2. Process Spintax options inside curly brackets {Hello|Hi|Hey}
                final_body = spin(formatted_body)
                final_subject = spin(formatted_subject)

                # Create Plain Text Email Message
                msg = MIMEMultipart()
                # Set dynamic display name from CSV in the From header
                msg["From"] = f'"{sender_display_name}" <{inbox_user}>' if sender_display_name else inbox_user
                msg["To"] = recipient
                msg["Subject"] = final_subject
                msg.attach(MIMEText(final_body, "plain"))

                try:
                    server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
                    server.starttls()
                    server.login(inbox_user, inbox_pass)
                    server.sendmail(inbox_user, recipient, msg.as_string())
                    server.quit()

                    # Increment records on success
                    st.session_state.send_counts[inbox_user] += 1
                    st.session_state.success_count += 1

                except Exception as e:
                    st.session_state.failed_count += 1
                    st.sidebar.error(f"Failed to send to {recipient}: {e}")

                # Save current position index
                st.session_state.current_index += 1
                progress_bar.progress(st.session_state.current_index / total_leads)

                # Show status summary
                status.info(
                    f"[{st.session_state.current_index}/{total_leads}] Last dispatch: **{recipient}** as **'{sender_display_name}'** via `{inbox_user}` "
                    f"({st.session_state.send_counts[inbox_user]}/{DAILY_INBOX_LIMIT})"
                )

                # Apply second-by-second countdown delay so the layout doesn't lock completely
                if st.session_state.current_index < total_leads and st.session_state.sending_active:
                    for remaining in range(delay_seconds, 0, -1):
                        status.warning(f"⏳ Waiting {remaining} seconds before sending the next email (Lead {st.session_state.current_index + 1}/{total_leads})...")
                        time.sleep(1)

            # Check if execution finished completely
            if st.session_state.current_index >= total_leads:
                st.session_state.sending_active = False
                st.balloons()
                st.success(
                    f"🎉 Task run complete! Sent: {st.session_state.success_count} | Failed: {st.session_state.failed_count}"
                )
