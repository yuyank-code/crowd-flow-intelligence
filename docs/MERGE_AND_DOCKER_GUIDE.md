# Merge and Docker guide

`integrate/stabilisation-security` is built on top of `fix/history-jsx-oct11` (which already contains `fix/sim-core-oct11`),
so it includes both branches' history. Where the branches and the newer work overlapped (`engine.py`, `main.py`,
`App.tsx`, config files) the newer version was kept; CI trigger settings, `PYTHONUNBUFFERED` and `sqlalchemy[asyncio]` from your branches were preserved.

```bash
git push -u origin integrate/stabilisation-security   # then open a pull request into main
./scripts/verify-docker.sh                            # builds and checks the whole Docker stack
```
Windows: run the script from Git Bash or WSL.
