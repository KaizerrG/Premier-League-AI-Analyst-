with player_xg as (
    select * from {{ ref('stg_player_xg') }}
),
team_level as (
    select
        team_name,
        season,
        sum(goals) as goals_scored,
        sum(xg) as total_xg
    from player_xg
    group by team_name, season
),
player_level as (
    select
        player_name,
        team_name,
        season,
        goals,
        xg,
        (goals - xg) as goals_minus_xg
    from player_xg
)
select
    'player' as entity_type,
    player_name as entity_name,
    team_name,
    season,
    goals,
    xg,
    goals_minus_xg as goals_vs_xg_delta
from player_level

union all

select
    'team' as entity_type,
    team_name as entity_name,
    team_name,
    season,
    goals_scored as goals,
    total_xg as xg,
    (goals_scored - total_xg) as goals_vs_xg_delta
from team_level
