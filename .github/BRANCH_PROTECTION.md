# Branch Protection — `main`

These settings are applied in the GitHub UI (**Settings → Branches → Branch
protection rules → Add rule**, branch name pattern `main`). They are documented
here, not automated — GitHub does not read this file.

## Recommended rule for `main`

- **Require a pull request before merging**
  - Required approvals: **1** (set to **0** if you're a solo developer)
  - Dismiss stale approvals when new commits are pushed
- **Require status checks to pass before merging**
  - Required checks: **`backend-ci`** and **`frontend-ci`**
  - **Require branches to be up to date before merging** (re-run CI on the
    latest `main` before allowing merge)
- **Do not allow force pushes**
- **Do not allow deletions**

## Why these checks

`backend-ci` and `frontend-ci` are the two job names in
`.github/workflows/ci.yml`. The `deploy` job is intentionally **not** a required
check — it only runs on push to `main` (after a merge), not on the PR, so it
can't be a merge gate. CI gates the merge; deploy runs once the code is on
`main`.

## Optional: protect the deploy

The deploy job declares `environment: production`. Under **Settings →
Environments → production** you can add **required reviewers** so each
production deployment must be manually approved, and/or a **wait timer**. This
gives a human gate on releases without blocking CI.
