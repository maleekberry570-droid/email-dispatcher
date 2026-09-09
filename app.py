import csv
import io
import random
import re
import time
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="Dynamic Email Dispatcher", page_icon="✉️", layout="wide"
)

st.title("✉️ Outreach Dispatcher with Spintax")
st.markdown(
    "Upload your CSV containing `email`, `first_name`, and `sender_name` columns."
)

# ==========================================
# 1. INITIALIZE SUPABASE DB QUEUE
# ==========================================
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception:
    st.error(
        "⚠️ Supabase secrets missing! Please set `SUPABASE_URL` and `SUPABASE_KEY` in Streamlit secrets."
    )

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
        
        delay_seconds = st.sidebar.number_input(
            "Delay between sends (seconds)", 
            min_value=1, 
            max_value=600, 
            value=120, 
            step=5,
            help="Your background GitHub worker enforces a 120-second gap between sends."
        )

        subject_template = st.text_input("Subject Line", value="Project Inquiry")
        
        body_template = st.text_area(
            "Email Body Template (Supports [CSV variables] & {Spintax})", 
            value="{Hello|Hi|Hey} [first_name]\n\n{Are you available for a project, let's discuss by email.|Do you have capacity for a quick project? Can we chat via email?|Are you taking on new projects right now? Let's connect over email.}\n\n{Best Regards|Best|Kind Regards|Regards}\n[sender_name]",
            height=220
        )

        # ==========================================
        # 3. QUEUE CAMPAIGN TO SUPABASE
        # ==========================================
        if st.button("🚀 Queue Campaign & Run in Cloud", use_container_width=True):
            records = []
            for _, row in df.iterrows():
                records.append({
                    "recipient_email": str(row["email"]).strip(),
                    "first_name": str(row.get("first_name", "")).strip(),
                    "sender_name": str(row.get("sender_name", "")).strip(),
                    "subject_template": subject_template,
                    "body_template": body_template,
                    "status": "pending"
                })
            
            try:
                # Insert all leads into Supabase queue
                supabase.table("campaign_queue").insert(records).execute()
                st.balloons()
                st.success(
                    f"🎉 Successfully queued {len(records)} leads! Your cloud worker will send them every 5 minutes automatically. You can turn off your PC now."
                )
            except Exception as e:
                st.error(f"Failed to queue campaign: {e}")
