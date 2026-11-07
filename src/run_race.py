"""Run one GlobalSim race between the first 3 scraped teams and print the results.

Usage:
    python src/run_race.py [--teams ../data/cm21_teams.json] [--seed 1]
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from globalsim import ChampionsMeeting, PreparedRace, RaceBuilder, Strategy, Uma, UmaBuilder

# CM21 = Capricorn Cup 2: Chukyo turf 1200m, Firm, Sunny, Winter, Midday. CM mood is Great.
CM = ChampionsMeeting.CAPRICORN_CUP_2
MOOD = 2


def build_race(teams, seed):
    race = RaceBuilder.champions_meeting(CM).seed(seed)
    for team_index, team in enumerate(teams):
        for member in team["members"]:
            race.runner(UmaBuilder.from_json(dict(member, teamId=team_index + 1)).mood(MOOD))
    return race


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--teams", type=Path, default=Path("../data/cm21_teams.json"))
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    teams = json.loads(args.teams.read_text(encoding="utf-8"))[:3]
    race = build_race(teams, args.seed)
    request = race.build()  # raises if any skill would be silently ignored by the engine
    horses = request.horses

    with PreparedRace(request) as prepared:
        replay = prepared.run(args.seed)
    metadata = replay.metadata
    if "error" in metadata:
        raise SystemExit(f"GlobalSim error: {metadata['error']}")

    skills_used = Counter(event["horseIndex"] for event in metadata["skillEvents"])
    results = sorted(enumerate(metadata["results"]), key=lambda item: item[1]["finishOrder"])
    winner_time = results[0][1]["finishTimeRaw"]

    print(race, end="\n\n")
    print(f"{'Pos':>3}  {'Team':>4}  {'Uma':<24}  {'Strategy':<12}  {'Time':>7}  {'Gap':>6}  {'Skills':>6}")
    for index, result in results:
        horse = horses[index]
        name = Uma(horse.extra["charaId"]).label
        strategy = Strategy(horse.strategy).name.replace("_", " ").title()
        print(f"{result['finishOrder'] + 1:>3}  {horse.extra['teamId']:>4}  {name:<24}  {strategy:<12}  "
              f"{result['finishTime']:>7.2f}  {result['finishTimeRaw'] - winner_time:>+6.2f}  "
              f"{skills_used[index]:>3}/{len(horse.extra['skills']):<2}")

    winning_team = horses[results[0][0]].extra["teamId"]
    print(f"\nWinning team: {winning_team} ({teams[winning_team - 1]['id'][:12]}...)")


if __name__ == "__main__":
    main()
