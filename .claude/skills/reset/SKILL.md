---
description: Restart the demo on port 8800 with fresh data dated today. Wipes the demo database and uploads.
disable-model-invocation: true
---

1. Say what's about to go: every report, upload and action in `data/app.db` and `data/uploads/`. The council password in `data/council_password.txt` stays.
2. Run `FT_RESET=1 scripts/start_server.sh`. It stops whatever is on port 8800, rebuilds the simulated reports for today (`scripts/build_seed.py`), starts the app in the background and waits for it to answer. The log is `data/server.log`.
3. Run `curl -s http://localhost:8800/api/health` and report the number of incidents and the model's status. On Apple silicon the model shows `loading` and then `ready`: seconds once it's downloaded, but the first start fetches about 7 GB. Elsewhere it's `off`, and the demo photos come from the cache.
4. Give the two addresses: http://localhost:8800 for the public site and http://localhost:8800/council for the console.
