-- Cleaned: completed purchases only, within the analysis window.
-- Window: 2017 (baseline), 2018 (programme year), Jan to Oct 2019 (follow-up).

{{ config(
    materialized='table',
    cluster_by=['customer_id']
) }}

select
    transaction_id,
    transaction_at,
    date_trunc(date(transaction_at), month)   as transaction_month,
    customer_id,
    card_id,
    amount,
    payment_method,
    merchant_id,
    mcc,
    is_planted
from {{ ref('stg_transactions') }}
where transaction_at >= '2017-01-01'
  and transaction_at <  '2019-11-01'
  and amount > 0                 -- drop refunds
  and error_message is null      -- drop failed payments