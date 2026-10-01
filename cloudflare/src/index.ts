// The hosted demo's Worker. A visitor starts a session from the landing page and gets their own copy of Sorted (a
// container) until it ends. The Gate holds the sessions and the daily counts, and each SortedApp is one visitor's copy.
// The caps live in wrangler.jsonc. docs/HOSTING.md explains it, and docs/decisions/0006-hosted-copy.md says why.
import { Container, ContainerProxy, getContainer, type OutboundHandlerContext } from "@cloudflare/containers";
import { DurableObject } from "cloudflare:workers";
import { BAR_JS } from "./bar";
import { landingPage, type PhotoRefusal, type Refusal, type Status, statusPage, waitPage } from "./pages";

export { ContainerProxy };

const MODEL = "@cf/google/gemma-4-26b-a4b-it";
const OSRM = "https://router.project-osrm.org";
const COOKIE = "sorted_demo";
const SID = /^[0-9a-f]{32}$/;

const num = (v: string | undefined, fallback: number) => {
	const n = Number(v);
	return Number.isFinite(n) && n >= 0 ? n : fallback;
};
const hex = (bytes: ArrayBuffer | Uint8Array) =>
	[...new Uint8Array(bytes)].map((b) => b.toString(16).padStart(2, "0")).join("");
const json = (body: unknown, status = 200, headers: HeadersInit = {}) =>
	Response.json(body, { status, headers: { "Cache-Control": "no-store", ...headers } });
const html = (body: string, status = 200, headers: HeadersInit = {}) =>
	new Response(body, {
		status,
		headers: {
			"Content-Type": "text/html; charset=utf-8",
			"Cache-Control": "no-store",
			"X-Robots-Tag": "noindex",
			...headers,
		},
	});
const redirect = (to: string, cookie?: string) =>
	new Response(null, { status: 303, headers: { Location: to, "Cache-Control": "no-store", ...(cookie ? { "Set-Cookie": cookie } : {}) } });
// The cookie outlives its session by an hour, so a visitor who comes back is told it has ended.
const sessionCookie = (sid: string, expires: number) =>
	`${COOKIE}=${sid}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${Math.max(0, Math.floor((expires - Date.now()) / 1000)) + 3600}`;
