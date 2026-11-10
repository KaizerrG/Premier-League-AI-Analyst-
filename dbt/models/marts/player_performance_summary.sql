with player_stats as (
    select * from {{ ref('stg_player_xg') }}
),
fixtures as (
    select * from {{ ref('stg_fixtures') }}
),
shots as (
    select * from {{ ref('stg_shots') }}
),
player_fixture_impact as (
    select
        p.player_stat_id,
        p.player_name,
        p.team_name,
        p.league,
        p.season,
        p.games,
        p.minutes,
        p.goals,
        p.assists,
        p.xg,
        p.xa,
        p.npxg,
        p.shots,
        p.key_passes,
        p.xgchain,
        p.xgbuildup,
        count(distinct s.shot_id) as total_shots_taken,
        sum(case when s.result in ('Goal', 'Own Goal', 'Penalty') then 1 else 0 end) as goals_from_shots,
        sum(case when s.result = 'SavedShot' then 1 else 0 end) as saved_shots,
        sum(case when s.result = 'MissedShots' then 1 else 0 end) as missed_shots
    from player_stats p
    left join shots s
        on lower(trim(p.player_name)) = lower(trim(s.player_name))
        and lower(trim(p.team_name)) = lower(trim(s.team_name))
        and p.season = s.season
    group by
        p.player_stat_id,
        p.player_name,
        p.team_name,
        p.league,
        p.season,
        p.games,
        p.minutes,
        p.goals,
        p.assists,
        p.xg,
        p.xa,
        p.npxg,
        p.shots,
        p.key_passes,
        p.xgchain,
        p.xgbuildup
)
select * from player_fixture_impact
