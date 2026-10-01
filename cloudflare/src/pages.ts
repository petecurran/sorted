// The Worker's own pages: the landing page (with why a session can't start, when it can't) and the wait while a copy
// starts. The app's pages come from the copy itself.

export type Refusal = "closed" | "busy" | "today" | "you";
export type PhotoRefusal = "today" | "session";

type DayCounts = {
	date: string;
	sessions: number;
	visitors: number;
	photos: number;
	refused: Partial<Record<Refusal, number>>;
	photosRefused: Partial<Record<PhotoRefusal, number>>;
};
export type Status = {
	open: boolean;
	running: number;
	caps: { running: number; sessions: number; perVisitor: number; photos: number; photosPerSession: number; minutes: number };
	today: DayCounts;
	yesterday: DayCounts;
};

const REFUSALS: Record<Refusal, string> = {
	closed: "The demo is closed at the moment.",
	busy: "All the demo's copies are in use right now. Try again in a few minutes.",
	today: "The demo has had all its visitors for today. Try again tomorrow.",
	you: "Your internet connection has started as many copies as the demo allows in a day. Try again tomorrow.",
};

const esc = (s: string) =>
	s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c);

function shell(title: string, body: string, script = "", head = ""): string {
	return `<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>${esc(title)}</title>
${head}
<style>
:root { --bg: #f4f4f5; --panel: #fff; --ink: #1d2327; --muted: #5b6670; --line: #dde1e4; --brand: #0b6e6e; --brand-ink: #fff; --note: #fff7e0; --note-line: #f0d48a; }
@media (prefers-color-scheme: dark) { :root { --bg: #14181b; --panel: #1d2327; --ink: #eef1f3; --muted: #a9b3bb; --line: #333c43; --brand: #3fb5b0; --brand-ink: #0c1214; --note: #2d2816; --note-line: #6b5a23; } }
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px 16px; background: var(--bg); color: var(--ink); font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { width: 100%; max-width: 560px; background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 28px 24px; }
h1 { margin: 0 0 4px; font-size: 30px; line-height: 1.15; }
.lede { margin: 0 0 18px; color: var(--muted); }
h2 { margin: 22px 0 6px; font-size: 16px; }
p { margin: 0 0 10px; }
.notice { margin: 0 0 18px; padding: 12px 14px; border-radius: 10px; background: var(--note); border: 1px solid var(--note-line); }
button { display: block; width: 100%; margin: 22px 0 0; padding: 14px 18px; border: 0; border-radius: 12px; background: var(--brand); color: var(--brand-ink); font: inherit; font-weight: 700; cursor: pointer; }
button:focus-visible, a:focus-visible { outline: 3px solid var(--brand); outline-offset: 2px; }
a { color: var(--brand); }
.small { margin-top: 18px; font-size: 13px; color: var(--muted); }
table { width: 100%; margin: 4px 0 14px; border-collapse: collapse; font-size: 15px; }
th, td { padding: 7px 4px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
th { font-weight: 600; }
td.n { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
td.hit { font-weight: 700; }
ul { margin: 0 0 14px; padding-left: 20px; }
.spin { width: 36px; height: 36px; margin: 6px 0 16px; border: 4px solid var(--line); border-top-color: var(--brand); border-radius: 50%; animation: spin 0.9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spin { animation-duration: 3s; } }
</style>
</head>
<body>
<main>
${body}
</main>
${script}
</body>
</html>`;
}

export function landingPage(opts: { minutes: number; refused?: Refusal; notice?: string }): string {
	const notice = opts.refused ? REFUSALS[opts.refused] : opts.notice;
	return shell(
		"Sorted: try the fly-tipping demo",
		`${notice ? `<p class="notice" role="status">${esc(notice)}</p>` : ""}
<h1>Sorted</h1>
<p class="lede">A fly-tipping reporting and triage tool for councils, built in a one-day hackathon at the Labour Conference 2026 by Sagal Qodah, Joe Williams and Pete Curran.</p>
<p>You get your own copy of the demo for ${opts.minutes} minutes: the residents' site, where you report a pile of rubbish, and the council console, where an AI model reads the photo and the council's rules decide what happens next.</p>
<p>Report with one of the sample photos, or a photo of your own. The council, Mersey Vale, is made up, and every other report is simulated.</p>
<h2>Your photos</h2>
<p>A photo you upload is seen only by you. Its location and other hidden data are removed, and it is read by Gemma 4 on Cloudflare Workers AI, which doesn't keep it or train on it. When your session ends, your copy is deleted with everything in it. Please don't upload photos that show people or number plates.</p>
<form method="post" action="/__demo/start"><button type="submit">Start my copy</button></form>
<p class="small">This is a demonstration, not a council service. To report fly-tipping, go to <a href="https://www.gov.uk/report-flytipping">gov.uk/report-flytipping</a>. The code is at <a href="https://github.com/petecurran/sorted">github.com/petecurran/sorted</a>.</p>`,
	);
}

