# Prepared data distributions

This directory registers versioned, project-produced GitHub Release
distributions. The descriptor identifies the stable release tag and index URL;
the remote index contains the final asset sizes, SHA-256 values, file counts and
row counts.

Researchers do not follow the URLs manually. Use:

```bash
smc-data distribution
smc-data install
smc-data ready --verify
```

`smc-data install` verifies the index, annual asset archives and every extracted
file before activating the release under `data/installed`.
