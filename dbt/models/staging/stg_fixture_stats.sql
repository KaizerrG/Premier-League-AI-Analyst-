with source as (
    select * from {{ source('raw', 'fixture_stats') }}
),
renamed as (
    select
        id as fixture_stats_id,
        fixture_id,
        team_name,
        season,
        cast(shots_on_goal as integer) as shots_on_goal,
        cast(shots_off_goal as integer) as shots_off_goal,
        cast(total_shots as integer) as total_shots,
        cast(blocked_shots as integer) as blocked_shots,
        cast(shots_insidebox as integer) as shots_insidebox,
        cast(shots_outsidebox as integer) as shots_outsidebox,
        cast(fouls as integer) as fouls,
        cast(corners as integer) as corners,
        cast(offsides as integer) as offsides,
        cast(possession as numeric) as possession,
        cast(yellow_cards as integer) as yellow_cards,
        cast(red_cards as integer) as red_cards,
        cast(goalkeeper_saves as integer) as goalkeeper_saves,
        cast(total_passes as integer) as total_passes,
        cast(accurate_passes as integer) as accurate_passes,
        cast(pass_accuracy as numeric) as pass_accuracy,
        cast(expected_goals as numeric) as expected_goals,
        cast(goals_prevented as numeric) as goals_prevented,
        fetched_at
    from source
)
select * from renamed
