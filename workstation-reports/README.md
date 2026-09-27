# CLARITY workstation report channel

This branch is an append-only transport for sanitized CLARITY workstation result reports.

- Do not merge this branch.
- Do not place raw logs, model checkpoints, credentials, environment dumps, hostnames, usernames, or absolute workstation paths here.
- Complete artifacts remain in the workstation's ignored `runs/` directory.
- Each run writes an immutable JSON file under `workstation-reports/results/` and updates `workstation-reports/latest.json`.
- Result commits are produced only after a user explicitly starts a commit-pinned workstation command.
