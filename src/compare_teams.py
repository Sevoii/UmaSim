"""Compare two teams on identical races against random opponents from a team list.

Each trial draws a random race seed, 2 random opponent teams, and a random gate
permutation. The same seed, opponents, and gates are then used for team A and team B,
so the only difference between the two races is which team is being tested: the
runner in team slot k gets the same gate in both races.

Team A and team B are JSON files holding either {"id": ..., "members": [...]} or a
list of 3 runners. Teams in the list with the same id are excluded from the opponents.

Usage:
    python src/compare_teams.py 21 data/cm21_teams.json team_a.json team_b.json --trials 1000
"""
import argparse
import json
import math
import os
import random
import re
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from statistics import NormalDist, fmean, stdev

from globalsim import ChampionsMeeting, PreparedRace, RaceBuilder, Strategy, Uma, UmaBuilder
from tqdm import tqdm

from cm_names import CM_NAMES

MOOD = 2  # Champions Meeting runners are at Great mood
SKILL_LINE = re.compile(r"^    .*  #(\d+)\s+Lv\d")  # a skill row in UmaBuilder's summary
TEAM_SIZE = 3
FIELD_SIZE = 9
SEED_MAX = 2 ** 31 - 1  # the retail runtime requires signed 32-bit seeds


def parse_cm(value):
    """Resolve a meeting number, CM ID, or GlobalSim preset name."""
    value = value.strip()
    match = re.fullmatch(r"(?:cm)?(\d+)", value, re.IGNORECASE)
    if match:
        number = int(match.group(1))
        if not 1 <= number <= len(CM_NAMES):
            raise argparse.ArgumentTypeError(f"Unknown meeting number {number}; supported: 1-{len(CM_NAMES)}")
        parts = CM_NAMES[number - 1].split()
        value = parts[0].upper() + "_CUP" + ("_" + parts[1] if len(parts) > 1 else "")
    try:
        return ChampionsMeeting[value.upper()]
    except KeyError:
        raise argparse.ArgumentTypeError(f"Unknown Champions Meeting preset: {value}") from None


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
    return (orders, distances_from_top(replay, race.course.distance), time_gaps(results),
            activated_skills(replay.metadata, len(results)))


def activated_skills(metadata, horse_count):
    """Per runner, the set of skill IDs (as strings) that activated at least once."""
    activated = [set() for _ in range(horse_count)]
    for event in metadata["skillEvents"]:
        skill_id = event["skillId"]
        if isinstance(skill_id, str) and not skill_id.isdecimal():
            continue  # non-skill events such as "kakari" (rushing)
        activated[event["horseIndex"]].add(str(int(skill_id)))
    return activated


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
        self.win_count = 0
        self.places = [[] for _ in range(TEAM_SIZE)]  # 1 = 1st
        self.distances = [[] for _ in range(TEAM_SIZE)]
        self.times = [[] for _ in range(TEAM_SIZE)]
        self.skill_procs = [Counter() for _ in range(TEAM_SIZE)]  # races each skill activated in

    def add(self, orders, distances, times, skills):
        self.wins.append(int(min(orders[:TEAM_SIZE]) == 0))
        self.win_count += self.wins[-1]
        for k in range(TEAM_SIZE):
            self.places[k].append(orders[k] + 1)
            self.distances[k].append(distances[k])
            self.times[k].append(times[k])
            self.skill_procs[k].update(skills[k])


# Per-process state for batched runs, set once by init_worker so each task only
# carries (seed, opponent indices, gates) instead of the full team data.
_WORKER = {}


def init_worker(cm_name, team_a, team_b, pool):
    _WORKER.update(cm=ChampionsMeeting[cm_name], team_a=team_a, team_b=team_b, pool=pool)


def run_paired_trial(trial):
    """Run one trial for both tested teams with the same seed, opponents and gates."""
    seed, opponent_indices, gates = trial
    opponents = [_WORKER["pool"][i] for i in opponent_indices]
    return (run_trial(_WORKER["cm"], _WORKER["team_a"], opponents, seed, gates),
            run_trial(_WORKER["cm"], _WORKER["team_b"], opponents, seed, gates))


def run_all(trials, init_args, tally_a, tally_b, label, workers, batch_size):
    """Run every trial (in a process pool when workers > 1), recording results in trial order."""
    bar = tqdm(total=len(trials), desc=label, unit="trial", dynamic_ncols=True, file=sys.stderr)

    def record(result):
        result_a, result_b = result
        tally_a.add(*result_a)
        tally_b.add(*result_b)
        bar.set_postfix({"A wins": tally_a.win_count, "B wins": tally_b.win_count}, refresh=False)
        bar.update()

    executor = None
    try:
        if workers == 1:
            init_worker(*init_args)
            for trial in trials:
                record(run_paired_trial(trial))
        else:
            executor = ProcessPoolExecutor(workers, initializer=init_worker, initargs=init_args)
            for result in executor.map(run_paired_trial, trials, chunksize=batch_size):
                record(result)
    finally:
        # Close the bar first so any traceback or the summary starts on a clean line, and
        # drop queued batches instead of waiting for them when interrupted.
        bar.close()
        if executor is not None:
            executor.shutdown(wait=True, cancel_futures=True)


