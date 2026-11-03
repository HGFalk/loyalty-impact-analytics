"""Generate the synthetic Points+ loyalty programme on top of the Kaggle data.

Design (documented in the README):
- Points+ launches 1 March 2018.
- Organic joining: customers who bought more in 2017 are more likely to join
  (built-in selection bias).
- Invitation experiment: on 1 September 2018, active non-members are split
  50/50 at random; invited customers are more likely to join.
- Planted true effect: members make about 5% more purchases after joining.
  These extra purchases go in a separate table so the effect is fully traceable.

Output tables in BigQuery dataset `raw`:
    loyalty_members, experiment_assignments, extra_transactions
"""
import numpy as np
import pandas as pd
from google.cloud import bigquery

PROJECT_ID = "loyalty-impact-analytics"
DATASET = "raw"
SEED = 42  # fixed seed: running the script again gives exactly the same data

LAUNCH = pd.Timestamp("2018-03-01")
EXPERIMENT_START = pd.Timestamp("2018-09-01")
DATA_END = pd.Timestamp("2019-10-31 23:59:59")

# Chance of joining on their own by 2017 activity quartile (1 = least active).
ORGANIC_JOIN_RATE = {1: 0.10, 2: 0.15, 3: 0.22, 4: 0.30}
INVITE_ACCEPT_RATE = 0.25    # share of invited customers who accept
PLANTED_EFFECT_PCT = 5       # extra purchases for members after joining, in %

TXN = f"`{PROJECT_ID}.{DATASET}.transactions`"


def fmt(ts):
    """Timestamp to the same text format as raw.transactions.date."""
    return ts.dt.strftime("%Y-%m-%d %H:%M:%S")


def random_dates(rng, start, end, n):
    """n random timestamps between start and end, rounded to the minute."""
    seconds = rng.uniform(0, (end - start).total_seconds(), n)
    return (start + pd.to_timedelta(seconds, unit="s")).floor("min")


def build_programme(customers, rng):
    """Decide who joins Points+, when, and through which channel."""
    df = customers.copy()

    # Activity quartile from 2017 purchases (rank first so ties do not break qcut).
    df["quartile"] = pd.qcut(df["txns_2017"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)

    # Organic joiners: probability depends on quartile, join date spread over the programme period.
    joins = rng.random(len(df)) < df["quartile"].map(ORGANIC_JOIN_RATE)
    df["organic_date"] = pd.NaT
    df.loc[joins, "organic_date"] = random_dates(rng, LAUNCH, DATA_END, joins.sum())

    # Experiment: active Jun to Aug 2018 and not yet a member on 1 Sep 2018.
    not_member_yet = df["organic_date"].isna() | (df["organic_date"] >= EXPERIMENT_START)
    eligible = df[df["active_summer_2018"] & not_member_yet].copy()
    eligible["variant"] = np.where(rng.random(len(eligible)) < 0.5, "invitation", "control")

    # Invited customers who accept join within days (average 10, at most 60).
    invited = eligible["variant"] == "invitation"
    accepts = invited & (rng.random(len(eligible)) < INVITE_ACCEPT_RATE)
    days = np.minimum(rng.exponential(10, len(eligible)), 60)
    eligible["invite_date"] = pd.NaT
    eligible.loc[accepts, "invite_date"] = (EXPERIMENT_START + pd.to_timedelta(days[accepts], unit="D")).floor("min")

    df = df.merge(eligible[["client_id", "invite_date"]], on="client_id", how="left")

    # Enrolment is whichever came first; channel records which route it was.
    df["enrolled_at"] = df[["organic_date", "invite_date"]].min(axis=1)
    members = df[df["enrolled_at"].notna()].copy()
    members["channel"] = np.where(members["enrolled_at"] == members["invite_date"], "invitation", "organic")

    members_out = members[["client_id"]].assign(
        enrolled_at=fmt(members["enrolled_at"]), channel=members["channel"]
    )
    experiment_out = eligible[["client_id", "variant"]].assign(
        assigned_at=EXPERIMENT_START.strftime("%Y-%m-%d %H:%M:%S")
    )
    return members_out, experiment_out


def main():
    client = bigquery.Client(project=PROJECT_ID)

    # One row per customer active in 2018, with 2017 purchases and summer 2018 activity.
    customers = client.query(f"""
        SELECT
          client_id,
          COUNTIF(date BETWEEN '2017-01-01' AND '2017-12-31 23:59:59') AS txns_2017,
          COUNTIF(date BETWEEN '2018-06-01' AND '2018-08-31 23:59:59') > 0 AS active_summer_2018
        FROM {TXN}
        GROUP BY client_id
        HAVING COUNTIF(date BETWEEN '2018-01-01' AND '2018-12-31 23:59:59') > 0
    """).to_dataframe()
    print(f"customers active in 2018: {len(customers):,}")

    rng = np.random.default_rng(SEED)
    members, experiment = build_programme(customers, rng)

    for df, name in [(members, "loyalty_members"), (experiment, "experiment_assignments")]:
        table_id = f"{PROJECT_ID}.{DATASET}.{name}"
        job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
        client.load_table_from_dataframe(df, table_id, job_config=job_config).result()
        print(f"{name}: {len(df):,} rows loaded")

    # Planted effect: copy about 5% of each member's purchases after joining,
    # shifted 1 to 72 hours later. FARM_FINGERPRINT makes the choice repeatable.
    client.query(f"""
        CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET}.extra_transactions` AS
        SELECT * FROM (
          SELECT
            CONCAT('S', t.id) AS id,
            FORMAT_TIMESTAMP('%F %T', TIMESTAMP_ADD(TIMESTAMP(t.date),
              INTERVAL MOD(ABS(FARM_FINGERPRINT(CONCAT(t.id, 'shift'))), 72) + 1 HOUR)) AS date,
            t.* EXCEPT (id, date)
          FROM {TXN} AS t
          JOIN `{PROJECT_ID}.{DATASET}.loyalty_members` AS m USING (client_id)
          WHERE t.date > m.enrolled_at
            AND MOD(ABS(FARM_FINGERPRINT(CONCAT(t.id, 'points_plus'))), 100) < {PLANTED_EFFECT_PCT}
        )
        WHERE date <= '2019-10-31 23:59:59'
    """).result()
    extra = client.get_table(f"{PROJECT_ID}.{DATASET}.extra_transactions").num_rows
    print(f"extra_transactions: {extra:,} rows created")


if __name__ == "__main__":
    main()