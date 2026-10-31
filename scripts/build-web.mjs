import { mkdir } from "node:fs/promises";
import { build, file, write } from "bun";

async function compile(entrypoint) {
  const result = await build({
    entrypoints: [entrypoint],
    target: "browser",
    format: "iife",
    minify: true,
    define: { "process.env.NODE_ENV": '"production"' },
  });
  if (!result.success) throw new Error(result.logs.map(String).join("\n"));
  if (result.outputs.length !== 1) {
    throw new Error(`${entrypoint} must produce one self-contained asset`);
  }
  return result.outputs[0].text();
}

const [script, style] = await Promise.all([compile("web/page.ts"), compile("web/page.css")]);
const banner = '/* Generated from web/page.ts. Run bun run build to update. */ "use strict";\n';
await mkdir("transcripts/assets", { recursive: true });
// React contains a script-closing string. Escape it before HTML inlining while
// preserving the JavaScript string value and the renderer's asset parity.
await Promise.all([
  write("transcripts/assets/page.js", banner + script.replace(/<\/script/gi, "<\\/script")),
  write("transcripts/assets/page.css", style),
  write("transcripts/assets/page.html", file("web/page.html")),
]);
