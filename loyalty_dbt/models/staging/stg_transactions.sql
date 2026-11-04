-- Staging: one row per card transaction, typed and renamed.
-- Combines the Kaggle transactions with the planted Points+ effect rows.

with kaggle as (

    select
        id, date, client_id, card_id, amount, use_chip,
        merchant_id, merchant_city, merchant_state, zip, mcc, errors,
        false as is_planted
    from {{ source('raw', 'transactions') }}

),

planted as (

    select
        id, date, client_id, card_id, amount, use_chip,
        merchant_id, merchant_city, merchant_state, zip, mcc, errors,
        true as is_planted
    from {{ source('raw', 'extra_transactions') }}

),

combined as (

    select * from kaggle
    union all
    select * from planted

)

select
    id                                                   as transaction_id,
    timestamp(date)                                      as transaction_at,
    client_id                                            as customer_id,
    card_id,
    safe_cast(replace(amount, '$', '') as numeric)       as amount,
    use_chip                                             as payment_method,
    merchant_id,
    merchant_city,
    merchant_state,
    zip,
    mcc,
    nullif(errors, '')                                   as error_message,
    is_planted
from combined