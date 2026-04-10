import streamlit as stimportimport pandas as pd
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
# Error_Count_Diff_P173_vs_261E0_NAR.xlsx
# =================================================
def extract_market(filename: str) -> str:
    return os.path.basename(filename).replace(".xlsx", "").split("_")[-1]

def extract_releases(filename: str):
    base = os.path.basename(filename).replace(".xlsx", "")
    parts = base.split("_")
    # Error_Count_Diff_<OLD>_vs_<NEW>_<MARKET>
    old_rel = parts[3]
    new_rel = parts[5]
    return old_rel, new_rel

def clean_report_name(filename: str) -> str:
    return (
        os.path.basename(filename)
        .replace("Error_Count_Diff_", "")
        .replace(".xlsx", "")
    )

# =================================================
# Market → Report mapping
# =================================================
market_map = {}
for f in files:
    market = extract_market(f)
    report = clean_report_name(f)
    market_map.setdefault(market, {})[report] = f

# =================================================
# Sidebar selection
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

selected_file = market_map[selected_market][selected_report]

# =================================================
# Load report
# =================================================
df = pd.read_excel(selected_file)

old_rel, new_rel = extract_releases(selected_file)

st.write(
    f"### ✅ Loaded Report: **{selected_report}** "
    f"(Market: **{selected_market}**)"
)

# =================================================
# Ensure Bug Ticket column exists
# =================================================
if "Bug Ticket" not in df.columns:
    df["Bug Ticket"] = np.nan

# =================================================
# Jira link column
# =================================================
JIRA_BASE = "https://here-technologies.atlassian.net/browse/"
ticket_re = re.compile(r"(HERESUP-\d+)")

def ticket_to_url(val):
    if pd.isna(val):
        return None
    match = ticket_re.search(str(val))
    if match:
        return f"{JIRA_BASE}{match.group(1)}"
    return None

df["Jira Link"] = df["Bug Ticket"].apply(ticket_to_url)

# =================================================
# ✅ CORRECTLY bind OLD/NEW status & error columns
# =================================================
old_status = f"{old_rel}_{selected_market}"
new_status = f"{new_rel}_{selected_market}"

old_err = f"{old_rel}_{selected_market}_errors"
new_err = f"{new_rel}_{selected_market}_errors"

# =================================================
# ✅ FINAL diff % LOGIC (NOW 100% CORRECT)
# =================================================
def compute_diff_percent(row):
    # Old Pass + Old errors = 0 + New errors > 0 → NA
    if (
        row[old_status] == "Pass" and
        row[old_err] == 0 and
        row[new_err] > 0
    ):
        return np.nan

    if row[old_err] != 0:
        return round((row["diff"] / row[old_err]) * 100, 2)

    return np.nan

df["diff_percent"] = df.apply(compute_diff_percent, axis=1)

# =================================================
# Severity classification
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
# Filters
# =================================================
st.sidebar.header("🔍 Filters")

mode = st.sidebar.radio(
    "Show",
    ["All", "Only Regressions", "Only Improvements"]
)

view = df.copy()

if mode == "Only Regressions":
    view = view[view["diff"] > 0]
elif mode == "Only Improvements":
    view = view[view["diff"] < 0]

# =================================================
# Diff Table with color coding
# =================================================
st.subheader("📋 Diff Table")

def color_diff(val):
    if val > 0:
        return "background-color:#FFC7CE"
    if val < 0:
        return "background-color:#C6EFCE"
    return ""

styled_main = view.style.map(color_diff, subset=["diff"])

st.dataframe(
    styled_main,
    use_container_width=True,
    column_config={
        "Jira Link": st.column_config.LinkColumn("Jira", display_text="🔗")
    }
)

# =================================================
# New Failures (Pass → Fail)
# =================================================
st.subheader("🆕 New Failures (Pass → Fail)")

nf = df[
    (df[old_status] == "Pass") &
    (df[new_status] == "Fail")
].copy()

nf["Jira Link"] = nf["Bug Ticket"].apply(ticket_to_url)

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
# Severity Pie Chart
# =================================================
st.subheader("🟣 Severity Distribution")

sev_counts = df["Severity"].value_counts().reset_index()
sev_counts.columns = ["Severity", "Count"]

fig = px.pie(sev_counts, names="Severity", values="Count")
fig.update_traces(textinfo="label+percent")
st.plotly_chart(fig, use_container_width=True)

# =================================================
# Regression Severity Criteria
# =================================================
st.subheader("ℹ️ Regression Severity Criteria")

criteria_df = pd.DataFrame({
    "Regression Type": [
        "Minor Regression",
        "Moderate Regression",
        "Major Regression",
        "Improvement",
        "No Change"
    ],
    "Diff % Criteria": [
        "0% < Diff % ≤ 5%",
        "5% < Diff % ≤ 10%",
        "Diff % > 10%",
        "Diff % < 0",
        "Diff % = 0"
    ]
})

st.table(criteria_df)

# =================================================
# Export
# =================================================
st.subheader("📤 Export")

buffer = BytesIO()
view.to_excel(buffer, index=False)
buffer.seek(0)

st.download_button(
    "⬇️ Download Filtered Data (Excel)",
    data=buffer,
    file_name=f"{selected_report}_Filtered.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
