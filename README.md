# OSS Community Health

Simple utility to track your open source community health. Run from CLI:

```
python3 oss-health-check.py fanahova/nba_rb fanahova
```

Or import in your Python code:

```
from oss_health_check import DockerStats, GithubHealth, PypiStats

gh = GithubHealth('fanahova/smol-podcaster', ['fanahova'])

gh.time_to_first_response_for_issues()
```

# Batch runs

Fill out the `bulk-data.json` file to run this in batch on multiple projects at once.