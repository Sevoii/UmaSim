"""Convert a captured race JSON (game client race data) into a team file.

Writes {"id": ..., "members": [<GlobalSim horse>, ...]}, the format compare_teams.py
takes for team A / team B. By default the player's own team is converted; use
--team-id to pick another team in the race.

Usage:
    python src/convert_race.py "Taiki Shuttle-54.8286s-20261106.json" -o ../data/my_team.json
"""
import argparse
import json
from pathlib import Path

from globalsim import Aptitude, Strategy, Uma

from scrape_umalogs import to_skill

# Client aptitude codes: 1 = G ... 8 = S.
APTITUDES = {1: "G", 2: "F", 3: "E", 4: "D", 5: "C", 6: "B", 7: "A", 8: "S"}
STRATEGIES = {1: Strategy.FRONT_RUNNER, 2: Strategy.PACE_CHASER, 3: Strategy.LATE_SURGER,
              4: Strategy.END_CLOSER}
DISTANCE_KEYS = {"Short": "proper_distance_short", "Mile": "proper_distance_mile",
                 "Middle": "proper_distance_middle", "Long": "proper_distance_long"}
SURFACE_KEYS = {1: "proper_ground_turf", 2: "proper_ground_dirt"}
STRATEGY_KEYS = {Strategy.FRONT_RUNNER: "proper_running_style_nige",
                 Strategy.RUNAWAY: "proper_running_style_nige",
                 Strategy.PACE_CHASER: "proper_running_style_senko",
                 Strategy.LATE_SURGER: "proper_running_style_sashi",
                 Strategy.END_CLOSER: "proper_running_style_oikomi"}


def aptitude(code):
    return Aptitude(APTITUDES[code]).value


def strategy_of(horse):
    """Runaway is stored as running_style 1 with runningStyleEx set, so check the extension first."""
    extended = str(horse.get("runningStyleEx", "None"))
    if extended.lower() in ("oonige", "runaway"):
        return Strategy.RUNAWAY
    if extended != "None":
        raise ValueError(f"Unknown runningStyleEx {extended!r} for {horse['charaName']}")
    return STRATEGIES[horse["responseHorseData"]["running_style"]]


def to_runner(horse, distance_key, surface_key):
    data = horse["responseHorseData"]
    strategy = strategy_of(horse)
    return {
        "speed": data["speed"],
        "stamina": data["stamina"],
        "power": data["pow"],
        "guts": data["guts"],
        "wisdom": data["wiz"],
        "strategy": strategy.value,
        "distanceAptitude": aptitude(data[distance_key]),
        "surfaceAptitude": aptitude(data[surface_key]),
        "strategyAptitude": aptitude(data[STRATEGY_KEYS[strategy]]),
        "charaId": int(Uma(data["chara_id"])),
        "skills": [to_skill(skill["skill_id"], skill["level"]) for skill in data["skill_array"]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("race", type=Path, help="Captured race JSON")
    parser.add_argument("-o", "--out", type=Path, required=True, help="Output team JSON")
    parser.add_argument("--team-id", type=int, help="Team to convert (default: the player's team)")
    parser.add_argument("--id", help="Team id to write (default: race file name and team id)")
    args = parser.parse_args()

    race = json.loads(args.race.read_text(encoding="utf-8"))
    distance_key = DISTANCE_KEYS[race["courseDistanceType"]]
    surface_key = SURFACE_KEYS[race["raceCourseSet"]["ground"]]

    team_id = args.team_id
    if team_id is None:
        team_id = race["playerTeamMemberArray"][0]["responseHorseData"]["team_id"]
    horses = sorted((h for h in race["raceHorse"] if h["responseHorseData"]["team_id"] == team_id),
                    key=lambda h: h["responseHorseData"]["team_member_id"])
    if not horses:
        teams = sorted({h["responseHorseData"]["team_id"] for h in race["raceHorse"]})
        raise SystemExit(f"No team {team_id} in this race; teams are {teams}")

    team = {"id": args.id or f"{args.race.stem}-team{team_id}",
            "members": [to_runner(h, distance_key, surface_key) for h in horses]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(team, indent=2), encoding="utf-8")

    print(f"Team {team_id} ({horses[0]['trainerName']}) -> {args.out}")
    for horse, member in zip(horses, team["members"]):
        print(f"  {horse['charaName']:<20} {Strategy(member['strategy']).name.replace('_', ' ').title():<12} "
              f"{member['speed']}/{member['stamina']}/{member['power']}/{member['guts']}/{member['wisdom']}  "
              f"apt {member['distanceAptitude']}{member['surfaceAptitude']}{member['strategyAptitude']}  "
              f"{len(member['skills'])} skills")


if __name__ == "__main__":
    main()
