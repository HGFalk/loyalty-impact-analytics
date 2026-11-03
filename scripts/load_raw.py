"""Load the raw Kaggle files into the BigQuery dataset `raw`.

Raw layer rule: land the data as it is, every column as STRING.
Cleaning and type casting happen later, in the dbt staging models.

Run:
    python scripts/load_raw.py --data-dir "PATH\\TO\\KAGGLE\\FILES"
"""
import argparse
import json
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

PROJECT_ID = "loyalty-impact-analytics"
DATASET = "raw"

# Card numbers and CVV codes are never loaded, even though this data is synthetic.
SENSITIVE_CARD_COLUMNS = ["card_number", "cvv"]


def load_dataframe(client, df, table_name):
    """Upload a small pandas table, replacing the BigQuery table if it exists."""
    table_id = f"{PROJECT_ID}.{DATASET}.{table_name}"
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    client.load_table_from_dataframe(df, table_id, job_config=job_config).result()
    print(f"{table_name}: {client.get_table(table_id).num_rows:,} rows loaded")


def load_large_csv(client, csv_path, table_name):
    """Stream a large CSV straight to BigQuery without reading it into memory."""
    table_id = f"{PROJECT_ID}.{DATASET}.{table_name}"

    # Read only the header line to build an all-STRING schema.
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        columns = f.readline().strip().split(",")
    schema = [bigquery.SchemaField(col, "STRING") for col in columns]

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=schema,
        write_disposition="WRITE_TRUNCATE",
    )
    print(f"{table_name}: uploading {csv_path.stat().st_size / 1e9:.2f} GB, this takes a while...")
    with open(csv_path, "rb") as f:
        job = client.load_table_from_file(f, table_id, job_config=job_config)
        job.result()
    print(f"{table_name}: {client.get_table(table_id).num_rows:,} rows loaded")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True, help="Folder with the Kaggle files")
    data_dir = Path(parser.parse_args().data_dir)

    client = bigquery.Client(project=PROJECT_ID)

    users = pd.read_csv(data_dir / "users_data.csv", dtype=str)
    load_dataframe(client, users, "users")

    cards = pd.read_csv(data_dir / "cards_data.csv", dtype=str)
    cards = cards.drop(columns=SENSITIVE_CARD_COLUMNS)
    load_dataframe(client, cards, "cards")

    with open(data_dir / "mcc_codes.json", encoding="utf-8") as f:
        mcc = json.load(f)
    mcc_df = pd.DataFrame(list(mcc.items()), columns=["mcc", "description"])
    load_dataframe(client, mcc_df, "mcc_codes")

    load_large_csv(client, data_dir / "transactions_data.csv", "transactions")


if __name__ == "__main__":
    main()