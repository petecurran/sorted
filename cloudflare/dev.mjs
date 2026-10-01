// `npm run dev`: the whole demo on this machine with no Cloudflare account. Workers AI only runs on Cloudflare, so this
// runs wrangler.jsonc without its AI binding, and FAKE_AI=1 (.dev.vars) answers every photo with a fake reading.
// Docker must be running. To try the real model locally, sign in with `npx wrangler login` and run `npx wrangler dev`.
import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, readFileSync, writeFileSync } from "node:fs";

const config = JSON.parse(
	readFileSync("wrangler.jsonc", "utf8")
		.split("\n")
		.filter((line) => !line.trim().startsWith("//"))
		.join("\n"),
);
delete config.ai;
writeFileSync("wrangler.local.jsonc", `// Made by dev.mjs from wrangler.jsonc. Don't edit it.\n${JSON.stringify(config, null, 2)}\n`);
if (!existsSync(".dev.vars")) copyFileSync(".dev.vars.example", ".dev.vars");
const run = spawnSync("npx", ["wrangler", "dev", "-c", "wrangler.local.jsonc", ...process.argv.slice(2)], { stdio: "inherit" });
process.exit(run.status ?? 1);
