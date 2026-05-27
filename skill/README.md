# WikiMaker Skill Source

This project folder is the canonical workspace mirror for the WikiMaker skill source and related files.

The current runtime is the repo pipeline at `/Users/enkay/dev/wikimaker/wikimaker.py`, run through the dedicated `wikimaker` conda environment. The repo-local skill launcher `wikimaker_alpha_v0001.py` is a compatibility wrapper around that pipeline.

Useful checks:

```bash
conda run -n wikimaker python /Users/enkay/dev/wikimaker/wikimaker.py --help
/Users/enkay/dev/wikimaker/wikimakerctl.sh status
```

If this skill is copied into a Hermes/Harmis skill directory, copy the whole `skill/` folder after updating `SKILL.md` here.