def stat_line(tally, k, z):
    place, place_half = mean_ci(tally.places[k], z)
    metres, metres_half = mean_ci(tally.distances[k], z)
    secs, secs_half = mean_ci(tally.times[k], z)
    return (f"avg place {place:.2f} ± {place_half:.2f}   avg from top {metres:.2f} ± {metres_half:.2f} m   "
            f"{secs:.2f} ± {secs_half:.2f} s")


def win_rate_line(tally, n, z, level):
    low, high = wilson_ci(tally.win_count, n, z)
    return f"Team win rate  {tally.win_count / n:.1%}  ({level} {low:.1%} to {high:.1%})"


def print_full(name, tally, n, z, level):
    print("=" * 72)
    print(f"{name}: {tally.name}  ({team_label(tally.team)})")
    print(win_rate_line(tally, n, z, level))
    print("=" * 72)
    for k, member in enumerate(tally.team["members"]):
        print()
        print(with_proc_rates(str(UmaBuilder.from_json(member).mood(MOOD)), tally.skill_procs[k], n))
        print(f"  {'Results':<10} {stat_line(tally, k, z)}")
    print()


def with_proc_rates(summary, procs, n):
    """Append each skill's proc rate (% of races it activated in) to the UmaBuilder summary."""
    lines = summary.splitlines()
    skill_lines = [i for i, line in enumerate(lines) if SKILL_LINE.match(line)]
    if skill_lines:
        width = max(len(lines[i]) for i in skill_lines)
        for i in skill_lines:
            skill_id = SKILL_LINE.match(lines[i]).group(1)
            lines[i] = f"{lines[i]:<{width}}  {procs[skill_id] / n:6.1%} procs"
    return "\n".join(lines)


def print_compact(name, tally, n, z, level):
    print(f"{name}: {tally.name}")
    print(f"  {win_rate_line(tally, n, z, level)}")
    for k, member in enumerate(tally.team["members"]):
        label = f"{Uma(member['charaId']).label} ({Strategy(member['strategy']).name.replace('_', ' ').title()})"
        print(f"    {label:<32} {stat_line(tally, k, z)}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cm", type=parse_cm, metavar="CM",
                        help="Meeting number, ID, or preset name, e.g. 21, cm21, or CAPRICORN_CUP_2")
    parser.add_argument("teams", type=Path, help="Team list JSON (opponent pool)")
    parser.add_argument("team_a", type=Path, help="Team A JSON file")
    parser.add_argument("team_b", type=Path, help="Team B JSON file")
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--confidence", type=float, default=0.95, help="Confidence level (default 0.95)")
    parser.add_argument("--rng-seed", type=int, help="Seed for trial generation (for reproducible runs)")
    parser.add_argument("--workers", type=int, default=os.cpu_count(),
                        help="Processes running trials in parallel (default: all cores; 1 = no pool)")
    parser.add_argument("--batch-size", type=int, default=16,
                        help="Trials sent to a worker at a time (default 16)")
    parser.add_argument("--compact", action="store_true",
                        help="Print one line per Uma instead of the full runner summaries")
    args = parser.parse_args()
    if args.trials < 2:
        parser.error("--trials must be at least 2 for a confidence interval")
    if args.workers < 1 or args.batch_size < 1:
        parser.error("--workers and --batch-size must be at least 1")

    cm = args.cm
    z = NormalDist().inv_cdf(0.5 + args.confidence / 2)
    teams = json.loads(args.teams.read_text(encoding="utf-8"))
    team_a, team_b = load_team(args.team_a), load_team(args.team_b)
    tested_ids = {team_a["id"], team_b["id"]}
    pool = [team for team in teams if team["id"] not in tested_ids]
    if len(pool) < 2:
        raise SystemExit("The team list needs at least 2 opponent teams besides the tested teams")

    # Draw every trial up front so results are identical for any --workers value.
    rng = random.Random(args.rng_seed)
    trials = []
    for _ in range(args.trials):
        seed = rng.randint(0, SEED_MAX)
        opponent_indices = rng.sample(range(len(pool)), 2)
        gates = rng.sample(range(FIELD_SIZE), FIELD_SIZE)
        trials.append((seed, opponent_indices, gates))

    tally_a, tally_b = Tally(team_a, args.team_a.stem), Tally(team_b, args.team_b.stem)
    run_all(trials, (cm.name, team_a, team_b, pool), tally_a, tally_b, cm.label,
            min(args.workers, args.trials), args.batch_size)

    n = args.trials
    level = f"{args.confidence:.0%} CI"
    print(f"\n{cm.label}: {n} trials against {len(pool)} possible opponent teams ({level})\n")
    for name, tally in (("A", tally_a), ("B", tally_b)):
        (print_compact if args.compact else print_full)(name, tally, n, z, level)

    # Both teams race the same seeds, opponents and gates, so compare them per trial.
    difference, half = paired_difference_ci([a - b for a, b in zip(tally_a.wins, tally_b.wins)], z)
    print(f"Team win % difference ({tally_a.name} - {tally_b.name}): {difference:+.1%}  "
          f"({level} {difference - half:+.1%} to {difference + half:+.1%})")


if __name__ == "__main__":
    main()
