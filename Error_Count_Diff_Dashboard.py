import streamlit as st
import pandas as pd
import glob
import os
import plotly.express as px
import numpy as np
import re
from io import BytesIO

st.set_page_config(page_title="Error Count Diff Dashboard", layout="wide")
st.title("📊 Error Count Diff Dashboard")

BASE_PATH = "data"

files = glob.glob(os.path.join(BASE_PATH, "*.xlsx"))
if not files:
    st.error("No Excel files found in data/ folder")
    st.stop()

def extract_market(filename: str) -> str:
    return os.path.basename(filename).replace(".xlsx", "").split("_")[-1]

def clean_report_name(filename: str) -> str:
    return os.path.basename(filename).replace("Error_Count_Diff_", "").replace(".xlsx", "")

market_map = {}
for f in files:
    market = extract_market(f)
    market_map.setdefault(market, {})[clean_report_name(f)] = f

st.sidebar.header("📁 Select Report")
selected_market = st.sidebar.selectbox("Select Market", sorted(market_map.keys()))
selected_report = st.sidebar.selectbox("Select Report", sorted(market_map[selected_market].keys()))
selected_file = market_map[selected_market][selected_report]

df = pd.read_excel(selected_file)

st.write(f"### ✅ Loaded Report: **{selected_report}** (Market: **{selected_market}**)")

if "Bug Ticket" not in df.columns:
    df["Bug Ticket"] = np.nan

JIRA_BASE = "https://here-technologies.atlassian.net/browse/"
ticket_re = re.compile(r"(HERESUP-\\d+)")

def ticket_to_url(val):
    if pd.isna(val):
        return None
    m = ticket_re.search(str(val))
    return f"{JIRA_BASE}{m.group(1)}" if m else None

df["Jira Link"] = df["Bug Ticket"].apply(ticket_to_url)

status_cols = [c for c in df.columns if c.endswith(selected_market)]
error_cols = [c for c in df.columns if c.endswith("_errors")]

old_status, new_status = status_cols[:2]
old_err, new_err = error_cols[:2]

def compute_diff_percent(row):
    if row[old_status] == "Pass" and row[old_err] == 0 and row[new_err] > 0:
        return np.nan
    if row[old_err] != 0:
        return round((row["diff"] / row[old_err]) * 100, 2)
    return np.nan

df["diff_percent"] = df.apply(compute_diff_percent, axis=1)

def classify_severity(p):
    if pd.isna(p):
        return "NA"
    if p < 0:
        return "Improvement"
    if p <= 5:
        return "Minor Regression"
    if p <= 10:
        return "Moderate Regression"
    return "Major Regression"

df["Severity"] = df["diff_percent"].apply(classify_severity)

st.subheader("📋 Diff Table")

def color_diff(v):
    if v > 0:
        return "background-color:#FFC7CE"
    if v < 0:
        return "background-color:#C6EFCE"
    return ""

styled = df.style.map(color_diff, subset=["diff"])

st.dataframe(
    styled,
    use_container_width=True,
    column_config={
        "Jira Link": st.column_config.LinkColumn("Jira", display_text="🔗")
    }
)

st.subheader("🟣 Severity Distribution")
sev = df["Severity"].value_counts().reset_index()
sev.columns = ["Severity", "Count"]
fig = px.pie(sev, names="Severity", values="Count")
fig.update_traces(textinfo="label+percent")
st.plotly_chart(fig, use_container_width=True)

buffer = BytesIO()
df.to_excel(buffer, index=False)
buffer.seek(0)

st.download_button(
    "⬇️ Download Excel",
    data=buffer,
    file_name=f"{selected_report}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)