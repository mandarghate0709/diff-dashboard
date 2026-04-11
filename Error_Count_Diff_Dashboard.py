import streamlit as st
import pandas as pd
import glob
import os
import plotly.express as px
import numpy as np
import re
from io import BytesIO

# =================================================
# Streamlit setup
# =================================================

st.set_page_config(page_title="Error Count Diff Dashboard", layout="wide")
st.title("📊 Error Count Diff Dashboard")

# =================================================
# Base folder
# =================================================

BASE_PATH = "data"
files = glob.glob(os.path.join(BASE_PATH, "*.xlsx"))

if not files:
    st.error("No Excel files found in data/ folder")
    st.stop()

# =================================================
# Filename helpers
# =================================================

def extract_market(filename: str) -> str:
    return os.path.basename(filename).replace(".xlsx", "").split("_")[-1]

def extract_releases(filename: str):
    base = os.path.basename(filename).replace(".xlsx", "")
    parts = base.split("_")
    return parts[3], parts[5]

def clean_report_name(filename: str) -> str:
    return os.path.basename(filename).replace("Error_Count_Diff_", "").replace(".xlsx", "")

# =================================================
# Market → Report mapping
# =================================================

market_map = {}
for f in files:
    market = extract_market(f)
    market_map.setdefault(market, {})[clean_report_name(f)] = f

# =================================================
# Sidebar controls
# =================================================

st.sidebar.header("📁 Select Report")

selected_market = st.sidebar.selectbox(
    "Select Market",
    sorted(market_map.keys())
)

selected_report = st.sidebar.selectbox(
    "Select Report",
    sorted(market_map[selected_market].keys())
)

view_mode = st.sidebar.radio(
    "Show",
    ["All Tests", "Only Regressions", "Only Improvements"]
)

search_text = st.sidebar.text_input(
    "🔎 Search Test ID / Name",
    placeholder="Type testId or test name..."
)

selected_file = market_map[selected_market][selected_report]

# =================================================
# Load report
# =================================================

df = pd.read_excel(selected_file)
old_rel, new_rel = extract_releases(selected_file)

st.markdown(
    f"### ✅ Loaded Report: {clean_report_name(selected_file)} "
    f"(Market: **{selected_market}**)"
)

# =================================================
# Ensure Bug Ticket / Bug Comment columns exist
# =================================================

if "Bug Ticket" not in df.columns:
    df["Bug Ticket"] = np.nan

if "Bug Comment" not in df.columns:
    df["Bug Comment"] = np.nan

# =================================================
# Jira link column
# =================================================

JIRA_BASE = "https://here-technologies.atlassian.net/browse/"
ticket_re = re.compile(r"(HERESUP-\d+)")

def ticket_to_url(val):
    if pd.isna(val):
        return None
    m = ticket_re.search(str(val))
    return f"{JIRA_BASE}{m.group(1)}" if m else None

df["Jira Link"] = df["Bug Ticket"].apply(ticket_to_url)

# =================================================
# Bind correct OLD / NEW status & error columns
# =================================================

old_status = f"{old_rel}_{selected_market}"
new_status = f"{new_rel}_{selected_market}"
old_err = f"{old_rel}_{selected_market}_errors"
new_err = f"{new_rel}_{selected_market}_errors"

# =================================================
# Diff % logic
# =================================================

def compute_diff_percent(row):
    if row[old_status] == "Pass" and row[old_err] == 0 and row[new_err] > 0:
        return np.nan
    if row[old_err] != 0:
        return round((row["diff"] / row[old_err]) * 100, 2)
    return np.nan

df["diff_percent"] = df.apply(compute_diff_percent, axis=1)

# =================================================
# Severity
# =================================================

def classify_severity(p):
    if pd.isna(p):
        return "NA"
    if p < 0:
        return "Improvement"
    if p == 0:
        return "No Change"
    if p <= 5:
        return "Minor Regression"
    if p <= 10:
        return "Moderate Regression"
    return "Major Regression"

