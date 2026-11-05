"""Points+ loyalty impact app.

Reads the customer-month metrics exported from the dbt mart
(app/data/fct_customer_month.parquet). No database connection needed.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

DATA_PATH = Path(__file__).parent / "data" / "fct_customer_month.parquet"
REPO_URL = "https://github.com/HGFalk/loyalty-impact-analytics"
PRE_START = pd.Timestamp("2018-01-01")         # experiment baseline: Jan to Aug 2018
EXPERIMENT_START = pd.Timestamp("2018-09-01")  # random assignment date

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
is_member = df["enrolled_at"].notna()

# --- 1. Naive comparison: members after joining vs never-members, 2019 ---
y2019 = df[df["month"] >= "2019-01-01"]
naive = lift_pct(
    y2019.loc[y2019["membership_phase"] == "after_joining", "purchases"].mean(),
    y2019.loc[y2019["membership_phase"] == "non_member", "purchases"].mean(),
)

# Selection check: future members vs never-members in 2017, before Points+ existed.
y2017 = df[df["month"] < "2018-01-01"]
pre_gap = lift_pct(
    y2017.loc[is_member, "purchases"].mean(),
    y2017.loc[~is_member, "purchases"].mean(),
)

# --- 2. Members compared with themselves: after vs before joining ---
members = df[is_member]
before_after = lift_pct(
    members.loc[members["membership_phase"] == "after_joining", "purchases"].mean(),
    members.loc[members["membership_phase"] == "before_joining", "purchases"].mean(),
)

# --- 3. Experiment: per-customer change from Jan to Aug 2018 to Sep 2018 onwards ---
exp = df[df["experiment_variant"].notna() & (df["month"] >= PRE_START)].copy()
exp["period"] = np.where(exp["month"] >= EXPERIMENT_START, "post", "pre")
per_customer = exp.pivot_table(
    index=["customer_id", "experiment_variant"], columns="period",
    values="purchases", aggfunc="mean",
).reset_index()
per_customer["change"] = per_customer["post"] - per_customer["pre"]

stats = per_customer.groupby("experiment_variant")["change"].agg(["mean", "var", "count"])
baseline = per_customer.loc[per_customer["experiment_variant"] == "control", "pre"].mean()
did = stats.loc["invitation", "mean"] - stats.loc["control", "mean"]   # difference in differences
se = np.sqrt((stats["var"] / stats["count"]).sum())                    # Welch standard error
did_pct = 100 * did / baseline
ci_low_pct = 100 * (did - 1.96 * se) / baseline
ci_high_pct = 100 * (did + 1.96 * se) / baseline
n_per_group = int(stats["count"].min())

# Sample size per group to detect a 1% lift with 80% power at 5% significance.
target = 0.01 * baseline
sd_change = np.sqrt(stats["var"].mean())
n_needed = int(np.ceil(2 * (1.96 + 0.84) ** 2 * sd_change**2 / target**2))

# Join rates by experiment group (eligible customers were all non-members on 1 Sep 2018).
customers = df.drop_duplicates("customer_id")
exp_customers = customers[customers["experiment_variant"].notna()]
join_rate = 100 * exp_customers.assign(joined=exp_customers["enrolled_at"].notna()).groupby(
    "experiment_variant"
)["joined"].mean()

# Effect per customer who joined because of the invitation (intention-to-treat / extra joiners).
extra_joiners = (join_rate["invitation"] - join_rate["control"]) / 100
per_joiner_pct = did_pct / extra_joiners

# Wording that depends on the result, so the text never contradicts the numbers.
ci_includes_zero = ci_low_pct <= 0 <= ci_high_pct
if ci_includes_zero:
    exp_headline = "Invitations drive sign-ups, but the purchase effect is too small for this test to confirm."
    exp_verdict = "and that range includes zero"
else:
    exp_headline = "Invitations drive sign-ups and a small, measurable purchase lift."
    exp_verdict = "so the lift is unlikely to be chance"
if n_needed > n_per_group:
    size_advice = (f"Detecting a 1% lift needs about **{n_needed:,}** customers per group; "
                   f"this test had about {n_per_group:,}.")
else:
    size_advice = (f"This test (about {n_per_group:,} per group) was large enough to detect a 1% lift; "
                   "a larger rollout should still be measured with a holdout group.")
invited_lower_before = (
    per_customer.loc[per_customer["experiment_variant"] == "invitation", "pre"].mean() < baseline
)

# ======================= Page =======================
st.title("Does the Points+ loyalty programme make customers buy more?")
st.caption(
    "Synthetic loyalty programme built on public Kaggle card data (2017 to 2019). "
    "The true effect was planted at +5% purchases for members after joining, "
    "so each method can be checked against the right answer."
)

st.header("Recommendation")
st.markdown(
    f"""
