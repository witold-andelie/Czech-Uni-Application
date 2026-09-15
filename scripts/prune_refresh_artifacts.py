"""Bound storage of this workflow's generated checkpoints/review bundles only."""
import json
import os
import subprocess

repo = os.environ["GITHUB_REPOSITORY"]
raw = subprocess.check_output([
    "gh", "api", f"repos/{repo}/actions/artifacts?per_page=100", "--paginate", "--slurp",
], text=True)
artifacts = [item for page in json.loads(raw) for item in page["artifacts"]]
groups = [
    [item for item in artifacts if item["name"] == "refresh-state"],
]
for group in groups:
    # Keep two complete recovery points; never touch source commits or releases.
    group.sort(key=lambda item: item["created_at"], reverse=True)
    for item in group[2:]:
        subprocess.run(["gh", "api", "--method", "DELETE",
                        f"repos/{repo}/actions/artifacts/{item['id']}"], check=True)
