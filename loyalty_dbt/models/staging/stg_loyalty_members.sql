-- Staging: one row per Points+ member.

select
    client_id                as customer_id,
    timestamp(enrolled_at)   as enrolled_at,
    channel                  as enrolment_channel
from {{ source('raw', 'loyalty_members') }}