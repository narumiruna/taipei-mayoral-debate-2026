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

// This API stub controls time and readiness without loading or playing a remote video.
function installChapterPlayer() {
  const probe = { calls: [], scrolls: [] };
  window.chapterProbe = probe;
  const scrollIntoView = Element.prototype.scrollIntoView;
  Element.prototype.scrollIntoView = function (options) {
    probe.scrolls.push(this.id);
    return scrollIntoView.call(this, options);
  };
  window.YT = {
    Player: class {
      constructor(_element, { events }) {
        let seconds = 0;
        let state = 5;
        let failureCode;
        this.getCurrentTime = () => seconds;
        this.getPlayerState = () => state;
        this.seekTo = (time, allowSeekAhead) => {
          probe.calls.push(["seek", time, allowSeekAhead]);
          seconds = time;
        };
        this.cueVideoById = ({ videoId, startSeconds }) => {
          probe.calls.push(["cue", startSeconds, videoId]);
          seconds = startSeconds;
          state = 5;
        };
        this.playVideo = () => {
          probe.calls.push(["play"]);
          if (failureCode !== undefined) {
            events.onError({ data: failureCode });
            return;
          }
          state = 1;
          events.onStateChange({ data: state });
        };
        probe.ready = () => events.onReady({ target: this });
        probe.tick = (time, playerState = 1) => {
          seconds = time;
          state = playerState;
          events.onStateChange({ data: state });
        };
        probe.fail = (code) => {
          failureCode = code;
          state = -1;
          events.onError({ data: code });
        };
      }
    },
  };
}

function chapterEntries(items, ancestors = [], path = []) {
  return items.flatMap((chapter) => {
    const entry = { ...chapter, ancestors, path: [...path, chapter.title] };
    return [
      entry,
      ...(chapter.children
        ? chapterEntries(chapter.children, [...ancestors, chapter.id], entry.path)
        : []),
    ];
  });
}

function chapterTime(seconds) {
  const hours = Math.floor(seconds / 3600);
  const clock = [Math.floor(seconds / 60) % 60, Math.floor(seconds) % 60]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
  return hours ? `${hours}:${clock}` : clock;
}

const chapterButton = (page, id) => page.locator(`.chapter-button[data-chapter-id="${id}"]`);
const chapterGroup = (page, id) => page.locator(`details[data-chapter-group="${id}"]`);
const chapterSummary = (page, id) => chapterGroup(page, id).locator(":scope > summary");

async function openChapterPath(page, entry) {
  for (const id of [...entry.ancestors, ...(entry.children ? [entry.id] : [])]) {
    if (!(await chapterGroup(page, id).evaluate((group) => group.open))) {
      await chapterSummary(page, id).click();
    }
  }
}

async function assertChapterTarget(page, entry, { playback = true } = {}) {
  await page.waitForFunction(
    (id) => document.activeElement === document.querySelector(`#cue-${id} > button`),
    entry.start_cue_id,
  );
  assert.equal(await page.locator("#tab-transcript").getAttribute("aria-selected"), "true");
  assert.equal(await page.locator("#search").inputValue(), "");
  assert.equal(await page.locator("#speaker-filter").inputValue(), "__all__");
  assert.equal(await page.locator("#verdict-filter").inputValue(), "__all__");
  assert.equal(new URL(page.url()).hash, `#cue-${entry.start_cue_id}`);
  const target = page.locator(`#cue-${entry.start_cue_id}`);
  assert.equal(await target.isVisible(), true);
  assert.match(await target.getAttribute("class"), /\bis-target\b/);
  assert.equal(await page.locator(".cue.is-target").count(), 1);
  const videoLink = new URL(await page.locator("#video-link").getAttribute("href"));
  assert.equal(videoLink.hostname, "youtu.be");
  const videoID = new URL(await page.locator("#debate-video").getAttribute("src")).pathname
    .split("/")
    .at(-1);
  assert.equal(videoLink.pathname, `/${videoID}`);
  assert.equal(videoLink.searchParams.get("t"), String(Math.floor(entry.start)));
  assert(
    await target.evaluate((cue) => {
      const rect = cue.getBoundingClientRect();
      return rect.bottom > 0 && rect.top < innerHeight;
    }),
  );
  if (playback) {
    const calls = await page.evaluate(() => window.chapterProbe.calls);
    assert.deepEqual(calls, [["seek", entry.start, true], ["play"]]);
    assert(
      (await page.evaluate(() => window.chapterProbe.scrolls)).includes(
        `cue-${entry.start_cue_id}`,
      ),
    );
  }
}

