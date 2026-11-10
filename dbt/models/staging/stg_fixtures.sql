with source as (
    select * from {{ source('raw', 'fixtures') }}
),
renamed as (
    select
        id as fixture_id,
        league,
        season,
        cast(fixture_id as text) as fixture_key,
        home_team,
        away_team,
        cast(home_goals as integer) as home_goals,
        cast(away_goals as integer) as away_goals,
        cast(home_xg as numeric) as home_xg,
        cast(away_xg as numeric) as away_xg,
        cast(home_win_prob as numeric) as home_win_prob,
        cast(draw_prob as numeric) as draw_prob,
        cast(away_win_prob as numeric) as away_win_prob,
        cast(match_date as text) as match_date,
        fetched_at
    from source
)
select * from renamed