const ENDED = "Your session has ended, and your copy of the demo has been deleted with any photos in it.";
const clearCookie = `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
const today = (at = Date.now()) => new Date(at).toISOString().slice(0, 10);

function cookie(request: Request, name: string): string | null {
	for (const part of (request.headers.get("cookie") ?? "").split(";")) {
		const [k, ...v] = part.trim().split("=");
		if (k === name) return v.join("=");
	}
	return null;
}

// ---- the Gate: sessions and caps ------------------------------------------------------------------------------------

type Day = {
	sessions: number;
	photos: number;
	salt: string;
	visitors: Record<string, number>;
	copies: Record<string, number>;
	// How often each cap turned someone away, for the status page.
	refused?: Partial<Record<Refusal, number>>;
	photosRefused?: Partial<Record<PhotoRefusal, number>>;
};
type Secrets = { STATUS_KEY?: string; FAKE_AI?: string };

/** One for the whole demo, so every count is exact. It keeps no addresses: a visitor is a hash salted afresh each day. */
export class Gate extends DurableObject<Env> {
	private async day(): Promise<[string, Day]> {
		const key = `d:${today()}`;
		let d = await this.ctx.storage.get<Day>(key);
		if (!d) {
			d = { sessions: 0, photos: 0, salt: crypto.randomUUID(), visitors: {}, copies: {} };
			await this.ctx.storage.put(key, d);
		}
		return [key, d];
	}

	/** A new session, or why not. Every refusal is counted for the status page. */
	async start(address: string): Promise<{ sid: string; expires: number } | { refused: Refusal }> {
		const { salt } = (await this.day())[1];
		const visitor = hex(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(salt + address)));
		// Only storage calls from here on, so no other request can change the counts in between.
		const now = Date.now();
		const [key, d] = await this.day();
		const sessions = await this.ctx.storage.list<number>({ prefix: "s:" });
		const running = [...sessions.values()].filter((e) => e > now).length;
		const refused: Refusal | null =
			this.env.DEMO_OPEN !== "yes"
				? "closed"
				: running >= num(this.env.MAX_ACTIVE_SESSIONS, 20)
					? "busy"
					: d.sessions >= num(this.env.MAX_SESSIONS_PER_DAY, 100)
						? "today"
						: (d.visitors[visitor] ?? 0) >= num(this.env.MAX_SESSIONS_PER_VISITOR_PER_DAY, 20)
							? "you"
							: null;
		if (refused) {
			d.refused = { ...d.refused, [refused]: (d.refused?.[refused] ?? 0) + 1 };
			await this.ctx.storage.put(key, d);
			return { refused };
		}
		d.sessions += 1;
		d.visitors[visitor] = (d.visitors[visitor] ?? 0) + 1;
		const sid = hex(crypto.getRandomValues(new Uint8Array(16)));
		const expires = now + num(this.env.SESSION_MINUTES, 30) * 60_000;
		await this.ctx.storage.put({ [key]: d, [`s:${sid}`]: expires });
		await this.scheduleSweep();
		return { sid, expires };
	}

	/** When the session ends, or null if it has. */
	async session(sid: string): Promise<number | null> {
		if (!SID.test(sid)) return null;
		const expires = await this.ctx.storage.get<number>(`s:${sid}`);
		return expires && expires > Date.now() ? expires : null;
	}

	/** End a session now. The sweep stops its copy. */
	async end(sid: string): Promise<void> {
		if (!SID.test(sid) || !(await this.ctx.storage.get(`s:${sid}`))) return;
		await this.ctx.storage.put(`s:${sid}`, 0);
		await this.ctx.storage.setAlarm(Date.now() + 500);
	}

	/** Count one photo for the model if today's cap and this copy's cap allow it, or say which cap stopped it. */
	async spendPhoto(copy: string): Promise<PhotoRefusal | null> {
		const [key, d] = await this.day();
		const refused: PhotoRefusal | null =
			d.photos >= num(this.env.MAX_PHOTOS_PER_DAY, 300)
				? "today"
				: (d.copies[copy] ?? 0) >= num(this.env.MAX_PHOTOS_PER_SESSION, 8)
					? "session"
					: null;
		if (refused) d.photosRefused = { ...d.photosRefused, [refused]: (d.photosRefused?.[refused] ?? 0) + 1 };
		else {
			d.photos += 1;
			d.copies[copy] = (d.copies[copy] ?? 0) + 1;
		}
		await this.ctx.storage.put(key, d);
		return refused;
	}

	/** Today's and yesterday's counts against the caps, for the status page. It changes nothing. */
	async status(): Promise<Status> {
		const now = Date.now();
		const read = async (at: number) => {
			const d = await this.ctx.storage.get<Day>(`d:${today(at)}`);
			return {
				date: today(at),
				sessions: d?.sessions ?? 0,
				visitors: Object.keys(d?.visitors ?? {}).length,
				photos: d?.photos ?? 0,
				refused: d?.refused ?? {},
				photosRefused: d?.photosRefused ?? {},
			};
		};
		const sessions = await this.ctx.storage.list<number>({ prefix: "s:" });
		const e = this.env;
		return {
			open: e.DEMO_OPEN === "yes",
			running: [...sessions.values()].filter((x) => x > now).length,
			caps: {
				running: num(e.MAX_ACTIVE_SESSIONS, 20),
				sessions: num(e.MAX_SESSIONS_PER_DAY, 100),
				perVisitor: num(e.MAX_SESSIONS_PER_VISITOR_PER_DAY, 20),
				photos: num(e.MAX_PHOTOS_PER_DAY, 300),
				photosPerSession: num(e.MAX_PHOTOS_PER_SESSION, 8),
				minutes: num(e.SESSION_MINUTES, 30),
			},
			today: await read(now),
			yesterday: await read(now - 86_400_000),
		};
	}

	private async scheduleSweep(): Promise<void> {
		const sessions = await this.ctx.storage.list<number>({ prefix: "s:" });
		if (!sessions.size) return;
		const next = Math.max(Math.min(...sessions.values()), Date.now() + 500);
		const current = await this.ctx.storage.getAlarm();
		if (current === null || next < current) await this.ctx.storage.setAlarm(next);
	}

	/** At the end of each session, stop its copy (which wipes its disk, photos and all) and forget the session. */
	async alarm(): Promise<void> {
		const now = Date.now();
		for (const [key, expires] of await this.ctx.storage.list<number>({ prefix: "s:" })) {
			if (expires > now) continue;
			try {
				await getContainer(this.env.APP, key.slice(2)).destroy();
			} catch {
				// it had already stopped
			}
			await this.ctx.storage.delete(key);
		}
		const keep = new Set([`d:${today(now)}`, `d:${today(now - 86_400_000)}`]);
		for (const key of (await this.ctx.storage.list({ prefix: "d:" })).keys()) {
			if (!keep.has(key)) await this.ctx.storage.delete(key);
		}
		await this.scheduleSweep();
	}
}

const gateOf = (env: Env) => env.GATE.get(env.GATE.idFromName("gate"));
const landing = (env: Env, opts: { refused?: Refusal; notice?: string } = {}) =>
	landingPage({ ...opts, minutes: num(env.SESSION_MINUTES, 30) });

// ---- one visitor's copy ---------------------------------------------------------------------------------------------

export class SortedApp extends Container<Env> {
	defaultPort = 8800;
	sleepAfter = "15m";
	// No internet: the copy reaches only ai.sorted and osrm.sorted, which the handlers below answer.
	enableInternet = false;

	// Hosted mode (decision 6), the model behind ai.sorted, and a short pause before a cached reading lands, so the demo
	// kit still shows "Checking…". The Gate, not the copy, limits its photos, so the status page counts every refusal.
	envVars = {
		FT_HOSTED: "1",
		FT_CLASSIFIER: "workers-ai",
		FT_AI_URL: "http://ai.sorted/run",
		FT_OSRM_URL: "http://osrm.sorted",
		FT_CACHE_DELAY: "3",
	};
}

/** A copy's photo, read by Gemma 4 on Workers AI. The Worker picks the model and its settings, and counts the photo
 * against the caps first, so a copy can't spend more than its share. */
async function readPhoto(request: Request, env: Env, ctx: OutboundHandlerContext): Promise<Response> {
	if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);
	if (Number(request.headers.get("content-length") ?? 0) > 8_000_000) return json({ error: "too_large" }, 413);
	const body = (await request.json().catch(() => null)) as { messages?: unknown } | null;
	const messages = body?.messages;
	if (!Array.isArray(messages) || messages.length !== 1) return json({ error: "bad_request" }, 400);
	const refused = await gateOf(env).spendPhoto(ctx.containerId);
	if (refused) {
		console.log(`refused: photos_${refused}`);
		return json({ error: "photo_limit", cap: refused }, 429);
	}
	if ((env as Secrets).FAKE_AI === "1") return json(FAKE_REPLY);
	try {
		const ai = env.AI as unknown as { run(model: string, inputs: unknown): Promise<unknown> };
		const out = await ai.run(MODEL, {
			messages,
			max_completion_tokens: 400,
			temperature: 0,
			chat_template_kwargs: { enable_thinking: false },
		});
		return json(out);
	} catch (e) {
		console.error("Workers AI failed:", e instanceof Error ? e.message : e);
		return json({ error: "model_error" }, 502);
	}
}

/** The Routes tab's road distances, from the public OSRM demo server (light use only). */
async function route(request: Request): Promise<Response> {
	const url = new URL(request.url);
	if (request.method !== "GET" || !/^\/(route|trip)\/v1\/driving\/[-\d.,;]+$/.test(url.pathname)) {
		return json({ error: "not_allowed" }, 403);
	}
	return fetch(OSRM + url.pathname + url.search, {
		headers: { "User-Agent": "sorted-demo (https://github.com/petecurran/sorted)" },
	});
}

SortedApp.outboundByHost = {
	"ai.sorted": (request, env, ctx) => readPhoto(request, env as Env, ctx),
	"osrm.sorted": (request) => route(request),
};

// For `npm run dev` without a Cloudflare account: FAKE_AI=1 in .dev.vars answers every photo with this.
const FAKE_REPLY = {
	choices: [
		{
			message: {
				role: "assistant",
				content:
					'{"what_you_see": "A test reading from the local fake model.", "items": "3 black bags", "fly_tip": "yes", "confidence": 80, "size": "Car boot or less", "waste_type": "Black bags - household", "land_type": "Highway", "hazards": "none"}',
			},
		},
	],
};

// ---- the Worker -----------------------------------------------------------------------------------------------------

/** The status page, for whoever runs the demo: today's counts against the caps. It's off until STATUS_KEY is set (a
 * secret), then the browser asks for it as a password, so the key never appears in a URL or a log. */
async function statusResponse(request: Request, env: Env, gate: DurableObjectStub<Gate>): Promise<Response> {
	const key = (env as Secrets).STATUS_KEY;
	if (!key) return new Response("Not found", { status: 404 });
	const given = (() => {
		const auth = request.headers.get("authorization") ?? "";
		try {
			return auth.startsWith("Basic ") ? atob(auth.slice(6)).split(":").slice(1).join(":") : "";
		} catch {
			return "";
		}
	})();
	const a = new TextEncoder().encode(given);
	const b = new TextEncoder().encode(key);
	if (a.byteLength !== b.byteLength || !crypto.subtle.timingSafeEqual(a, b)) {
		return new Response("Enter the status key as the password (any user name).", {
			status: 401,
			headers: { "WWW-Authenticate": 'Basic realm="Sorted demo status", charset="UTF-8"', "Cache-Control": "no-store" },
		});
	}
	const status = await gate.status();
	return new URL(request.url).searchParams.has("json") ? json(status) : html(statusPage(status));
}

/** Send a request to the visitor's copy. The containers library answers its own failures (a dropped connection, a copy
 * still starting) with a plain-text 5xx, which the app never sends. A safe request gets one retry; null means the copy
 * isn't answering yet. */
async function forward(app: DurableObjectStub<SortedApp>, request: Request): Promise<Response | null> {
	const safe = request.method === "GET" || request.method === "HEAD";
	for (let attempt = 0; attempt < (safe ? 2 : 1); attempt++) {
		if (attempt) await new Promise((r) => setTimeout(r, 400));
		try {
			const r = await app.fetch(safe ? new Request(request) : request);
			if (r.status < 500 || !(r.headers.get("content-type") ?? "").startsWith("text/plain")) return r;
			console.error("copy unavailable:", r.status, (await r.text()).slice(0, 200));
		} catch (e) {
			console.error("copy unavailable:", e instanceof Error ? e.message : e);
		}
	}
	return null;
}

export default {
	async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
		const url = new URL(request.url);
		const path = url.pathname;
		const gate = gateOf(env);
		const wantsPage = request.method === "GET" && (request.headers.get("accept") ?? "").includes("text/html");

		if (path === "/robots.txt") return new Response("User-agent: *\nDisallow: /\n", { headers: { "Content-Type": "text/plain" } });

		if (path === "/__demo/start") {
			if (request.method !== "POST") return redirect("/");
			if (request.headers.get("origin") !== url.origin) return html(landing(env), 403);
			const started = await gate.start(request.headers.get("cf-connecting-ip") ?? "unknown");
			if ("refused" in started) {
				console.log(`refused: ${started.refused}`);
				return html(landing(env, { refused: started.refused }), 429);
			}
			return redirect("/__demo/wait", sessionCookie(started.sid, started.expires));
		}

		if (path === "/__demo/ended") return html(landing(env, { notice: ENDED }));
		if (path === "/__demo/status") return statusResponse(request, env, gate);

		if (path.startsWith("/__demo/join/")) {
			// The phone link: the session id is its key, so a phone can join the copy it was shown.
			const sid = path.slice("/__demo/join/".length);
			const expires = await gate.session(sid);
			return expires ? redirect("/", sessionCookie(sid, expires)) : html(landing(env, { notice: "That link has expired." }), 410);
		}

		const sid = cookie(request, COOKIE);
		const expires = sid ? await gate.session(sid) : null;
		if (!sid || !expires) {
			const notice = sid ? ENDED : undefined;
			if (wantsPage) return html(landing(env, { notice }), 200, sid ? { "Set-Cookie": clearCookie } : {});
			return json({ error: "no_session" }, 401);
		}

		const app = getContainer(env.APP, sid);
		switch (path) {
			case "/__demo/wait":
				return html(waitPage());
			case "/__demo/ready":
				try {
					const r = await app.fetch(new Request("http://app/api/health"));
					return json({ ready: r.ok }, r.ok ? 200 : 503);
				} catch {
					return json({ ready: false }, 503);
				}
			case "/__demo/session":
				return json({ expires, join: `${url.origin}/__demo/join/${sid}` });
			case "/__demo/bar.js":
				return new Response(BAR_JS, { headers: { "Content-Type": "text/javascript; charset=utf-8", "Cache-Control": "no-cache" } });
			case "/__demo/end":
				if (request.method !== "POST" || request.headers.get("origin") !== url.origin) return redirect("/");
				await gate.end(sid);
				return redirect("/__demo/ended", clearCookie);
		}

		let response = await forward(app, request);
		if (!response) {
			if (wantsPage) return html(waitPage(), 503);
			return json({ error: "starting" }, 503);
		}
		response = new Response(response.body, response);
		response.headers.set("X-Robots-Tag", "noindex");
		if (!(response.headers.get("content-type") ?? "").startsWith("text/html")) return response;
		return new HTMLRewriter()
			.on("body", {
				element(body) {
					body.append('<script src="/__demo/bar.js" defer></script>', { html: true });
				},
			})
			.transform(response);
	},
} satisfies ExportedHandler<Env>;
