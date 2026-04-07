import streamlit as st
import pandas as pd
import glob
import os
import plotly.express as px
from io import BytesIO
import numpy as np

st.set_page_config(page_title="Diff Dashboard", layout="wide")
st.title("📊 Single‑Report Diff Dashboard")

# =================================================
# Base folder (Streamlit Cloud compatible)
# =================================================
BASE_PATH = "data"

files = glob.glob(os.path.join(BASE_PATH, "**", "*.xlsx"), recursive=True)
if not files:
    st.error("No Excel files found in data folder")
    st.stop()

file_names = [os.path.basename(f) for f in files]
selected_name = st.sidebar.selectbox("Select Report", file_names)
selected_file = dict(zip(file_names, files))[selected_name]

df = pd.read_excel(selected_file)
st.write(f"### ✅ Loaded Report: **{selected_name}**")

# =================================================
# Detect old/new columns
# =================================================
status_cols = [c for c in df.columns if "_" in c and not c.endswith("_errors")]
error_cols = [c for c in df.columns if c.endswith("_errors")]

old_status, new_status = (status_cols + [None, None])[:2]
new_err_col, old_err_col = (error_cols + [None, None])[:2]

# =================================================
# ✅ Robust diff % calculation (0 → non‑zero = NA)
# =================================================
def calc_diff_percent(row):
    old = row[old_err_col]
    new = row[new_err_col]
    if old == 0:
        return np.nan
    return round(((new - old) / old) * 100, 2)

df["diff_percent"] = df.apply(calc_diff_percent, axis=1)

# =================================================
# ✅ Severity classification (NA‑aware)
# =================================================
def classify_severity(p):
    if pd.isna(p):
        return "NA"
    if p > 10:
        return "Major Regression"
    elif p > 5:
        return "Moderate Regression"
    elif p > 0:
        return "Minor Regression"
    elif p < 0:
        return "Improvement"
    return "No Change"

df["Severity"] = df["diff_percent"].apply(classify_severity)

# =================================================
# ✅ Summary
# =================================================
st.subheader("📦 Summary")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Tests", len(df))
c2.metric("Regressions", (df["diff"] > 0).sum())
c3.metric("Improvements", (df["diff"] < 0).sum())
c4.metric("No Change", (df["diff"] == 0).sum())

valid_pct = df.dropna(subset=["diff_percent"])
worst = valid_pct.loc[valid_pct["diff_percent"].idxmax()] if not valid_pct.empty else None
best  = valid_pct.loc[valid_pct["diff_percent"].idxmin()] if not valid_pct.empty else None

if "highlight" not in st.session_state:
    st.session_state.highlight = None

c5, c6 = st.columns(2)

with c5:
    if worst is not None:
        st.metric("Worst Regression (% diff)", f"{worst['diff_percent']}%")
        st.caption(f"TestId: {worst['testId']}")
        if st.button("Highlight Worst"):
            st.session_state.highlight = worst["testId"]
    else:
        st.metric("Worst Regression (% diff)", "NA")

with c6:
    if best is not None:
        st.metric("Best Improvement (% diff)", f"{best['diff_percent']}%")
        st.caption(f"TestId: {best['testId']}")
        if st.button("Highlight Best"):
            st.session_state.highlight = best["testId"]
    else:
        st.metric("Best Improvement (% diff)", "NA")

if st.session_state.highlight and st.button("Clear Highlight"):
    st.session_state.highlight = None

# =================================================
# ✅ Filters
# =================================================
st.sidebar.header("🔍 Filters")

mode = st.sidebar.radio("Show", ["All", "Only Regressions", "Only Improvements"])
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

if st.session_state.highlight:
    view = view[view["testId"] == st.session_state.highlight]

# =================================================
# ✅ Diff table
# =================================================
def color_diff(v):
    if isinstance(v, (int, float)):
        if v > 0:
            return "background-color:#FFC7CE"
        if v < 0:
            return "background-color:#C6EFCE"
    return ""

st.subheader("📋 Diff Table")
st.dataframe(view.style.map(color_diff, subset=["diff"]), use_container_width=True)

# =================================================
# ✅ 🔥 Top 20 Major Regressions
# =================================================
st.subheader("🔥 Top 20 Major Regressions (diff% > 10%)")
major = df[df["Severity"] == "Major Regression"].sort_values("diff_percent", ascending=False).head(20)
st.dataframe(major.style.map(color_diff, subset=["diff"]), use_container_width=True)

# =================================================
# ✅ 🆕 New Failures (Pass → Fail)
# =================================================
st.subheader("🆕 New Failures (Pass → Fail)")

if old_status and new_status:
    new_failures = df[
        (df[old_status] == "Pass") &
        (df[new_status] == "Fail")
    ]

    if new_failures.empty:
        st.info("No new Pass → Fail cases detected.")
    else:
        st.write(f"**Total New Failures:** {len(new_failures)}")
        st.dataframe(
            new_failures.style.map(color_diff, subset=["diff"]),
            use_container_width=True
        )
else:
    st.warning("Old/New Pass‑Fail columns not detected in this report.")

# =================================================
# ✅ Severity pie chart
# =================================================
st.subheader("🟣 Severity Distribution")

sev_counts = df["Severity"].value_counts().reset_index()
sev_counts.columns = ["Severity", "Count"]

pie = px.pie(
    sev_counts,
    names="Severity",
    values="Count",
    color="Severity",
    color_discrete_map={
        "Major Regression": "#ff4d4d",
        "Moderate Regression": "#ff944d",
        "Minor Regression": "#ffe066",
        "Improvement": "#66cc66",
        "No Change": "#cccccc",
        "NA": "#999999",
    },
)

st.plotly_chart(pie, use_container_width=True)

# =================================================
# ✅ Export
# =================================================
def to_excel(d):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        d.to_excel(w, index=False)
    return out.getvalue()

st.download_button(
    "⬇️ Download Filtered Excel",
    data=to_excel(view),
    file_name="Filtered_Diff_Report.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
