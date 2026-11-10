with fixtures as (
    select * from {{ ref('stg_fixtures') }}
),
team_points as (
    select
        home_team as team_name,
        case
            when home_goals > away_goals then 3
            when home_goals = away_goals then 1
            else 0
        end as points,
        case
            when home_goals > away_goals then 'W'
            when home_goals = away_goals then 'D'
            else 'L'
        end as result,
        match_date
    from fixtures

    union all

    select
        away_team as team_name,
        case
            when away_goals > home_goals then 3
            when away_goals = home_goals then 1
            else 0
        end as points,
        case
            when away_goals > home_goals then 'W'
            when away_goals = home_goals then 'D'
            else 'L'
        end as result,
        match_date
    from fixtures
),
ranked as (
    select
        team_name,
        result,
        points,
        match_date,
        row_number() over (
            partition by team_name
            order by match_date desc
        ) as match_rank
    from team_points
),
last_five as (
    select
        team_name,
        result,
        points,
        match_date,
        match_rank
    from ranked
    where match_rank <= 5
),
agg as (
    select
        team_name,
        count(*) as matches_last_5,
        sum(points) as points_last_5,
        sum(case when result = 'W' then 1 else 0 end) as wins_last_5,
        sum(case when result = 'D' then 1 else 0 end) as draws_last_5,
        sum(case when result = 'L' then 1 else 0 end) as losses_last_5,
        max(match_date) as latest_match_date
    from last_five
    group by team_name
)
select * from agg
