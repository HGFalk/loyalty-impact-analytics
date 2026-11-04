-- Business metrics: one row per customer per month, 2017-01 to 2019-10.
-- Includes zero-purchase months, so retention and frequency can be measured.

with months as (

    select month
    from unnest(generate_date_array('2017-01-01', '2019-10-01', interval 1 month)) as month

),

customers as (

    select distinct customer_id from {{ ref('int_purchases') }}

),

monthly as (

    select
        customer_id,
        transaction_month   as month,
        count(*)            as purchases,
        sum(amount)         as spend
    from {{ ref('int_purchases') }}
    group by 1, 2

),

members as (
    select * from {{ ref('stg_loyalty_members') }}
),

experiment as (
    select * from {{ ref('stg_experiment_assignments') }}
)

select
    concat(c.customer_id, '-', format_date('%Y-%m', m.month))   as customer_month_id,
    c.customer_id,
    m.month,
    coalesce(mo.purchases, 0)                                    as purchases,
    coalesce(mo.spend, 0)                                        as spend,
    coalesce(mo.purchases, 0) > 0                                as is_active,
    mem.enrolled_at,
    mem.enrolment_channel,
    case
        when mem.enrolled_at is null                                then 'non_member'
        when m.month <  date_trunc(date(mem.enrolled_at), month)    then 'before_joining'
        when m.month =  date_trunc(date(mem.enrolled_at), month)    then 'joining_month'
        else 'after_joining'
    end                                                          as membership_phase,
    e.variant                                                    as experiment_variant
from customers as c
cross join months as m
left join monthly    as mo  on mo.customer_id = c.customer_id and mo.month = m.month
left join members    as mem on mem.customer_id = c.customer_id
left join experiment as e   on e.customer_id = c.customer_id