"""Points+ loyalty impact app (version 0.1).

Reads the customer-month metrics exported from the dbt mart
(app/data/fct_customer_month.parquet). No database connection needed.
"""
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).parent / "data" / "fct_customer_month.parquet"
EXPERIMENT_START = pd.Timestamp("2018-09-01")

st.set_page_config(page_title="Points+ loyalty impact", layout="wide")


@st.cache_data
def load_data():
    df = pd.read_parquet(DATA_PATH)
    df["month"] = pd.to_datetime(df["month"])
    return df


def lift_pct(a, b):
    """Relative difference of a over b, in percent."""
    return 100 * (a / b - 1)


df = load_data()

# 1. Naive: members after joining vs never-members, 2019 only.
y2019 = df[df["month"] >= "2019-01-01"]
naive_members = y2019.loc[y2019["membership_phase"] == "after_joining", "purchases"].mean()
naive_others = y2019.loc[y2019["membership_phase"] == "non_member", "purchases"].mean()

# 2. Members compared with themselves: after vs before joining.
members = df[df["enrolled_at"].notna()]
after = members.loc[members["membership_phase"] == "after_joining", "purchases"].mean()
before = members.loc[members["membership_phase"] == "before_joining", "purchases"].mean()

# 3. Experiment: change from pre-period (Jan to Aug 2018) to post-period, per group.
exp = df[df["experiment_variant"].notna() & (df["month"] >= "2018-01-01")].copy()
exp["period"] = (exp["month"] >= EXPERIMENT_START).map({True: "post", False: "pre"})
groups = exp.groupby(["experiment_variant", "period"])["purchases"].mean().unstack()
change = lift_pct(groups["post"], groups["pre"])
did = change["invitation"] - change["control"]

st.title("Does the Points+ loyalty programme make customers buy more?")
st.caption(
    "Synthetic loyalty programme built on public Kaggle card data (2017 to 2019). "
    "The true effect was planted at +5% purchases for members after joining, "
    "so each method can be checked against the right answer."
)

c1, c2, c3 = st.columns(3)
c1.metric("Naive: members vs non-members", f"{lift_pct(naive_members, naive_others):+.1f}%")
c2.metric("Members: after vs before joining", f"{lift_pct(after, before):+.1f}%")
c3.metric("Experiment: invited vs control, adjusted", f"{did:+.1f} pts")

st.info("Version 0.1. Charts, uncertainty and the recommendation are coming next.")