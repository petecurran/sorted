# 4. The laptop is the only caller trusted without a password

Accepted for the demo. Tightened afterwards to close two ways in from other websites.

## Context

At the demo, the audience reported from their own phones through a Cloudflare Quick Tunnel while the presenter ran the council console on the laptop serving the app. The presenter couldn't stop to type a password on stage, and the room had to be kept out of the console completely. There was no time to build staff accounts, and a demo doesn't need them.

## Decision

A request is trusted only if it comes from this machine, is addressed to this machine, and comes from one of the app's own pages. `trust.py` treats a request as remote if any of these fails:

- it comes from another address, or through any proxy (the tunnel adds `cf-connecting-ip`);
- its `Host` isn't a loopback name;
- it carries an `Origin` from another site.

Each check fails closed: a missing or malformed header counts as remote. Remote callers get the public site, and the council console asks them for a password, which is made on first use and kept in `data/council_password.txt`.

The first version checked only the address and the proxy headers, and let any site through with CORS. That left two ways in from a web page open in the presenter's browser. Another site could read and act on the council API directly. So could a site that pointed its own domain at 127.0.0.1 (DNS rebinding). The `Origin` and `Host` checks close both. The CORS middleware has gone too, since the app serves both front ends itself.

## Consequences

- The laptop needs no sign-in, so the stage flow stays quick.
- Anyone at the laptop is the council. That's fine for a demo on the presenter's own machine and wrong anywhere else: real use needs staff sign-in and roles.
- The console's sign-in cookie is `SameSite=Lax`, so a page on another site can't borrow a signed-in session.
- Opening the app at `http://0.0.0.0:8800`, or at the laptop's own network address, counts as remote. Use `localhost` or `127.0.0.1`.
- `tests/test_units.py` checks each way in against `trust.py`. `tests/smoke.py` checks that the running server asks a phone, another site's page and a rebound name to sign in, and still gives them the public site.
