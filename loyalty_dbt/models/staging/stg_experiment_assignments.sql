-- Staging: one row per customer in the invitation experiment.

select
    client_id                as customer_id,
    variant,
    timestamp(assigned_at)   as assigned_at
from {{ source('raw', 'experiment_assignments') }}