1. **Do not judge Points+ by comparing members with non-members.** That comparison shows
   **{naive:+.1f}%**, but future members already bought **{pre_gap:+.1f}%** more in 2017,
   before the programme existed. Most of the gap is who joins, not what the programme does.
2. **The real effect on members is small and positive.** Members buy **{before_after:+.1f}%**
   more after joining than before. The planted true effect is +5%.
3. **{exp_headline}**
   Invited customers joined at **{join_rate['invitation']:.0f}%** versus **{join_rate['control']:.0f}%**
   without an invitation. Per invited customer, purchases changed **{did_pct:+.1f}%**
     (95% interval {ci_low_pct:+.1f}% to {ci_high_pct:+.1f}%), {exp_verdict}.
   Spread over the extra customers the invitation brought in, that is about
   **{per_joiner_pct:+.1f}%** per joiner, close to the planted +5%.
4. **Before scaling invitations, check the size of the test and add costs.** {size_advice}
   Points costs and redemptions are not in this data and decide whether the lift pays off.
"""
)

st.header("Three ways to measure the same effect")
c1, c2, c3 = st.columns(3)
c1.metric("Naive: members vs non-members", f"{naive:+.1f}%")
c2.metric("Members: after vs before joining", f"{before_after:+.1f}%")
c3.metric("Experiment: per invited customer", f"{did_pct:+.1f}%",
          help=f"95% interval {ci_low_pct:+.1f}% to {ci_high_pct:+.1f}%")

st.subheader("Members were heavier buyers before Points+ launched")
trend = (
    df.assign(group=np.where(is_member, "Joined Points+ at some point", "Never joined"))
    .groupby(["month", "group"])["purchases"].mean()
    .unstack()
)
st.line_chart(trend, x_label="Month", y_label="Purchases per customer per month")
st.caption("Points+ launched in March 2018. The gap between the lines exists from the start of 2017.")

st.subheader("Invitation experiment, adjusted for each group's starting point")
st.markdown(
    f"Random assignment on 1 September 2018 still left the invited group buying "
    f"{'less' if invited_lower_before else 'more'} than control beforehand. "
    "Comparing each group's change, not its level, removes that starting difference."
)
exp_table = (
    per_customer.groupby("experiment_variant")[["pre", "post"]].mean()
    .assign(change_pct=lambda t: lift_pct(t["post"], t["pre"]))
    .join(join_rate.rename("joined_pct"))
    .rename_axis(None)
    .rename(
        index={"control": "Control (no invitation)", "invitation": "Invited"},
        columns={
            "pre": "Purchases/month, Jan to Aug 2018",
            "post": "Purchases/month, Sep 2018 on",
            "change_pct": "Change %",
            "joined_pct": "Joined Points+ %",
        },
    )
)
st.dataframe(exp_table.style.format("{:.1f}"), width="stretch")

st.header("Method and data")
st.markdown(
    f"""
- **Data:** public Kaggle card transactions (ComputingVictor, *Financial Transactions Dataset: Analytics*,
  Apache 2.0). The Points+ programme, the experiment and the +5% effect are synthetic, generated in Python.
- **Pipeline:** Python loads the raw files into BigQuery; dbt builds staging, cleaned and
  customer-month models with 18 tests; this app reads the exported customer-month table.
- **Measures:** purchases per customer per month, including months with no purchases.
  The experiment interval uses a Welch standard error on per-customer changes.
- **Built with AI-assisted coding (Claude).** I directed the design and reviewed and tested the code.
- **Code:** [{REPO_URL}]({REPO_URL})
"""
)