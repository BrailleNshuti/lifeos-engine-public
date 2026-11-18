# Release checklist

Run top to bottom. Do not skip a step; tick it with a date.

## Before tagging
- [ ] `git status` clean, on `main`, up to date with origin.
- [ ] `pytest -q` passes; `lifeos guard $(git ls-files)` passes.
- [ ] Version equal in `pyproject.toml` and `lifeos/__init__.py`; top `CHANGELOG.md` entry matches.
- [ ] README commands table and roadmap match the code.
- [ ] No personal data: `git log --format='%an <%ae>' | sort -u` shows only the noreply address.

## First public release only
- [ ] Rewritten history verified (one author, no forbidden terms, tip tree unchanged).
- [ ] Pushed to a NEW repository; the old repository stays private.
- [ ] Settings: private vulnerability reporting on; Dependabot alerts on; secret scanning on.
- [ ] Repository is made public only after the steps above.

## Tag
- [ ] `git tag -a v0.4.0 -m "v0.4.0"` and push the tag.
- [ ] Create the GitHub release from the tag; paste the CHANGELOG entry.
