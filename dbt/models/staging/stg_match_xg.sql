with source as (
    select * from {{ source('raw', 'match_xg') }}
),
renamed as (
    select
        id as match_xg_id,
        league,
        season,
        match_id,
        home_team,
        away_team,
        cast(home_xg as numeric) as home_xg,
        cast(away_xg as numeric) as away_xg,
        cast(match_date as text) as match_date,
        fetched_at
    from source
)
select * from renamed
