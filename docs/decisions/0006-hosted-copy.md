# 6. A hosted copy belongs to one visitor

Accepted for the hosted demo.

## Context

After the hackathon, the team wanted a link that anyone could open to try Sorted. The demo was built for one laptop. It trusts only that laptop ([decision 4](0004-laptop-trust-rule.md)), its model needs Apple silicon ([decision 1](0001-local-model.md)), and everyone shares one set of demo data. Sharing one public copy would show each visitor's uploads to everyone else, let anyone into the council console, and leave the cost open-ended. The link is for one person at a time to try the demo, not for a community to report into.

## Decision

Each visitor gets their own copy. A Cloudflare Worker (`cloudflare/`) gives each new session a random id and a container running the app, for 30 minutes and within daily caps. One Durable Object, the Gate, keeps the sessions and the counts, and stops each copy when its session ends. The cookie holding the session id is the only way into a copy.

Inside a copy, the visitor is the council. With `FT_HOSTED=1`, `server.py` trusts every caller, because a container has no address of its own. Every request has come through the Worker, which sends each visitor only to their own copy. Hosted mode also needs `CLOUDFLARE_DURABLE_OBJECT_ID`, which Cloudflare sets in every container. Setting `FT_HOSTED` on a laptop therefore changes nothing, and the laptop rule still applies there.

The model is Gemma 4 26B on Cloudflare Workers AI. The container has no internet: its only route to the model is a name that the Worker answers, after counting the photo against the caps. The Worker picks the model and its settings.

## Consequences

- No visitor sees another's reports or photos, and nobody needs a password in their own copy.
- Photos now leave the machine that holds them, so decision 1's "nothing leaves the machine" doesn't hold for the hosted copy. Workers AI doesn't keep photos or train on them, and the landing page says so. The demo kit's readings are cached, so those photos never leave the copy.
- The hosted model isn't the one the prompt was tuned and measured on. `docs/HOSTING.md` says how to measure it, through the same call the app makes.
- The caps bound the cost: about $25 a month at worst with the defaults (100 sessions a day), and $5 when nobody visits. Cloudflare offers budget alerts but no hard limit, so the caps in the Worker are what hold.
- Each copy starts from fresh demo data, which takes about ten seconds the first time.
- CLAUDE.md's rule 3 now has this one exception. The unit tests check that `FT_HOSTED` on its own does nothing, and the smoke test runs with `FT_HOSTED=1` set, so every trust check there covers it too.
