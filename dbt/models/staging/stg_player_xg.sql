with source as (
    select * from {{ source('raw', 'player_xg') }}
),
renamed as (
    select
        id as player_stat_id,
        league,
        season,
        player_name,
        team_name,
        position,
        cast(games as integer) as games,
        cast(minutes as integer) as minutes,
        cast(goals as integer) as goals,
        cast(assists as integer) as assists,
        cast(xg as numeric) as xg,
        cast(xa as numeric) as xa,
        cast(npxg as numeric) as npxg,
        cast(shots as integer) as shots,
        cast(key_passes as integer) as key_passes,
        cast(xgchain as numeric) as xgchain,
        cast(xgbuildup as numeric) as xgbuildup,
        cast(yellow_cards as integer) as yellow_cards,
        cast(red_cards as integer) as red_cards,
        fetched_at
    from source
)
select * from renamed
