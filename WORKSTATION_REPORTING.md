# Workstation result reporting

The reporting wrapper runs an explicitly supplied command at an exact Git
commit, keeps complete logs under the ignored `runs/` directory, and publishes
only a compact JSON report to the `workstation-results` branch. The repository
is public: never add raw logs, checkpoints, credentials, environment dumps, or
machine-specific files to that branch.

## One-time reporting checkout

After the reporting branch exists:

```bash
git clone --single-branch --branch workstation-results \
  https://github.com/csned-inl/clarity-standalone.git \
  "$HOME/src/clarity-standalone-results"
```

The checkout must have `git config user.name` and `git config user.email` set.
The wrapper never force-pushes and never changes the source checkout's branch.

## Run a job

From the source checkout, with the virtual environment active:

```bash
python scripts/workstation_job.py \
  --job-id example-20260927-01 \
  --expected-sha 0000000000000000000000000000000000000000 \
  --result-root runs/example-20260927-01 \
  --reports-checkout "$HOME/src/clarity-standalone-results" \
  -- \
  python pipeline.py --model thermostat --mode analytic \
    --output runs/example-20260927-01
```

Replace the job ID and expected SHA with the exact values supplied for the
run. The wrapper refuses a SHA mismatch or dirty tracked source. It records
success, failure, or interruption and attempts publication in all three cases.

If publication fails after execution, the complete report remains local. Retry
without rerunning the computation:

```bash
python scripts/publish_workstation_result.py \
  --report runs/workstation-jobs/JOB_ID/report.json \
  --reports-checkout "$HOME/src/clarity-standalone-results"
```

Use `--no-publish` for a local-only wrapper test.
