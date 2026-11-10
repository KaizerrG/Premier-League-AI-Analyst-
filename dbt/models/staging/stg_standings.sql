with source as (
    select * from {{ source('raw', 'standings') }}
),
renamed as (
    select
        id as standing_id,
        league,
        season,
        cast(rank as integer) as rank,
        team_name,
        cast(played as integer) as played,
        cast(won as integer) as won,
        cast(drawn as integer) as drawn,
        cast(lost as integer) as lost,
        cast(goals_for as integer) as goals_for,
        cast(goals_against as integer) as goals_against,
        cast(goal_difference as integer) as goal_difference,
        cast(xg as numeric) as xg,
        cast(xga as numeric) as xga,
        cast(points as integer) as points,
        fetched_at
    from source
)
select * from renamed