await test("chapter navigation uses a deterministic YouTube API with external requests blocked", async (t) => {
  const html = publishedFiles.get("index.html").toString("utf8");
  const payloadPattern = /(<script[^>]*id="debate-data"[^>]*>)([\s\S]*?)(<\/script>)/;
  const payloadMatch = html.match(payloadPattern);
  assert(payloadMatch, "generated page has its embedded data payload");
  const data = JSON.parse(payloadMatch[2]);
  assert(data.chapters, "build must include the curated chapter metadata");
  const entries = chapterEntries(data.chapters.items);
  const leaves = entries.filter((entry) => !entry.children);
  const groups = entries.filter((entry) => entry.children);
  assert.equal(leaves.length, 20);
  assert.equal(groups.length, 10);
  assert.deepEqual(
    leaves.map(({ id }) => id),
    [
      "introduction",
      "shen-opening",
      "chiang-opening",
      ...[1, 2, 3, 4].flatMap((round) => [
        `cross-round-${round}-chiang-asks`,
        `cross-round-${round}-shen-asks`,
      ]),
      "fan-question",
      "fan-chiang-answer",
      "fan-shen-answer",
      "huang-question",
      "huang-shen-answer",
      "huang-chiang-answer",
      "chiang-closing",
      "shen-closing",
      "final-host",
    ],
  );
  assert.deepEqual(
    groups.map(({ id }) => id),
    [
      "opening-statements",
      "cross-examination",
      "cross-round-1",
      "cross-round-2",
      "cross-round-3",
      "cross-round-4",
      "media-questions",
      "fan-qiming",
      "huang-yanyi",
      "closing-statements",
    ],
  );
  const screenshotDir = new URL("../outputs/chapters/", import.meta.url);
  const server = createServer((request, response) => {
    const pathname = new URL(request.url, "http://localhost").pathname;
    const name = pathname.startsWith(basePath)
      ? pathname.slice(basePath.length) || "index.html"
      : "";
    const content = publishedFiles.get(name);
    response.writeHead(content ? 200 : 404, {
      "Content-Type": name.endsWith(".html") ? "text/html; charset=utf-8" : "application/json",
    });
    response.end(content);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert(address && typeof address === "object");
  const origin = `http://127.0.0.1:${address.port}`;
  const url = `${origin}${basePath}`;
  let browser;
  const contexts = [];
  const errors = [];
  const externalRequests = [];
  try {
    browser = await chromium.launch({ headless: true });
    async function newChapterPage({ mock = true, payload } = {}) {
      const context = await browser.newContext({
        viewport: { width: 1440, height: 1000 },
        reducedMotion: "reduce",
      });
      contexts.push(context);
      await context.route("**/*", (route) => {
        const requestURL = new URL(route.request().url());
        if (requestURL.protocol === "file:") return route.continue();
        if (requestURL.origin !== origin) {
          externalRequests.push(requestURL.href);
          return route.abort();
        }
        if (payload && requestURL.pathname === basePath) {
          const encoded = JSON.stringify(payload).replaceAll("<", "\\u003c");
          return route.fulfill({
            contentType: "text/html; charset=utf-8",
            body: html.replace(
              payloadPattern,
              (_match, start, _data, end) => `${start}${encoded}${end}`,
            ),
          });
        }
        return route.continue();
      });
      if (mock) await context.addInitScript(installChapterPlayer);
      const page = await context.newPage();
      page.on("pageerror", (error) => errors.push(error.message));
      return page;
    }
    const page = await newChapterPage();
    const load = async (hash = "", ready = true) => {
      // A hash-only goto can reuse the previous document and its ready player.
      await page.goto("about:blank");
      await page.goto(`${url}${hash}`, { waitUntil: "domcontentloaded" });
      await page.locator("#chapters > ol.chapter-list").waitFor();
      await page.waitForFunction(() => typeof window.chapterProbe?.ready === "function");
      if (ready) await page.evaluate(() => window.chapterProbe.ready());
    };
    const resetProbe = () =>
      page.evaluate(() => {
        window.chapterProbe.calls.length = 0;
        window.chapterProbe.scrolls.length = 0;
      });

    await t.test(
      "hierarchy, text labels, accessible paths, and initial disclosure states",
      async () => {
        await load();
        assert.equal(await page.locator("#chapters-title").textContent(), "辯論流程");
        assert.equal(await page.locator(".chapter-button:not(.chapter-start)").count(), 20);
        assert.equal(await page.locator(".chapter-start").count(), 10);
        assert.equal(await page.locator("#chapters > ol > li").count(), 6);
        for (const entry of entries) {
          const button = chapterButton(page, entry.id);
          assert.equal(
            await button.locator(".chapter-time").textContent(),
            chapterTime(entry.start),
          );
          const name = await button.getAttribute("aria-label");
          assert(name.includes(entry.path.join("／")), entry.id);
          assert(name.includes(chapterTime(entry.start)), entry.id);
          assert.equal(await button.getAttribute("type"), "button");
          if (entry.children) {
            assert.equal(await chapterSummary(page, entry.id).textContent(), entry.title);
            assert.equal(
              await chapterGroup(page, entry.id).evaluate((group) => group.open),
              entry.ancestors.length === 0,
            );
            assert.equal(await chapterSummary(page, entry.id).locator("button").count(), 0);
            const firstLeaf = leaves.find((leaf) => leaf.ancestors.includes(entry.id));
            assert.equal(entry.start_cue_id, firstLeaf.start_cue_id);
          } else {
            assert.equal(await button.locator(".chapter-label").textContent(), entry.title);
          }
        }
        assert.deepEqual(await page.evaluate(() => window.chapterProbe.calls), []);
        assert.equal(await page.locator("#follow-playback").isChecked(), false);
        assert.equal(await page.locator('#chapters [aria-current="true"]').count(), 0);
        assert.doesNotMatch(
          await page.locator("#chapters").textContent(),
          /每\s*10\s*分鐘|時間索引/,
        );
      },
    );

    for (const tab of ["transcript", "fact-checks", "corrections", "pending"]) {
      await t.test(
        `all 20 leaves and 10 group starts clear combined filters from ${tab}`,
        async () => {
          for (const entry of entries) {
            await page.locator("#tab-fact-checks").click();
            await page.locator("#speaker-filter").selectOption("SPEAKER_04");
            await page.locator("#verdict-filter").selectOption("contradicted");
            await page.locator("#search").fill("no-chapter-results-12345");
            await page.locator(`#tab-${tab}`).click();
            assert.equal(await page.locator("#search").inputValue(), "no-chapter-results-12345");
            await openChapterPath(page, entry);
            await resetProbe();
            await chapterButton(page, entry.id).click();
            await assertChapterTarget(page, entry);
            for (const id of entry.ancestors) {
              assert.equal(await chapterGroup(page, id).evaluate((group) => group.open), true);
            }
          }
        },
      );
    }

    await t.test(
      "native disclosures do not seek; Tab, Enter, and Space operate chapter controls",
      async () => {
        await load();
        const group = chapterGroup(page, "cross-examination");
        const summary = chapterSummary(page, "cross-examination");
        await resetProbe();
        await summary.click();
        assert.equal(await group.evaluate((node) => node.open), false);
        await summary.focus();
        await page.keyboard.press("Enter");
        assert.equal(await group.evaluate((node) => node.open), true);
        await page.keyboard.press("Space");
        assert.equal(await group.evaluate((node) => node.open), false);
        await page.keyboard.press("Enter");
        await page.keyboard.press("Tab");
        assert.equal(
          await chapterButton(page, "cross-examination").evaluate(
            (node) => node === document.activeElement,
          ),
          true,
        );
        assert.deepEqual(await page.evaluate(() => window.chapterProbe.calls), []);
        assert.equal(new URL(page.url()).hash, "");
        for (const [id, key] of [
          ["cross-examination", "Enter"],
          ["cross-round-1-chiang-asks", "Space"],
        ]) {
          const entry = entries.find((entry) => entry.id === id);
          await openChapterPath(page, entry);
          await chapterButton(page, id).focus();
          await resetProbe();
          await page.keyboard.press(key);
          await assertChapterTarget(page, entry);
        }
      },
    );

    await t.test(
      "cue and time fragment reloads queue the original time without autoplay",
      async () => {
        const leaf = leaves.find((entry) => entry.id === "cross-round-3-shen-asks");
        const seconds = leaf.start + 0.25;
        for (const [hash, expectedTime, expectedCue] of [
          [`#cue-${leaf.start_cue_id}`, leaf.start, leaf.start_cue_id],
          [`#time-${seconds}`, seconds, data.cues.find((cue) => cue.end > seconds).id],
        ]) {
          await load(hash, false);
          assert.deepEqual(await page.evaluate(() => window.chapterProbe.calls), []);
          assert.match(
            await page.locator(`#cue-${expectedCue}`).getAttribute("class"),
            /is-target/,
          );
          assert.equal(
            new URL(await page.locator("#video-link").getAttribute("href")).searchParams.get("t"),
            String(Math.floor(expectedTime)),
          );
          for (const id of leaf.ancestors)
            assert.equal(await chapterGroup(page, id).evaluate((node) => node.open), true);
          await page.evaluate(() => window.chapterProbe.ready());
          let calls = await page.evaluate(() => window.chapterProbe.calls);
          assert.equal(calls.length, 1);
          assert.equal(calls[0][0], "cue");
          assert.equal(calls[0][1], expectedTime);
          assert.equal(new URL(page.url()).hash, hash);
          await page.reload({ waitUntil: "domcontentloaded" });
          await page.waitForFunction(() => typeof window.chapterProbe?.ready === "function");
          assert.deepEqual(await page.evaluate(() => window.chapterProbe.calls), []);
          await page.evaluate(() => window.chapterProbe.ready());
          calls = await page.evaluate(() => window.chapterProbe.calls);
          assert.equal(calls.length, 1);
          assert.deepEqual(calls[0].slice(0, 2), ["cue", expectedTime]);
        }
      },
    );

    await t.test(
      "current leaf and ancestor markers honor every half-open boundary and advertisement gap",
      async () => {
        await load();
        // Keep a mixed disclosure state. Playback must not change it, focus, or scroll.
        await chapterSummary(page, "opening-statements").click();
        await chapterSummary(page, "cross-round-2").click();
        await page.locator("#search").focus();
        await resetProbe();
        const before = await page.evaluate(() => ({
          open: [...document.querySelectorAll(".chapter-group")].map((node) => [
            node.dataset.chapterGroup,
            node.open,
          ]),
          focus: document.activeElement.id,
          windowY: scrollY,
          sidebarY: document.querySelector(".sidebar-sticky").scrollTop,
        }));
        const gaps = leaves.slice(1).flatMap((leaf, index) => {
          const previous = leaves[index];
          return leaf.start > previous.end ? [(previous.end + leaf.start) / 2] : [];
        });
        const advertisementGaps = leaves
          .slice(1)
          .filter((leaf, index) => leaf.start - leaves[index].end > 60);
        assert(advertisementGaps.length >= 4, "curated advertisement gaps must be tested");
        const points = [
          ...new Set([
            0,
            leaves[0].start / 2,
            leaves.at(-1).end + 1,
            ...gaps,
            ...leaves.flatMap(({ start, end }) => [
              start - 0.001,
              start,
              start + 0.001,
              end - 0.001,
              end,
              end + 0.001,
            ]),
          ]),
        ];
        for (const seconds of points) {
          const expected = leaves.find((leaf) => leaf.start <= seconds && seconds < leaf.end);
          const state = await page.evaluate((seconds) => {
            window.chapterProbe.tick(seconds);
            return {
              active: [...document.querySelectorAll('#chapters [aria-current="true"]')].map(
                (node) => node.dataset.chapterId,
              ),
              parents: [...document.querySelectorAll(".chapter-group.is-active-section")].map(
                (node) => node.dataset.chapterGroup,
              ),
              open: [...document.querySelectorAll(".chapter-group")].map((node) => [
                node.dataset.chapterGroup,
                node.open,
              ]),
              focus: document.activeElement.id,
              windowY: scrollY,
              sidebarY: document.querySelector(".sidebar-sticky").scrollTop,
              scrolls: window.chapterProbe.scrolls,
            };
          }, seconds);
          assert.deepEqual(state.active, expected ? [expected.id] : [], `leaf at ${seconds}`);
          assert.deepEqual(state.parents, expected?.ancestors ?? [], `ancestors at ${seconds}`);
          assert.deepEqual(state.open, before.open, `disclosures at ${seconds}`);
          assert.equal(state.focus, before.focus, `focus at ${seconds}`);
          assert.equal(state.windowY, before.windowY, `page scroll at ${seconds}`);
          assert.equal(state.sidebarY, before.sidebarY, `sidebar scroll at ${seconds}`);
          assert.deepEqual(state.scrolls, [], `scrollIntoView at ${seconds}`);
        }
        assert.equal(await page.locator("#follow-playback").isChecked(), false);
        assert.deepEqual(await page.evaluate(() => window.chapterProbe.calls), []);
      },
    );

    await t.test(
      "explicit cue navigation opens ancestors and follow playback still scrolls without taking focus",
      async () => {
        await load();
        const leaf = leaves.find((entry) => entry.id === "huang-shen-answer");
        await chapterSummary(page, "media-questions").click();
        await page.evaluate((id) => {
          location.hash = `cue-${id}`;
        }, leaf.start_cue_id);
        await page.waitForFunction(
          (id) => document.querySelector(`#cue-${id}`)?.classList.contains("is-target"),
          leaf.start_cue_id,
        );
        for (const id of leaf.ancestors)
          assert.equal(await chapterGroup(page, id).evaluate((node) => node.open), true);
        assert.equal(
          (await page.evaluate(() => window.chapterProbe.calls)).some(([kind]) => kind === "play"),
          false,
        );
        await page.locator("#follow-playback").check();
        await page.locator("#search").focus();
        // Check the behavior with a closed active group as well as a distant cue.
        await chapterSummary(page, "media-questions").click();
        await page.locator("#search").focus();
        await resetProbe();
        await page.evaluate((seconds) => window.chapterProbe.tick(seconds), leaf.start);
        assert(
          (await page.evaluate(() => window.chapterProbe.scrolls)).includes(
            `cue-${leaf.start_cue_id}`,
          ),
        );
        assert.equal(
          await page.locator("#search").evaluate((node) => node === document.activeElement),
          true,
        );
        assert(
          await page.locator(`#cue-${leaf.start_cue_id}`).evaluate((node) => {
            const rect = node.getBoundingClientRect();
            return rect.bottom > 0 && rect.top < innerHeight;
          }),
        );
        assert.equal(
          await chapterGroup(page, "media-questions").evaluate((node) => node.open),
          false,
        );
        await resetProbe();
        const next = leaves.find((entry) => entry.id === "chiang-closing");
        await page.evaluate((seconds) => window.chapterProbe.tick(seconds, 2), next.start);
        assert.deepEqual(await page.evaluate(() => window.chapterProbe.scrolls), []);
        await page.locator("#follow-playback").uncheck();
        await resetProbe();
        await page.evaluate((seconds) => window.chapterProbe.tick(seconds), next.start);
        assert.deepEqual(await page.evaluate(() => window.chapterProbe.scrolls), []);
      },
    );

    await t.test("fact-check return remains non-playing with the API available", async () => {
      await load();
      await page.locator("#tab-fact-checks").click();
      await resetProbe();
      await page.locator("#check-FC004 .text-button").click();
      const cueId = ledger.items.find((entry) => entry.id === "FC004").quotes[0].cue_id;
      await page.waitForFunction(
        (id) => document.activeElement === document.querySelector(`#cue-${id} > button`),
        cueId,
      );
      const calls = await page.evaluate(() => window.chapterProbe.calls);
      assert.equal(calls.length, 1);
      assert.deepEqual(calls[0].slice(0, 2), [
        "cue",
        data.cues.find((cue) => cue.id === cueId).start,
      ]);
      assert.equal(new URL(page.url()).hash, `#cue-${cueId}`);
    });

    await t.test(
      "blocked and failed YouTube preserve text navigation and timestamped fallback links",
      async () => {
        const blocked = await newChapterPage({ mock: false });
        await blocked.goto(url, { waitUntil: "domcontentloaded" });
        await blocked.locator("#media-error").waitFor({ state: "visible" });
        const leaf = leaves.find((entry) => entry.id === "cross-round-4-shen-asks");
        await blocked.locator("#tab-pending").click();
        await blocked.locator("#search").fill("no-results");
        await openChapterPath(blocked, leaf);
        await chapterButton(blocked, leaf.id).click();
        await assertChapterTarget(blocked, leaf, { playback: false });
        assert.match(await blocked.locator("#media-error").textContent(), /YouTube/);
        await blocked.context().close();
        await load();
        await page.evaluate(() => window.chapterProbe.fail(150));
        assert.match(await page.locator("#media-error").textContent(), /嵌入播放/);
        await openChapterPath(page, leaf);
        await resetProbe();
        await chapterButton(page, leaf.id).click();
        await assertChapterTarget(page, leaf);
        assert.equal(await page.locator("#media-error").isVisible(), true);
        assert.match(await page.locator("#media-error").textContent(), /嵌入播放/);
      },
    );

    await t.test(
      "single-file chapter navigation works offline without remote resources",
      async () => {
        const offline = await newChapterPage();
        await offline.context().setOffline(true);
        await offline.goto(pageURL.href, { waitUntil: "domcontentloaded" });
        await offline.waitForFunction(() => typeof window.chapterProbe?.ready === "function");
        await offline.evaluate(() => window.chapterProbe.ready());
        await offline.locator("#tab-corrections").click();
        await offline.locator("#search").fill("no-offline-results");
        const leaf = leaves.find((entry) => entry.id === "fan-shen-answer");
        await openChapterPath(offline, leaf);
        await offline.evaluate(() => {
          window.chapterProbe.calls.length = 0;
          window.chapterProbe.scrolls.length = 0;
        });
        await chapterButton(offline, leaf.id).click();
        await assertChapterTarget(offline, leaf);
        await offline.context().close();
      },
    );

    await t.test(
      "missing and empty chapter metadata show only the documented fallback",
      async () => {
        for (const missing of [true, false]) {
          const payload = structuredClone(data);
          if (missing) delete payload.chapters;
          else payload.chapters.items = [];
          const variant = await newChapterPage({ payload });
          await variant.goto(url, { waitUntil: "domcontentloaded" });
          await variant.locator("#chapters .index-note").waitFor();
          assert.equal(await variant.locator("#chapters").textContent(), "尚無章節資料");
          assert.equal(await variant.locator("#chapters button, #chapters details").count(), 0);
          assert.equal((await variant.locator(".turn").count()) > 0, true);
          assert.equal(await variant.locator("a[download]").count(), 5);
          await variant.context().close();
        }
      },
    );

    await t.test(
      "chapter titles are text, not HTML, including summary and accessible names",
      async () => {
        const payload = structuredClone(data);
        const group = payload.chapters.items.find((entry) => entry.children);
        const malicious =
          '<img src=x onerror="window.chapterTitleExecuted=true"> & <script>bad()</script>';
        group.title = malicious;
        group.children[0].title = malicious;
        const variant = await newChapterPage({ payload });
        await variant.goto(url, { waitUntil: "domcontentloaded" });
        await variant.locator("#chapters > ol").waitFor();
        assert.equal(await chapterSummary(variant, group.id).textContent(), malicious);
        const button = chapterButton(variant, group.children[0].id);
        assert.equal(await button.locator(".chapter-label").textContent(), malicious);
        assert((await button.getAttribute("aria-label")).includes(`${malicious}／${malicious}`));
        assert.equal(await variant.locator("#chapters img, #chapters script").count(), 0);
        assert.equal(await variant.evaluate(() => window.chapterTitleExecuted), undefined);
        await variant.context().close();
      },
    );

    await t.test(
      "expanded and collapsed navigation fits 1440, 390, and 320 pixel widths",
      async () => {
        await load();
        await mkdir(screenshotDir, { recursive: true });
        for (const width of [1440, 390, 320]) {
          await page.setViewportSize({ width, height: 1000 });
          for (const expanded of [true, false]) {
            await page.locator(".chapter-group").evaluateAll((groups, expanded) => {
              for (const group of groups) group.open = expanded;
            }, expanded);
            await page
              .locator("#chapters-title")
              .evaluate((node) => node.scrollIntoView({ block: "start", behavior: "instant" }));
            assert.equal(
              await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
              false,
              `page overflow at ${width}px`,
            );
            assert.equal(
              await page
                .locator("#chapters")
                .evaluate((node) => node.scrollWidth > node.clientWidth),
              false,
              `chapter overflow at ${width}px`,
            );
            assert.equal(
              await page.locator(".chapter-button:not(.chapter-start):visible").count(),
              expanded ? 20 : 2,
            );
            await page.screenshot({
              path: fileURLToPath(
                new URL(`width-${width}-${expanded ? "expanded" : "collapsed"}.png`, screenshotDir),
              ),
            });
          }
        }
      },
    );

    await t.test(
      "Tab reaches the final entry in the existing desktop sidebar scroll container at 1440x700",
      async () => {
        await load();
        await page.setViewportSize({ width: 1440, height: 700 });
        await page.locator(".chapter-group").evaluateAll((groups) => {
          for (const group of groups) group.open = true;
        });
        const sidebar = await page.locator(".sidebar-sticky").evaluate((node) => ({
          overflow: getComputedStyle(node).overflowY,
          client: node.clientHeight,
          scroll: node.scrollHeight,
        }));
        assert.equal(sidebar.overflow, "auto");
        assert(sidebar.scroll > sidebar.client);
        await chapterButton(page, "introduction").focus();
        const visited = [];
        for (let count = 0; count < entries.length + groups.length + 1; count++) {
          const current = await page.evaluate(() => ({
            id: document.activeElement.dataset.chapterId,
            summary: document.activeElement.tagName === "SUMMARY",
            inside: !!document.activeElement.closest("#chapters"),
          }));
          assert.equal(
            current.inside,
            true,
            "Tab must stay in chapter controls until the last entry",
          );
          if (current.id) visited.push(current.id);
          else assert.equal(current.summary, true);
          if (current.id === "final-host") break;
          await page.keyboard.press("Tab");
        }
        assert.deepEqual(
          visited,
          entries.map(({ id }) => id),
        );
        assert(
          await chapterButton(page, "final-host").evaluate((node) => {
            const rect = node.getBoundingClientRect();
            const container = node.closest(".sidebar-sticky");
            const parent = container.getBoundingClientRect();
            return (
              rect.top >= Math.max(0, parent.top) &&
              rect.bottom <= Math.min(innerHeight, parent.bottom) &&
              container.scrollTop > 0
            );
          }),
        );
        await page.screenshot({
          path: fileURLToPath(new URL("keyboard-last-1440x700.png", screenshotDir)),
        });
        const last = leaves.at(-1);
        await resetProbe();
        await page.keyboard.press("Enter");
        await assertChapterTarget(page, last);
      },
    );

    assert(
      externalRequests.some((request) => request.includes("youtube")),
      "external YouTube requests were blocked",
    );
    assert.deepEqual(errors, []);
  } finally {
    await Promise.all(contexts.map((context) => context.close()));
    await browser?.close();
    await new Promise((resolve, reject) =>
      server.close((error) => (error ? reject(error) : resolve())),
    );
  }
});
