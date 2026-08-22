# Project Agents Configuration

## Git Workflow

After every code modification session, the agent MUST:

1. Run `git add -A` to stage all changes
2. Run `git commit` with a concise commit message describing the changes
3. Run `git push` to push to the remote repository (`origin master`)

This applies to ALL code changes — bug fixes, feature additions, refactoring, test updates, etc. Never skip the push step.

Remote: `git@github.com:JC567/FP.git`

## Test Execution

Before committing, run the test suite to verify changes do not break existing functionality:

```powershell
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; python -X utf8 tests/test_p0_pit_pe.py tests/test_p0_pit_revision.py tests/test_p0_pit_attacks.py tests/test_pit_integration.py
```

## Code Style

- Self-contained `if __name__` assertion scripts for tests (not pytest)
- No future functions, no fabricated data, no DATA_INSUFFICIENT disguised as 50
- PIT (Point-in-Time) integrity: `announcement_date <= t` only
