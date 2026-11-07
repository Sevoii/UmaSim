"""Compare two teams on identical races against random opponents from a team list.

Each trial draws a random race seed, 2 random opponent teams, and a random gate
permutation. The same seed, opponents, and gates are then used for team A and team B,
so the only difference between the two races is which team is being tested: the
runner in team slot k gets the same gate in both races.

Team A and team B are JSON files holding either {"id": ..., "members": [...]} or a
list of 3 runners. Teams in the list with the same id are excluded from the opponents.

Usage:
    python src/compare_teams.py CAPRICORN_CUP_2 ../data/cm21_teams.json team_a.json team_b.json --trials 1000
"""
import argparse
import json
import math
import random
from pathlib import Path
from statistics import NormalDist, fmean, stdev

from globalsim import ChampionsMeeting, PreparedRace, RaceBuilder, Strategy, Uma, UmaBuilder
from tqdm import tqdm

MOOD = 2  # Champions Meeting runners are at Great mood
TEAM_SIZE = 3
FIELD_SIZE = 9
SEED_MAX = 2 ** 31 - 1  # the retail runtime requires signed 32-bit seeds


def load_team(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    team = data if isinstance(data, dict) else {"id": Path(path).stem, "members": data}
    if len(team["members"]) != TEAM_SIZE:
        raise ValueError(f"{path}: a team needs exactly {TEAM_SIZE} members")
    team.setdefault("id", Path(path).stem)
    return team


def team_label(team):
    return ", ".join(f"{Uma(m['charaId']).label} ({Strategy(m['strategy']).name.replace('_', ' ').title()})"
                     for m in team["members"])


def distances_from_top(replay, course_distance):
    """Metres each runner is behind the line when the winner crosses it.

    Frames are sampled every 1/15 s, so the winner's exact finish time falls between
    two frames. Take the last frame at or before it and advance every runner from
    there by speed * (finish time - frame time).
    """
    winner_time = min(result["finishTimeRaw"] for result in replay.metadata["results"])
    index = replay.count - 1
    while index > 0 and replay.frame(index)[0] > winner_time:
        index -= 1
    frame_time, values = replay.frame(index)
    dt = winner_time - frame_time
    gaps = []
    for i in range(replay.horse_count):
        position, speed = values[6 * i], values[6 * i + 1]
        gaps.append(max(0.0, course_distance - (position + speed * dt)))
    return gaps


def time_gaps(results):
    """Seconds each runner finished after the winner (exact, unrounded finish times)."""
    winner_time = min(result["finishTimeRaw"] for result in results)
    return [result["finishTimeRaw"] - winner_time for result in results]


def run_trial(cm, tested, opponents, seed, gates):
    """Race the tested team (slots 0-2) against the opponents (slots 3-8).

    Returns per-runner lists: (finish orders with 0 = 1st, metres behind the winner when
    it finishes, seconds behind the winner's finish time).
    """
    race = RaceBuilder.champions_meeting(cm).seed(seed)
    lineup = [tested, *opponents]
    slot = 0
    for team_number, team in enumerate(lineup, 1):
        for member in team["members"]:
            runner = dict(member, teamId=team_number, gateIndex=gates[slot])
            race.runner(UmaBuilder.from_json(runner).mood(MOOD))
            slot += 1
    request = race.build()
    request.extra["retainAllFrames"] = True
    with PreparedRace(request) as prepared:
        replay = prepared.run(seed)
    if "error" in replay.metadata:
        raise RuntimeError(f"GlobalSim error: {replay.metadata['error']}")
    results = replay.metadata["results"]
    orders = [result["finishOrder"] for result in results]
    return orders, distances_from_top(replay, race.course.distance), time_gaps(results)


def mean_ci(values, z):
    """(mean, half-width) of a normal-approximation confidence interval."""
    if len(values) < 2:
        return fmean(values), math.inf
    return fmean(values), z * stdev(values) / math.sqrt(len(values))


def paired_difference_ci(differences, z):
    """(mean, half-width) for per-trial differences in {-1, 0, +1}.

    The plain normal interval has zero width when every difference is equal (e.g. neither
    team ever wins), so the half-width adds one +1 and one -1 pseudo-observation.
    """
    mean = fmean(differences)
    padded = [*differences, 1, -1]
    return mean, z * stdev(padded) / math.sqrt(len(differences))


def wilson_ci(successes, n, z):
    """Wilson score interval for a proportion."""
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


class Tally:
    def __init__(self, team, name):
        self.team = team
        self.name = name
        self.wins = []  # 1 if a team member finished 1st, per trial
        self.places = [[] for _ in range(TEAM_SIZE)]  # 1 = 1st
        self.distances = [[] for _ in range(TEAM_SIZE)]
        self.times = [[] for _ in range(TEAM_SIZE)]

    def add(self, orders, distances, times):
        self.wins.append(int(min(orders[:TEAM_SIZE]) == 0))
        for k in range(TEAM_SIZE):
            self.places[k].append(orders[k] + 1)
            self.distances[k].append(distances[k])
            self.times[k].append(times[k])


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cm", choices=[cm.name for cm in ChampionsMeeting], metavar="CM",
                        help="ChampionsMeeting preset name, e.g. CAPRICORN_CUP_2")
    parser.add_argument("teams", type=Path, help="Team list JSON (opponent pool)")
    parser.add_argument("team_a", type=Path, help="Team A JSON file")
    parser.add_argument("team_b", type=Path, help="Team B JSON file")
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--confidence", type=float, default=0.95, help="Confidence level (default 0.95)")
    parser.add_argument("--rng-seed", type=int, help="Seed for trial generation (for reproducible runs)")
    args = parser.parse_args()
    if args.trials < 2:
        parser.error("--trials must be at least 2 for a confidence interval")

    cm = ChampionsMeeting[args.cm]
    z = NormalDist().inv_cdf(0.5 + args.confidence / 2)
    teams = json.loads(args.teams.read_text(encoding="utf-8"))
    team_a, team_b = load_team(args.team_a), load_team(args.team_b)
    tested_ids = {team_a["id"], team_b["id"]}
    pool = [team for team in teams if team["id"] not in tested_ids]
    if len(pool) < 2:
        raise SystemExit("The team list needs at least 2 opponent teams besides the tested teams")

    rng = random.Random(args.rng_seed)
    tally_a, tally_b = Tally(team_a, args.team_a.stem), Tally(team_b, args.team_b.stem)
    progress = tqdm(range(args.trials), desc=cm.label, unit="trial")
    for _ in progress:
        seed = rng.randint(0, SEED_MAX)
        opponents = rng.sample(pool, 2)
        gates = rng.sample(range(FIELD_SIZE), FIELD_SIZE)
        tally_a.add(*run_trial(cm, team_a, opponents, seed, gates))
        tally_b.add(*run_trial(cm, team_b, opponents, seed, gates))
        progress.set_postfix({"A wins": sum(tally_a.wins), "B wins": sum(tally_b.wins)}, refresh=False)

    n = args.trials
    level = f"{args.confidence:.0%} CI"
    print(f"\n{cm.label}: {n} trials against {len(pool)} possible opponent teams\n")
    for name, tally in (("A", tally_a), ("B", tally_b)):
        low, high = wilson_ci(sum(tally.wins), n, z)
        print("=" * 72)
        print(f"{name}: {tally.name}  ({team_label(tally.team)})")
        print(f"Team win rate  {sum(tally.wins) / n:.1%}  ({level} {low:.1%} to {high:.1%})")
        print("=" * 72)
        for k, member in enumerate(tally.team["members"]):
            metres, metres_half = mean_ci(tally.distances[k], z)
            secs, secs_half = mean_ci(tally.times[k], z)
            place, place_half = mean_ci(tally.places[k], z)
            print()
            print(UmaBuilder.from_json(member).mood(MOOD))
            print(f"  {'Results':<10} ({level})")
            print(f"    {'Avg placement':<16} {place:.2f} ± {place_half:.2f}")
            print(f"    {'Avg from top':<16} {metres:.2f} ± {metres_half:.2f} m   {secs:.2f} ± {secs_half:.2f} s")
        print()

    # Both teams race the same seeds, opponents and gates, so compare them per trial.
    difference, half = paired_difference_ci([a - b for a, b in zip(tally_a.wins, tally_b.wins)], z)
    print(f"Team win % difference ({tally_a.name} - {tally_b.name}): {difference:+.1%}  "
          f"({level} {difference - half:+.1%} to {difference + half:+.1%})")


if __name__ == "__main__":
    main()
