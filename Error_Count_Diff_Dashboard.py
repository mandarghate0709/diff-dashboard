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

st.write(
    f"### ✅ Loaded Report: **{selected_report}** "
    f"(Market: **{selected_market}**)"
)

# =================================================
# Ensure required columns
# =================================================
if "Bug Ticket" not in df.columns:
    df["Bug Ticket"] = np.nan

# =================================================
# Jira link column (stable)
# =================================================
JIRA_BASE = "https://here-technologies.atlassian.net/browse/"
ticket_re = re.compile(r"(HERESUP-\d+)")

def ticket_to_url(val):
    if pd.isna(val):
        return None
    m = ticket_re.search(str(val))
    if m:
        return f"{JIRA_BASE}{m.group(1)}"
    return None

df["Jira Link"] = df["Bug Ticket"].apply(ticket_to_url)

# =================================================
# Compute Severity if missing
# =================================================
if "Severity" not in df.columns:
    def classify_severity(row):
        if "diff_percent" in row and not pd.isna(row["diff_percent"]):
            p = row["diff_percent"]
            if p > 10:
                return "Major Regression"
            elif p > 5:
                return "Moderate Regression"
            elif p > 0:
                return "Minor Regression"
            elif p < 0:
                return "Improvement"
        if row["diff"] > 0:
            return "Regression"
        elif row["diff"] < 0:
            return "Improvement"
        return "No Change"

    df["Severity"] = df.apply(classify_severity, axis=1)

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

min_d, max_d = int(df["diff"].min()), int(df["diff"].max())
rng = st.sidebar.slider("Diff Range", min_d, max_d, (min_d, max_d))
view = view[(view["diff"] >= rng[0]) & (view["diff"] <= rng[1])]

search = st.sidebar.text_input("Search Test ID / Name")
if search:
    view = view[
        view["testId"].str.contains(search, case=False, na=False) |
        view["testName"].str.contains(search, case=False, na=False)
    ]

# =================================================
# Diff Table with COLOR CODING
# =================================================
st.subheader("📋 Diff Table")

def color_diff(val):
    if val > 0:
        return "background-color: #FFC7CE"
    elif val < 0:
        return "background-color: #C6EFCE"
    return ""

styled = view.style.applymap(color_diff, subset=["diff"])

st.dataframe(
    styled,
    use_container_width=True,
    column_config={
        "Jira Link": st.column_config.LinkColumn(
            "Jira",
            display_text="🔗"
        )
    }
)

# =================================================
# New Failures (Pass → Fail) WITH ERROR COUNTS
# =================================================
status_cols = [c for c in df.columns if c.endswith(selected_market)]
error_cols = [c for c in df.columns if c.endswith("_errors")]

if len(status_cols) >= 2 and len(error_cols) >= 2:
    old_status, new_status = status_cols[:2]
    old_err, new_err = error_cols[:2]

    st.subheader("🆕 New Failures (Pass → Fail)")

    nf = df[
        (df[old_status] == "Pass") &
        (df[new_status] == "Fail")
    ].copy()

    nf["Jira Link"] = nf["Bug Ticket"].apply(ticket_to_url)

    if nf.empty:
        st.info("No new Pass → Fail cases detected.")
    else:
        st.dataframe(
            nf[
                ["testId", "testName", old_err, new_err, "diff", "Jira Link"]
            ],
            use_container_width=True,
            column_config={
                "Jira Link": st.column_config.LinkColumn(
                    "Jira",
                    display_text="🔗"
                )
            }
        )

# =================================================
# Severity Pie Chart
# =================================================
st.subheader("🟣 Severity Distribution")

sev_counts = df["Severity"].value_counts().reset_index()
sev_counts.columns = ["Severity", "Count"]

fig = px.pie(
    sev_counts,
    names="Severity",
    values="Count"
)
st.plotly_chart(fig, use_container_width=True)

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