df["Severity"] = df["diff_percent"].apply(classify_severity)

# =================================================
# Summary
# =================================================

st.subheader("📦 Summary")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Tests", len(df))
c2.metric("Regressions", (df["diff"] > 0).sum())
c3.metric("Improvements", (df["diff"] < 0).sum())
c4.metric("No Change", (df["diff"] == 0).sum())

# =================================================
# Global filters
# =================================================

view = df.copy()

if view_mode == "Only Regressions":
    view = view[view["diff"] > 0]
elif view_mode == "Only Improvements":
    view = view[view["diff"] < 0]

if search_text:
    view = view[
        view["testId"].str.contains(search_text, case=False, na=False) |
        view["testName"].str.contains(search_text, case=False, na=False)
    ]

# =================================================
# Diff Table (Bug Comment NOT shown)
# =================================================

st.subheader("📋 Diff Table")

def color_diff(val):
    if val > 0:
        return "background-color:#FFC7CE"
    if val < 0:
        return "background-color:#C6EFCE"
    return ""

display_cols = [
    c for c in view.columns
    if c not in ["Bug Comment"]
]

styled_main = view[display_cols].style.map(color_diff, subset=["diff"])

st.dataframe(
    styled_main,
    use_container_width=True,
    column_config={
        "Jira Link": st.column_config.LinkColumn("Jira", display_text="🔗")
    }
)

# =================================================
# 🆕 New Failures (Pass → Fail) — RESTORED
# =================================================

st.subheader("🆕 New Failures (Pass → Fail)")

nf = df[
    (df[old_status] == "Pass") &
    (df[new_status] == "Fail")
].copy()

if view_mode == "Only Regressions":
    nf = nf[nf["diff"] > 0]
elif view_mode == "Only Improvements":
    nf = nf[nf["diff"] < 0]

if search_text:
    nf = nf[
        nf["testId"].str.contains(search_text, case=False, na=False) |
        nf["testName"].str.contains(search_text, case=False, na=False)
    ]

nf_view = nf[
    [
        "testId",
        "testName",
        old_status,
        new_status,
        old_err,
        new_err,
        "diff",
        "diff_percent",
        "Severity",
        "Bug Ticket",
        "Jira Link",
    ]
]

styled_nf = nf_view.style.map(color_diff, subset=["diff"])

st.dataframe(
    styled_nf,
    use_container_width=True,
    column_config={
        "Jira Link": st.column_config.LinkColumn("Jira", display_text="🔗")
    }
)

# =================================================
# 🧾 Failure Details (Bug Comments) — NEW
# =================================================

st.subheader("🧾 Failure Details (Bug Comments)")

failures_with_comments = df[
    (df[new_status] == "Fail") &
    df["Bug Ticket"].notna() &
    df["Bug Comment"].notna() &
    (df["Bug Comment"].str.strip() != "")
]

if failures_with_comments.empty:
    st.info("No Bug Comments available for failing tests.")
else:
    for _, row in failures_with_comments.iterrows():
        with st.expander(f"{row['testId']} | {row['Bug Ticket']}"):
            st.markdown(f"**Test Name:** {row['testName']}")
            st.markdown(f"**Bug Ticket:** {row['Jira Link']}")
            st.markdown("**🔍 Bug Comment:**")
            st.code(row["Bug Comment"], language="text")

# =================================================
# Severity Pie Chart
# =================================================

st.subheader("🟣 Severity Distribution")

sev_counts = df["Severity"].value_counts().reset_index()
sev_counts.columns = ["Severity", "Count"]
fig = px.pie(sev_counts, names="Severity", values="Count")
fig.update_traces(textinfo="label+percent")

st.plotly_chart(fig, use_container_width=True)

# =================================================
# Export
# =================================================

st.subheader("📤 Export")
buffer = BytesIO()
view[display_cols].to_excel(buffer, index=False)
buffer.seek(0)

st.download_button(
    "⬇️ Download Filtered Data (Excel)",
    data=buffer,
    file_name=f"{selected_report}_Filtered.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)