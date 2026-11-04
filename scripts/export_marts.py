"""Export the dbt business metrics from BigQuery to a file the Streamlit app reads.

The app reads this file instead of querying BigQuery, so it needs no
credentials and keeps working after the sandbox tables expire.
"""
from pathlib import Path

from google.cloud import bigquery

PROJECT_ID = "loyalty-impact-analytics"
OUT_DIR = Path(__file__).resolve().parents[1] / "app" / "data"


def main():
    client = bigquery.Client(project=PROJECT_ID)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    df = client.query(f"""
        SELECT *
        FROM `{PROJECT_ID}.analytics.fct_customer_month`
        ORDER BY customer_id, month
    """).to_dataframe()

    # BigQuery NUMERIC arrives as Python Decimal; float is simpler for the app.
    df["spend"] = df["spend"].astype(float)

    out_path = OUT_DIR / "fct_customer_month.parquet"
    df.to_parquet(out_path, index=False)
    print(f"{len(df):,} rows written to {out_path} ({out_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

    