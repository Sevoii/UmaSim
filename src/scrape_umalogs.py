"""Scrape the top teams for a Champions Meeting from hakuraku.moe UmaLogs.

Writes ``data/<cm_id>_teams.json`` by default as ``[{"id": str, "members": [<GlobalSim horse>, ...]}]``.

Usage:
    python src/scrape_umalogs.py 21 [--out data/teams.json] [--limit 100] [--offset 0] [--snapshot ID]
"""
import argparse
import json
import re
from pathlib import Path

import requests
from globalsim import Aptitude, Skill, Strategy, Uma

API = "https://hakuraku.moe/api/simdata"
PAGE_SIZE = 100
# Global release order. Keep this list in sync as new meetings are added.
CM_NAMES = (
    "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio",
    "sagittarius", "capricorn", "aquarius", "pisces", "aries",
    "taurus 2", "gemini 2", "cancer 2", "leo 2", "virgo 2", "libra 2",
    "scorpio 2", "sagittarius 2", "capricorn 2", "aquarius 2",
)
# hakuraku racingStyle -> GlobalSim strategy (style 6 "Debuffer" is a label; racingStyle is the real style).
STRATEGIES = {1: Strategy.FRONT_RUNNER, 2: Strategy.PACE_CHASER, 3: Strategy.LATE_SURGER,
              4: Strategy.END_CLOSER, 5: Strategy.RUNAWAY}

session = requests.Session()
session.headers["User-Agent"] = "UmaSim-scraper"


def fetch_json(url, params=None):
    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def normalize_cm(value):
    """Accept a number, cm ID, or cup name and return an UmaLogs ID."""
    value = value.strip().lower()
    if re.fullmatch(r"(?:cm)?\d+(?:-[a-z0-9]+)?", value):
        return value if value.startswith("cm") else "cm" + value
    name = re.sub(r"[_-]+", " ", value)
    name = re.sub(r"\bcup\b", "", name)
    name = " ".join(name.split())
    try:
        return f"cm{CM_NAMES.index(name) + 1}"
    except ValueError:
        raise ValueError(f"Unknown meeting {value!r}; use a number, cm ID, or cup name") from None


def latest_snapshot(cm_id):
    manifest = fetch_json(f"{API}/manifest")
    snapshots = [s for s in manifest["snapshots"] if s["cmId"] == cm_id]
    if not snapshots and re.fullmatch(r"cm\d+", cm_id):
        variants = {s["cmId"] for s in manifest["snapshots"] if s["cmId"].startswith(cm_id + "-")}
        if len(variants) > 1:
            raise SystemExit(f"Multiple variants for {cm_id}: {', '.join(sorted(variants))}; specify one")
        if variants:
            snapshots = [s for s in manifest["snapshots"] if s["cmId"] in variants]
    if not snapshots:
        raise SystemExit(f"No UmaLogs snapshot found for {cm_id}")
    return max(snapshots, key=lambda s: s["meta"].get("window", ""))


def find_snapshot(snapshot_id):
    manifest = fetch_json(f"{API}/manifest")
    for snapshot in manifest["snapshots"]:
        if snapshot["snapshotId"] == snapshot_id:
            return snapshot
    raise SystemExit(f"Snapshot {snapshot_id} not found")


def fetch_teams(snapshot_id, limit, offset=0):
    """Fetch teams using the Archetypes tab defaults: one per player, ranked by CI lower bound."""
    teams = []
    while len(teams) < limit:
        page = fetch_json(f"{API}/snapshots/{snapshot_id}/teams", {
            "slots": "[{},{},{}]",
            "players": "unique",
            "sort": "lower",
            "limit": min(PAGE_SIZE, limit - len(teams)),
            "offset": offset + len(teams),
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
    parser.add_argument("cm_id", help="Meeting number, ID, or name, e.g. 21, cm21, or 'Capricorn Cup 2'")
    parser.add_argument("--out", type=Path,
                        help="Output JSON file (default: repository data/<cm_id>_teams.json)")
    parser.add_argument("--limit", type=int, default=100, help="Number of top teams (default 100)")
    parser.add_argument("--offset", type=int, default=0, help="Number of ranked teams to skip (default 0)")
    parser.add_argument("--snapshot", help="Specific snapshot id (default: latest for the CM)")
    args = parser.parse_args()

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.offset < 0:
        parser.error("--offset must be non-negative")
    try:
        cm_id = normalize_cm(args.cm_id)
    except ValueError as exc:
        parser.error(str(exc))
    snapshot = find_snapshot(args.snapshot) if args.snapshot else latest_snapshot(cm_id)
    if snapshot["cmId"] != cm_id and not (re.fullmatch(r"cm\d+", cm_id) and
                                             snapshot["cmId"].startswith(cm_id + "-")):
        parser.error(f"snapshot {args.snapshot} belongs to {snapshot['cmId']}, not {cm_id}")
    teams = fetch_teams(snapshot["snapshotId"], args.limit, args.offset)
    result = [{"id": team["id"], "members": [to_runner(m) for m in team["members"]]} for team in teams]

    path = args.out if args.out is not None else (Path(__file__).resolve().parent.parent /
                                                  "data" / f"{snapshot['cmId']}_teams.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{snapshot['snapshotId']} ({snapshot['meta'].get('course')}): wrote {len(result)} teams to {path}")


if __name__ == "__main__":
    main()
