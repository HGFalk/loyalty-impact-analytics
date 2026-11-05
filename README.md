# Does a loyalty programme make customers buy more?

**Live app:** [loyalty-impact.streamlit.app](https://loyalty-impact.streamlit.app)

An end-to-end analytics project: 13.3 million card transactions loaded into **BigQuery**, modelled and tested with **dbt**, analysed in **Python** and presented in a **Streamlit** app. A fictional loyalty programme, Points+, is layered on public data with a known, planted effect, so every measurement method can be checked against the right answer.

## Recommendation

1. **Do not judge Points+ by comparing members with non-members.** That comparison shows +17.6%, but future members already bought 13.1% more in 2017, before the programme existed. Most of the gap is who joins, not what the programme does.
2. **The real effect on members is small and positive.** Members buy 3.1% more after joining than before. The planted true effect is +5%.
3. **Invitations work.** In a randomised test, invited customers joined at 36% versus 13% without an invitation. Purchases per invited customer rose 1.2% (95% interval +0.6% to +1.8%). Spread over the extra joiners, that is about +5.1% per joiner, close to the planted +5%.
4. **Before scaling, add costs.** Points costs and redemptions are not in this data. They decide whether a 3 to 5% lift in purchases pays for the programme.

## Why it matters

The simple member vs non-member comparison would have overstated the programme's effect more than three times. A team using it would over-invest in loyalty spend and set targets the programme cannot meet. The randomised invitation test, analysed against each customer's own baseline, gave an answer close to the truth with about 560 customers per group.

| Method | Measured effect | True effect | Verdict |
|---|---|---|---|
| Members vs non-members (2019) | +17.6% | +5% | Badly overstated by selection |
| Members, after vs before joining | +3.1% | +5% | Right direction, understated |
| Raw experiment, invited vs control | -6.4% | about +1% per invited customer | Misleading: groups differed before the test |
| Experiment adjusted for each group's baseline | +1.2% per invited customer, about +5.1% per joiner | +5% per joiner | Closest to the truth |

## How it works

```
Kaggle CSV files
   │  scripts/load_raw.py          Python, all columns landed as STRING
   ▼
BigQuery  raw dataset
   │  scripts/generate_loyalty.py  synthetic Points+ members, experiment, planted +5% effect
   ▼
dbt  (loyalty_dbt/)
   staging       stg_transactions, stg_loyalty_members, stg_experiment_assignments   (views)
   intermediate  int_purchases       completed purchases 2017-01 to 2019-10           (table, clustered)
   marts         fct_customer_month  one row per customer per month, incl. zero months
   │  scripts/export_marts.py
   ▼
app/data/fct_customer_month.parquet  →  Streamlit app (app/streamlit_app.py)
```

- **5 dbt models, 18 data tests, 7 sources**, all passing.
- **41,208 rows** in the final table: 1,212 customers × 34 months, with no gaps or duplicates.

### Design decisions

- **Raw data lands untyped.** All raw columns are STRING; casting and renaming happen in dbt staging, so a bad value fails a test instead of a load.
- **Sensitive fields never loaded.** Card numbers and CVV codes are dropped before upload, even though the data is synthetic.
- **The planted effect is traceable.** Extra purchases sit in their own table and carry an `is_planted` flag, so the effect can be audited.
- **Clustered, not partitioned.** The BigQuery free sandbox expires partitions older than 60 days immediately, and this data is from 2017 to 2019. Clustering by customer gives the speed-up without losing data.
- **The app reads an exported file, not BigQuery.** It needs no credentials and keeps working after sandbox tables expire.
- **Pinned versions.** A pre-release dbt version caused silent failures during the build; `requirements.txt` pins every package.
- **dbt Core v1, not v2.** v1 is fully supported and still the most common in production. The models use standard SQL and YAML that carry over to v2.

## The synthetic layer

The Kaggle data has no loyalty programme, so `scripts/generate_loyalty.py` creates one with a fixed random seed:

- Points+ launches on 1 March 2018. Customers who bought more in 2017 are more likely to join on their own (10% to 30% by activity quartile). This builds in selection bias on purpose.
- On 1 September 2018, active non-members are split 50/50 at random. Invited customers accept at 25%; control customers can still join on their own.
- Members make 5% more purchases after joining. This is implemented by copying a repeatable 5% sample of their post-joining purchases.

## Reproduce it

Requires Python 3.12 and a Google Cloud project with BigQuery (the free sandbox is enough).

```bash
pip install -r requirements.txt
python scripts/load_raw.py --data-dir PATH/TO/KAGGLE/FILES
python scripts/generate_loyalty.py
cd loyalty_dbt && dbt build && cd ..
python scripts/export_marts.py
streamlit run app/streamlit_app.py
```

The dbt profile (`~/.dbt/profiles.yml`) uses `method: oauth`, dataset `analytics`, location `EU`.

## Limitations and next steps

- Costs, points redemption and margins are not in the data, so the analysis measures purchases, not profit.
- Members' before/after lift (3.1%) is below the true 5%. A likely cause is that members were partly selected on an unusually strong 2017; this has not been verified yet.
- Monthly purchase counts dip every February because the month is shorter. Purchases per day would remove this.
- Next: add spend-based metrics, a per-day view, and an automated dbt run in CI.

## Data and credits

- Transactions, customers and cards: [Financial Transactions Dataset: Analytics](https://www.kaggle.com/datasets/computingvictor/transactions-fraud-datasets) by ComputingVictor on Kaggle, licensed under Apache 2.0.
- The Points+ programme, the invitation experiment and the +5% effect are synthetic and created for this project.
- Built with AI-assisted coding (Claude). I directed the design, reviewed and tested the code, and checked every result against the planted truth.

## Author

Homa Ghasemi Falk, [github.com/HGFalk](https://github.com/HGFalk)
