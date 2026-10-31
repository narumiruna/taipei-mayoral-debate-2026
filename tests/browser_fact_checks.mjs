import assert from "node:assert/strict";
import { mkdir, readdir, readFile } from "node:fs/promises";
import { createServer } from "node:http";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const siteURL = new URL("../site/", import.meta.url);
const pageURL = new URL("index.html", siteURL);
const ledger = JSON.parse(
  await readFile(new URL("../data/fact-checks.json", import.meta.url), "utf8"),
);
const publishedFiles = new Map(
  await Promise.all(
    (await readdir(siteURL)).map(async (name) => [name, await readFile(new URL(name, siteURL))]),
  ),
);
const basePath = "/taipei-mayoral-debate-2026/";
const screenshotDir = new URL("../outputs/fact-checks/", import.meta.url);

// Headless checks do not need WSLg launch arguments.
await test("fact checks work with external network requests blocked", async (t) => {
  const server = createServer((request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    const name = pathname.startsWith(basePath)
      ? pathname.slice(basePath.length) || "index.html"
      : "";
    const content = publishedFiles.get(name);
    if (!content) {
      response.writeHead(404);
      response.end();
      return;
    }
    const type = name.endsWith(".html")
      ? "text/html"
      : name.endsWith(".json")
        ? "application/json"
        : "text/plain";
    response.writeHead(200, { "Content-Type": `${type}; charset=utf-8` });
    response.end(content);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  const origin = `http://127.0.0.1:${address.port}`;
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.route("**/*", (route) => {
      const url = route.request().url();
      return url.startsWith(origin) || url.startsWith("file:") ? route.continue() : route.abort();
    });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.goto(`${origin}${basePath}`, { waitUntil: "domcontentloaded" });
    await page.locator(".turn").first().waitFor();
    const cards = page.locator(".fact-check-card");
    const reset = () => page.locator("#reset-filters").click();
    const openChecks = () => page.locator("#tab-fact-checks").click();

    await t.test("published downloads work under the GitHub Pages project path", async () => {
      const links = await page
        .locator("a[download]")
        .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href")));
      assert.equal(links.length, 5);
      for (const name of links) {
        const response = await page.request.get(new URL(name, page.url()).href);
        assert.equal(response.status(), 200, name);
        const source = await readFile(new URL(`../data/${name}`, import.meta.url));
        assert.deepEqual(await response.body(), source, name);
      }
      const unpublished = await page.request.get(`${origin}/data/transcript.json`);
      assert.equal(unpublished.status(), 404);
    });

    await t.test("tab, coverage, evidence, and original quotes", async () => {
      await openChecks();
      assert.equal(await cards.count(), ledger.items.length);
      assert.equal(await page.locator("#tab-fact-checks").getAttribute("aria-selected"), "true");
      assert.equal(await page.locator("#panel-transcript").isVisible(), false);
      assert.equal(await page.locator(".candidate-coverage").count(), 2);
      for (const item of ledger.items) {
        const card = page.locator(`#check-${item.id}`);
        assert.equal(
          await card.locator(".verdict").textContent(),
          {
            supported: "有資料支持",
            "needs-context": "需補充脈絡",
            contradicted: "與資料不符",
            "insufficient-evidence": "證據不足",
          }[item.verdict],
        );
        const expected = item.quotes
          .map((part, index) => {
            const previous = item.quotes[index - 1];
            return `${previous && part.cue_id !== previous.cue_id + 1 ? " […] " : ""}${part.text}`;
          })
          .join("");
        assert.equal(await card.locator("blockquote").textContent(), expected);
        await card.locator(".fact-check-evidence summary").click();
        const links = card.locator(".fact-check-sources a");
        assert.equal(await links.count(), item.sources.length);
        for (const [index, source] of item.sources.entries()) {
          assert.equal(await links.nth(index).getAttribute("href"), source.url);
          assert.equal(await links.nth(index).getAttribute("rel"), "noopener noreferrer");
        }
        await card.locator(".fact-check-evidence summary").click();
      }
      assert.match(await page.locator("#check-FC009 .pending-label").textContent(), /待確認字幕/);
      assert.match(await page.locator("#check-FC005 .pending-label").textContent(), /待確認字幕/);
    });

    await t.test("speaker corrections remain visible alongside fact checks", async () => {
      const transcript = JSON.parse(publishedFiles.get("transcript.json").toString("utf8"));
      const speakerCorrections = transcript.review.speaker_corrections;
      assert(speakerCorrections.length > 0);
      await page.locator("#tab-corrections").click();
      for (const correction of speakerCorrections) {
        const cue = transcript.cues.find((entry) => entry.id === correction.cue_id);
        assert(cue);
        const card = page.locator(".review-card").filter({
          has: page.getByText(`修訂 ${correction.id}`, { exact: true }),
        });
        assert.equal(await card.count(), 1);
        assert.deepEqual(await card.locator(".comparison dt").allTextContents(), [
          "原說話者",
          "修訂說話者",
        ]);
        assert.equal(await card.locator(".before dd").textContent(), cue.original_label);
        assert.equal(await card.locator(".after dd").textContent(), cue.label);
      }
      await openChecks();
      assert.equal(await cards.count(), ledger.items.length);
    });

    await t.test("candidate, verdict, and source-text search combine correctly", async () => {
      await page.getByRole("button", { name: "查看沈伯洋的查核" }).click();
      assert.equal(await cards.count(), 5);
      await page.locator("#verdict-filter").selectOption("needs-context");
      assert.equal(await cards.count(), 2);
      await page.locator("#search").fill("USPSTF");
      assert.equal(await cards.count(), 1);
      assert.equal(await cards.first().getAttribute("id"), "check-FC010");
      assert.equal(await cards.first().locator("details").getAttribute("open"), "");
      assert((await cards.first().locator("mark").count()) > 0);
      assert.equal(await page.locator(".candidate-coverage").count(), 2);
      await reset();
      assert.equal(await cards.count(), 10);
      await page.locator("#speaker-filter").selectOption("SPEAKER_04");
      assert.equal(await cards.count(), 5);
      await page.locator("#verdict-filter").selectOption("supported");
      assert.equal(await cards.count(), 2);
      await reset();
    });

    await t.test("empty results and reset do not imply factual accuracy", async () => {
      await page.locator("#verdict-filter").selectOption("contradicted");
      assert.equal(await cards.count(), 0);
      assert.equal(await page.locator("#empty-state").isVisible(), true);
      assert.match(await page.locator("#result-status").textContent(), /0 項事實查核/);
      await page.locator("#empty-reset").click();
      assert.equal(await cards.count(), 10);
      await page.locator("#search").fill("no-such-claim-12345");
      assert.equal(await cards.count(), 0);
      await page.locator("#clear-search").click();
      assert.equal(await cards.count(), 10);
      await page.locator("#speaker-filter").selectOption("SPEAKER_00");
      assert.equal(await cards.count(), 0);
      await reset();
    });

    await t.test("timestamps and transcript return retain the correct cue", async () => {
      const item = ledger.items.find((entry) => entry.id === "FC004");
      assert(item);
      await page.locator("#check-FC004 .time-button").click();
      assert.match(await page.locator("#video-link").getAttribute("href"), /t=1884/);
      assert.equal(await page.locator("#panel-fact-checks").isVisible(), true);
      await page.locator("#check-FC004 .text-button").click();
      assert.equal(await page.locator("#tab-transcript").getAttribute("aria-selected"), "true");
      const cue = page.locator(`#cue-${item.quotes[0].cue_id}`);
      assert.equal(await cue.isVisible(), true);
      assert.match(await cue.getAttribute("class"), /is-target/);
      assert.equal(
        await cue.locator("button").evaluate((button) => button === document.activeElement),
        true,
      );
    });

    await t.test("tab keys and overview hash navigation work repeatedly", async () => {
      await page.locator("#tab-transcript").focus();
      await page.keyboard.press("ArrowRight");
      assert.equal(await page.locator("#tab-fact-checks").getAttribute("aria-selected"), "true");
      await page.keyboard.press("End");
      assert.equal(await page.locator("#tab-pending").getAttribute("aria-selected"), "true");
      await page.keyboard.press("Home");
      assert.equal(await page.locator("#tab-transcript").getAttribute("aria-selected"), "true");
      const overview = page.locator('.intro a[href="#fact-checks"]');
      await overview.click();
      await page.locator("#panel-fact-checks").waitFor({ state: "visible" });
      await page.locator("#tab-transcript").click();
      await overview.click();
      await page.locator("#panel-fact-checks").waitFor({ state: "visible" });
    });

    await t.test("desktop and narrow mobile layouts have no page overflow", async () => {
      await mkdir(screenshotDir, { recursive: true });
      await page.locator(".fact-check-evidence").evaluateAll((details) => {
        for (const item of details) item.open = true;
      });
      for (const width of [1440, 390, 320]) {
        await page.setViewportSize({ width, height: 1000 });
        await page.evaluate(() =>
          document.getElementById("record").scrollIntoView({ block: "start", behavior: "instant" }),
        );
        assert.equal(
          await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
          false,
          `page overflow at ${width}px`,
        );
        await page.screenshot({
          path: fileURLToPath(new URL(`width-${width}.png`, screenshotDir)),
        });
      }
    });

    await t.test("the generated single-file page works offline", async () => {
      await context.setOffline(true);
      await page.goto(`${pageURL.href}#fact-checks`, { waitUntil: "domcontentloaded" });
      await page.locator("#panel-fact-checks").waitFor({ state: "visible" });
      assert.equal(await cards.count(), 10);
      await page.locator("#search").fill("生育");
      assert((await cards.count()) > 0);
      assert.equal(await page.locator("#panel-fact-checks").isVisible(), true);
    });
    assert.deepEqual(errors, []);
    await context.close();
  } finally {
    await browser?.close();
    await new Promise((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
