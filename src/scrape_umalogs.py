"""Scrape the top teams for a Champions Meeting from hakuraku.moe UmaLogs.

Writes ``{out}/cm21_teams.json`` as ``[{"id": str, "members": [<GlobalSim horse>, ...]}]``.

Usage:
    python src/scrape_umalogs.py cm21 --out data/cm21 [--limit 100] [--snapshot ID]
"""
import argparse
import json
from pathlib import Path

import requests
from globalsim import Aptitude, Skill, Strategy, Uma

API = "https://hakuraku.moe/api/simdata"
PAGE_SIZE = 100
# hakuraku racingStyle -> GlobalSim strategy (style 6 "Debuffer" is a label; racingStyle is the real style).
STRATEGIES = {1: Strategy.FRONT_RUNNER, 2: Strategy.PACE_CHASER, 3: Strategy.LATE_SURGER,
              4: Strategy.END_CLOSER, 5: Strategy.RUNAWAY}

session = requests.Session()
session.headers["User-Agent"] = "UmaSim-scraper"


def fetch_json(url, params=None):
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def latest_snapshot(cm_id):
    manifest = fetch_json(f"{API}/manifest")
    snapshots = [s for s in manifest["snapshots"] if s["cmId"] == cm_id]
    if not snapshots:
        raise SystemExit(f"No UmaLogs snapshot found for {cm_id}")
    return max(snapshots, key=lambda s: s["meta"].get("window", ""))


def find_snapshot(snapshot_id):
    manifest = fetch_json(f"{API}/manifest")
    for snapshot in manifest["snapshots"]:
        if snapshot["snapshotId"] == snapshot_id:
            return snapshot
    raise SystemExit(f"Snapshot {snapshot_id} not found")


def fetch_teams(snapshot_id, limit):
    """Fetch teams using the Archetypes tab defaults: one per player, ranked by CI lower bound."""
    teams = []
    while len(teams) < limit:
        page = fetch_json(f"{API}/snapshots/{snapshot_id}/teams", {
            "slots": "[{},{},{}]",
            "players": "unique",
            "sort": "lower",
            "limit": min(PAGE_SIZE, limit - len(teams)),
            "offset": len(teams),
        })["teams"]
        if not page:
            break
        teams.extend(page)
    return teams[:limit]


def is_own_unique(skill):
    """True for a runner's own unique: a non-inherited skill that has an inherited version."""
    if skill.is_inherited:
        return False
    try:
        skill.inherited
    except ValueError:
        return False
    return True


def to_skill(skill_id, level):
    skill = Skill(skill_id)  # raises on IDs missing from the catalog
    if not skill.in_bundled_table:
        print(f"warning: {skill.label} #{skill_id} is not in GlobalSim's bundled skill table "
              "and will be ignored by the engine")
    return {"skillId": str(int(skill)), "level": level, "isUnique": is_own_unique(skill)}


def to_runner(member):
    """Convert a hakuraku team member into a GlobalSim horse spec."""
    style = member["racingStyle"]
    if style not in STRATEGIES:
        raise ValueError(f"Unknown racingStyle {style} for member {member.get('id')}")
    speed, stamina, power, guts, wisdom = member["stats"]
    distance, surface, strategy = (Aptitude(a).value for a in member["aptitudes"])
    return {
        "speed": speed,
        "stamina": stamina,
        "power": power,
        "guts": guts,
        "wisdom": wisdom,
        "strategy": STRATEGIES[style].value,
        "distanceAptitude": distance,
        "surfaceAptitude": surface,
        "strategyAptitude": strategy,
        "charaId": int(Uma(member["chara"])),
        "skills": [to_skill(skill_id, level) for skill_id, level in member["skills"]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cm_id", help="Champions Meeting id, e.g. cm21")
    parser.add_argument("--out", type=Path, required=True, help="Output directory")
    parser.add_argument("--limit", type=int, default=100, help="Number of top teams (default 100)")
    parser.add_argument("--snapshot", help="Specific snapshot id (default: latest for the CM)")
    args = parser.parse_args()

    snapshot = find_snapshot(args.snapshot) if args.snapshot else latest_snapshot(args.cm_id)
    teams = fetch_teams(snapshot["snapshotId"], args.limit)
    result = [{"id": team["id"], "members": [to_runner(m) for m in team["members"]]} for team in teams]

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "cm21_teams.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{snapshot['snapshotId']} ({snapshot['meta'].get('course')}): wrote {len(result)} teams to {path}")


if __name__ == "__main__":
    main()
