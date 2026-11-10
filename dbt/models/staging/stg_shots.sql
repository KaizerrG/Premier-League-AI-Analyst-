with source as (
    select * from {{ source('raw', 'shots') }}
),
renamed as (
    select
        id as shot_id,
        league,
        season,
        player_name,
        team_name,
        cast(x as numeric) as x_coord,
        cast(y as numeric) as y_coord,
        cast(xg as numeric) as xg,
        result,
        match_id,
        cast(minute as integer) as minute,
        situation,
        fetched_at
    from source
)
select * from renamed