export function waitPage(): string {
	return shell(
		"Setting up your copy",
		`<div class="spin" aria-hidden="true"></div>
<h1>Setting up your copy</h1>
<p class="lede" id="msg" role="status">This takes up to a minute.</p>
<p class="small">This is a demonstration, not a council service.</p>`,
		`<script>
(() => {
  const started = Date.now();
  const msg = document.getElementById("msg");
  async function check() {
    try {
      const r = await fetch("/__demo/ready", { cache: "no-store" });
      if (r.ok) { location.replace("/"); return; }
      if (r.status === 401) { location.replace("/"); return; }
    } catch (e) { /* still starting */ }
    if (Date.now() - started > 120000) {
      msg.innerHTML = 'This is taking longer than usual. <a href="/__demo/wait">Try again</a>.';
      return;
    }
    setTimeout(check, 2000);
  }
  check();
})();
</script>`,
	);
}

const TURNED_AWAY: [Refusal, string][] = [
	["busy", "All copies in use"],
	["today", "Daily session limit"],
	["you", "One connection's daily limit"],
	["closed", "Demo closed"],
];
const PHOTOS_REFUSED: [PhotoRefusal, string][] = [
	["today", "Daily photo limit"],
	["session", "One session's photo limit"],
];

const longDate = (iso: string) =>
	new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });

function dayTable(d: DayCounts, s: Status, now: boolean): string {
	const row = (label: string, used: number, cap: number | null, note = "") =>
		`<tr><th scope="row">${esc(label)}</th><td class="n${cap !== null && used >= cap ? " hit" : ""}">${used}${cap === null ? "" : ` / ${cap}`}</td><td>${esc(note)}</td></tr>`;
	const away = [
		...TURNED_AWAY.map(([k, label]) => [label, d.refused[k] ?? 0] as const),
		...PHOTOS_REFUSED.map(([k, label]) => [`Photo refused: ${label.toLowerCase()}`, d.photosRefused[k] ?? 0] as const),
	].filter(([, n]) => n > 0);
	return `<table>
${row("Sessions started", d.sessions, s.caps.sessions)}
${row("Visitors", d.visitors, null, `counted by internet connection, up to ${s.caps.perVisitor} sessions each`)}
${row("Photos read by the model", d.photos, s.caps.photos, `up to ${s.caps.photosPerSession} a session`)}
${now ? row("Copies running now", s.running, s.caps.running, `${s.caps.minutes} minutes each`) : ""}
</table>
${away.length ? `<p>Turned away:</p><ul>${away.map(([label, n]) => `<li>${esc(label)}: ${n} ${n === 1 ? "time" : "times"}</li>`).join("")}</ul>` : "<p>Nobody was turned away.</p>"}`;
}

/** For whoever runs the demo: today's and yesterday's use against each cap, and who was turned away by which. */
export function statusPage(s: Status): string {
	const t = s.today;
	const hit = [
		t.sessions >= s.caps.sessions && "the daily session limit",
		t.photos >= s.caps.photos && "the daily photo limit",
		(t.refused.busy ?? 0) > 0 && "the limit on copies at once",
	].filter(Boolean) as string[];
	const notice = !s.open
		? "The demo is closed to new visitors (DEMO_OPEN is not \"yes\")."
		: hit.length
			? `Reached today: ${hit.join(", ")}.`
			: "";
	return shell(
		"Sorted demo status",
		`${notice ? `<p class="notice" role="status">${esc(notice)}</p>` : ""}
<h1>Demo status</h1>
<p class="lede">Today, ${esc(longDate(t.date))}. This page refreshes every minute.</p>
${dayTable(t, s, true)}
<h2>Yesterday, ${esc(longDate(s.yesterday.date))}</h2>
${dayTable(s.yesterday, s, false)}
<p class="small">Days run from midnight UTC. To change a limit, edit its setting in cloudflare/wrangler.jsonc and run npm run deploy (docs/HOSTING.md). Add ?json to this address for the same figures as JSON.</p>`,
		"",
		'<meta http-equiv="refresh" content="60">',
	);
}
