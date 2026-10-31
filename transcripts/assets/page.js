/* Generated from web/page.ts. Run bun run build to update. */ "use strict";
(() => {

  // web/page.ts
  (() => {
    function requiredElement(id, type) {
      const node = document.getElementById(id);
      if (!(node instanceof type)) {
        throw new Error(`Required element #${id} must be a ${type.name}`);
      }
      return node;
    }
    const $ = (id) => requiredElement(id, HTMLElement);
    const data = JSON.parse($("debate-data").textContent ?? "");
    const cues = data.cues;
    const corrections = data.review.corrections;
    const flags = data.review.flags;
    const factChecks = data.fact_checks?.items ?? [];
    const verdictLabels = {
      supported: "有資料支持",
      "needs-context": "需補充脈絡",
      contradicted: "與資料不符",
      "insufficient-evidence": "證據不足"
    };
    const verdictOrder = [
      "supported",
      "needs-context",
      "contradicted",
      "insufficient-evidence"
    ];
    const cueById = new Map(cues.map((cue) => [String(cue.id), cue]));
    const chronological = [...cues].sort((a, b) => a.start - b.start);
    const speakerKey = (cue) => cue?.speaker || "UNKNOWN";
    const speakers = [...new Set(cues.map(speakerKey))];
    const knownSpeakers = speakers.filter((speaker) => speaker !== "UNKNOWN");
    const speakerIndex = new Map(knownSpeakers.map((speaker, index) => [speaker, index]));
    const correctedIds = new Set(corrections.map((item) => String(item.cue_id)));
    const pendingIds = new Set(flags.map((item) => String(item.cue_id)));
    const video = requiredElement("debate-video", HTMLIFrameElement);
    const videoLink = requiredElement("video-link", HTMLAnchorElement);
    const videoId = new URL(video.src).pathname.split("/").pop() || "";
    const search = requiredElement("search", HTMLInputElement);
    const speakerFilter = requiredElement("speaker-filter", HTMLSelectElement);
    const verdictFilter = requiredElement("verdict-filter", HTMLSelectElement);
    const followPlayback = requiredElement("follow-playback", HTMLInputElement);
    const readingTools = requiredElement("reading-tools", HTMLDetailsElement);
    const toolsSummary = $("tools-summary");
    const compactTools = window.matchMedia("(max-width: 820px)");
    const tabs = [...document.querySelectorAll('[role="tab"]')].map((button) => {
      if (!(button instanceof HTMLButtonElement)) {
        throw new Error("Each tab must be a button");
      }
      const view = button.dataset.view;
      if (view !== "transcript" && view !== "fact-checks" && view !== "corrections" && view !== "pending") {
        throw new Error(`Invalid tab view: ${view}`);
      }
      return { button, view };
    });
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const duration = Math.max(Number(data.metadata.duration) || 0, ...cues.map((cue) => cue.end), 0);
    const formatNumber = (value) => new Intl.NumberFormat("zh-TW").format(value);
    let currentView = "transcript";
    let query = "";
    let selectedSpeaker = "__all__";
    let activeId = null;
    let targetId = null;
    let player = null;
    let pendingSeek = null;
    let mediaFailed = false;
    let autoplayBlocked = false;
    let lastFollowedId = null;
    let cueElements = new Map;
    const chapterLeaves = [];
    const chapterGroups = [];
    function element(tag, className, text) {
      const node = document.createElement(tag);
      if (className)
        node.className = className;
      if (text !== undefined)
        node.textContent = String(text);
      return node;
    }
    function time(seconds) {
      const total = Math.max(0, Math.floor(Number(seconds) || 0));
      const hours = Math.floor(total / 3600);
      const minutes = Math.floor(total % 3600 / 60);
      const remainder = String(total % 60).padStart(2, "0");
      return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${remainder}` : `${String(minutes).padStart(2, "0")}:${remainder}`;
    }
    function speakerName(speaker, cue) {
      if (cue?.label)
        return cue.label;
      const role = data.roles[speaker];
      if (role?.organization)
        return [role.name || role.role, role.organization].join("／");
      if (role)
        return [role.role, role.name].filter(Boolean).join("／") || "說話者未確認";
      return speaker === "UNKNOWN" ? "說話者未確認" : `${speaker}（角色未確認）`;
    }
    function speakerBadge(cue) {
      const speaker = speakerKey(cue);
      const index = speakerIndex.get(speaker);
      const color = speaker === "UNKNOWN" ? "speaker-unknown" : `speaker-${(index ?? 0) % 6}`;
      const badge = element("span", `speaker-badge ${color}`);
      const code = speaker === "UNKNOWN" ? "?" : String((index ?? 0) + 1).padStart(2, "0");
      const symbol = element("span", "speaker-code", code);
      symbol.setAttribute("aria-hidden", "true");
      const name = element("span");
      name.append(highlighted(speakerName(speaker, cue)));
      badge.append(symbol, name);
      return badge;
    }
    function textValue(value) {
      if (typeof value === "string")
        return value;
      return value == null ? "" : JSON.stringify(value) ?? "";
    }
    function highlighted(value) {
      const text = textValue(value);
      const fragment = document.createDocumentFragment();
      if (!query) {
        fragment.append(document.createTextNode(text));
        return fragment;
      }
      const lower = text.toLocaleLowerCase("zh-TW");
      let cursor = 0;
      let position = lower.indexOf(query);
      while (position !== -1) {
        fragment.append(document.createTextNode(text.slice(cursor, position)));
        fragment.append(element("mark", "", text.slice(position, position + query.length)));
        cursor = position + query.length;
        position = lower.indexOf(query, cursor);
      }
      fragment.append(document.createTextNode(text.slice(cursor)));
      return fragment;
    }
    function matches(cue, texts) {
      if (selectedSpeaker !== "__all__" && speakerKey(cue) !== selectedSpeaker)
        return false;
      return !query || texts.some((value) => textValue(value).toLocaleLowerCase("zh-TW").includes(query));
    }
    function applyPendingSeek() {
      if (!player || !pendingSeek)
        return;
      const { seconds, play } = pendingSeek;
      pendingSeek = null;
      autoplayBlocked = false;
      if (!play && player.getPlayerState() !== 1) {
        player.cueVideoById({ videoId, startSeconds: seconds });
      } else {
        player.seekTo(seconds, true);
        if (play)
          player.playVideo();
      }
    }
    function seek(cue, play = false) {
      const seconds = Number(cue.start) || 0;
      pendingSeek = { seconds, play };
      const link = new URL(videoLink.href);
      link.searchParams.set("t", String(Math.floor(seconds)));
      videoLink.href = link.href;
      setTarget(String(cue.id));
      chapterAt(seconds)?.ancestors.forEach((group) => {
        group.open = true;
      });
      try {
        const original = cueById.get(String(cue.id));
        const hash = original && Number(original.start) === seconds ? `#cue-${cue.id}` : `#time-${seconds}`;
        history.replaceState(null, "", hash);
      } catch {}
      applyPendingSeek();
      updatePlayback();
    }
    function timestampButton(cue) {
      const button = element("button", "time-button", time(cue.start));
      button.type = "button";
      button.setAttribute("aria-label", `從 ${time(cue.start)} 播放：${speakerName(speakerKey(cue), cue)}`);
      button.title = `播放 ${time(cue.start)}–${time(cue.end)}`;
      button.addEventListener("click", () => seek(cue, true));
      return button;
    }
    function setTarget(id) {
      if (targetId)
        cueElements.get(targetId)?.classList.remove("is-target");
      targetId = id;
      cueElements.get(id)?.classList.add("is-target");
    }
    function renderTranscript(visible) {
      const container = $("transcript-content");
      const fragment = document.createDocumentFragment();
      cueElements = new Map;
      let group = [];
      let characters = 0;
      function flush() {
        const first = group[0];
        const last = group[group.length - 1];
        if (!first || !last)
          return;
        const section = element("article", "turn");
        const header = element("header", "turn-header");
        const range = timestampButton(first);
        range.classList.add("turn-range");
        range.textContent = `${time(first.start)} — ${time(last.end)}`;
        header.append(speakerBadge(first), range);
        const paragraph = element("p", "turn-text");
        group.forEach((cue) => {
          const id = String(cue.id);
          const span = element("span", "cue");
          span.id = `cue-${id}`;
          span.title = `點選播放 ${time(cue.start)}–${time(cue.end)}`;
          span.addEventListener("click", (event) => {
            if (event.target instanceof Element && event.target.closest("button"))
              return;
            if (window.getSelection()?.toString())
              return;
            seek(cue, true);
          });
          span.append(timestampButton(cue), highlighted(cue.text));
          const corrected = correctedIds.has(id) || Boolean(cue.correction_id || cue.speaker_correction_id);
          const pending = pendingIds.has(id);
          if (corrected || pending) {
            const marker = element("span", "review-indicator", [corrected ? "校" : "", pending ? "待" : ""].filter(Boolean).join("・"));
            marker.title = [corrected ? "此段有校對修訂" : "", pending ? "此段有待確認項目" : ""].filter(Boolean).join("；");
            marker.setAttribute("aria-label", marker.title);
            span.append(marker);
          }
          if (id === activeId) {
            span.classList.add("is-active");
            span.setAttribute("aria-current", "true");
          }
          if (id === targetId)
            span.classList.add("is-target");
          cueElements.set(id, span);
          paragraph.append(span);
        });
        section.append(header, paragraph);
        fragment.append(section);
        group = [];
        characters = 0;
      }
      visible.forEach((cue) => {
        const previous = group[group.length - 1];
        const first = group[0];
        if (previous && first && (speakerKey(previous) !== speakerKey(cue) || cue.start - previous.end > 8 || characters > 280 || cue.start - first.start > 65))
          flush();
        group.push(cue);
        characters += cue.text.length;
      });
      flush();
      container.replaceChildren(fragment);
    }
    function detail(list, title, value) {
      const term = element("dt", "", title);
      const description = element("dd");
      description.append(highlighted(value || "未提供"));
      list.append(term, description);
    }
    function renderReview(items, pending) {
      const fragment = document.createDocumentFragment();
      items.forEach((item) => {
        const cue = cueById.get(String(item.cue_id));
        const card = element("article", "review-card");
        const header = element("header", "review-header");
        header.append(speakerBadge(cue), element("span", "record-id", `${pending ? "待確認" : "修訂"} ${item.id}`));
        if (cue)
          header.append(timestampButton(cue));
        else
          header.append(element("span", "pending-label", "對應字幕不存在"));
        card.append(header);
        if (pending) {
          const quote = element("blockquote", "pending-text");
          quote.append(highlighted(cue?.text || "未提供對應文字"));
          card.append(quote);
        } else if ("before" in item) {
          const comparison = element("dl", "comparison");
          const columns = [
            ["before", item.kind === "speaker" ? "原說話者" : "辨識原文", item.before],
            ["after", item.kind === "speaker" ? "修訂說話者" : "修訂文字", item.after]
          ];
          columns.forEach(([className, title, text]) => {
            const column = element("div", className);
            const description = element("dd");
            description.append(highlighted(text));
            column.append(element("dt", "", title), description);
            comparison.append(column);
          });
          card.append(comparison);
        }
        const details = element("dl", "review-details");
        detail(details, pending ? "待查原因" : "修訂原因", item.reason);
        detail(details, pending ? "待查建議" : "校對依據", "evidence" in item ? item.evidence : item.suggestion);
        if (pending)
          detail(details, "處理狀態", "尚未確認；建議不等於已採用修訂。");
        card.append(details);
        fragment.append(card);
      });
      $(pending ? "pending-content" : "corrections-content").replaceChildren(fragment);
    }
    function showTranscript(cue, play = false) {
      resetFilters();
      switchView("transcript");
      seek(cue, play);
      requestAnimationFrame(() => {
        const target = cueElements.get(String(cue.id));
        target?.scrollIntoView({ block: "center", behavior: "instant" });
        const button = target?.querySelector("button");
        if (button instanceof HTMLButtonElement)
          button.focus({ preventScroll: true });
      });
    }
    function renderFactCheckOverview() {
      const ledger = data.fact_checks;
      $("fact-check-date").textContent = ledger ? `查核日期 ${ledger.reviewed_at}` : "";
      $("fact-check-scope").textContent = ledger?.scope ?? "尚未收錄事實查核。";
      $("fact-check-method").textContent = ledger?.method ?? "查核內容將附原話、依據及限制。";
      const fragment = document.createDocumentFragment();
      [...new Set(factChecks.map((item) => item.speaker))].forEach((speaker) => {
        const items = factChecks.filter((item) => item.speaker === speaker);
        const card = element("section", "candidate-coverage");
        card.append(element("h4", "", data.roles[speaker]?.name || speaker), element("p", "coverage-total", `收錄 ${items.length} 項可核對說法`));
        const counts = element("dl", "coverage-counts");
        verdictOrder.forEach((verdict) => {
          const row = element("div");
          row.append(element("dt", "", verdictLabels[verdict]), element("dd", "", items.filter((item) => item.verdict === verdict).length));
          counts.append(row);
        });
        const button = element("button", "text-button", `查看${data.roles[speaker]?.name || speaker}的查核 →`);
        button.type = "button";
        button.addEventListener("click", () => {
          search.value = "";
          speakerFilter.value = speaker;
          verdictFilter.value = "__all__";
          render();
          $("result-status").scrollIntoView({ block: "center", behavior: "instant" });
        });
        card.append(counts, button);
        fragment.append(card);
      });
      $("fact-check-overview").replaceChildren(fragment);
    }
    function renderFactChecks(items) {
      const fragment = document.createDocumentFragment();
      items.forEach((item) => {
        const firstCue = cueById.get(String(item.quotes[0]?.cue_id));
        const card = element("article", "fact-check-card");
        card.id = `check-${item.id}`;
        const header = element("header", "review-header");
        header.append(speakerBadge(firstCue), element("span", `verdict verdict-${item.verdict}`, verdictLabels[item.verdict]), element("span", "record-id", item.id));
        if (firstCue)
          header.append(timestampButton(firstCue));
        const title = element("h4", "fact-check-title");
        title.append(highlighted(item.title));
        const summary = element("p", "fact-check-summary");
        summary.append(highlighted(item.summary));
        card.append(header, title, summary, element("h5", "fact-check-label", "辯論原話（逐字稿節錄）"));
        const quote = element("blockquote", "fact-check-quote");
        item.quotes.forEach((part, index) => {
          const previous = item.quotes[index - 1];
          if (previous && part.cue_id !== previous.cue_id + 1)
            quote.append(" […] ");
          quote.append(highlighted(part.text));
        });
        card.append(quote);
        const uncertain = item.quotes.some((part) => pendingIds.has(String(part.cue_id)));
        if (uncertain) {
          card.append(element("p", "pending-label", "此引文含待確認字幕，請先回聽；不可僅據辨識文字判定候選人說錯。"));
        }
        if (firstCue) {
          const transcript = element("button", "text-button", "回到逐字稿，閱讀前後文 →");
          transcript.type = "button";
          transcript.addEventListener("click", () => showTranscript(firstCue));
          card.append(transcript);
        }
        const details = element("details", "fact-check-evidence");
        details.open = Boolean(query);
        details.append(element("summary", "", `查核分析與來源（${item.sources.length}）`));
        item.analysis.forEach((text) => {
          const paragraph = element("p");
          paragraph.append(highlighted(text));
          details.append(paragraph);
        });
        details.append(element("h5", "fact-check-label", "資料來源"));
        const sources = element("ol", "fact-check-sources");
        item.sources.forEach((source) => {
          const row = element("li");
          const link = element("a");
          link.href = source.url;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          link.append(highlighted(source.title), " ↗");
          const metadata = element("p", "source-meta");
          metadata.append(highlighted(`${source.publisher} · 來源日期 ${source.published_at ?? "未標示"}`));
          const evidence = element("p");
          evidence.append(highlighted(source.evidence));
          row.append(link, metadata, evidence);
          sources.append(row);
        });
        details.append(sources, element("h5", "fact-check-label", "查核限制"));
        const limitations = element("p", "fact-check-limitations");
        limitations.append(highlighted(item.limitations));
        details.append(limitations);
        card.append(details);
        fragment.append(card);
      });
      $("fact-check-content").replaceChildren(fragment);
    }
    function render() {
      query = search.value.trim().toLocaleLowerCase("zh-TW");
      selectedSpeaker = speakerFilter.value;
      $("clear-search").hidden = !search.value;
      const visibleCues = chronological.filter((cue) => matches(cue, [cue.text, cue.label, speakerName(speakerKey(cue), cue)]));
      const filterReview = (items) => items.filter((item) => {
        const cue = cueById.get(String(item.cue_id));
        const texts = "before" in item ? [item.before, item.after, item.evidence] : [item.suggestion];
        return matches(cue, [cue?.text, cue?.label, item.reason, ...texts]);
      });
      const visibleCorrections = filterReview(corrections);
      const visibleFlags = filterReview(flags);
      const visibleFactChecks = factChecks.filter((item) => {
        const cue = cueById.get(String(item.quotes[0]?.cue_id));
        return (verdictFilter.value === "__all__" || item.verdict === verdictFilter.value) && matches(cue, [
          item.id,
          data.roles[item.speaker]?.name,
          item.title,
          verdictLabels[item.verdict],
          item.summary,
          ...item.analysis,
          item.limitations,
          ...item.quotes.map((part) => part.text),
          ...item.sources.flatMap((source) => [source.title, source.publisher, source.evidence])
        ]);
      });
      const counts = {
        transcript: visibleCues.length,
        "fact-checks": visibleFactChecks.length,
        corrections: visibleCorrections.length,
        pending: visibleFlags.length
      };
      Object.entries(counts).forEach(([view, count]) => {
        $(`count-${view}`).textContent = formatNumber(count);
      });
      if (currentView === "transcript")
        renderTranscript(visibleCues);
      else if (currentView === "fact-checks")
        renderFactChecks(visibleFactChecks);
      else
        renderReview(currentView === "corrections" ? visibleCorrections : visibleFlags, currentView === "pending");
      const count = counts[currentView];
      const nouns = {
        transcript: "段發言",
        "fact-checks": "項事實查核",
        corrections: "筆校對紀錄",
        pending: "筆待確認項目"
      };
      const filtering = Boolean(query || selectedSpeaker !== "__all__" || currentView === "fact-checks" && verdictFilter.value !== "__all__");
      $("result-status").textContent = `${filtering ? "符合條件" : "共"} ${formatNumber(count)} ${nouns[currentView]}`;
      $("empty-state").hidden = count > 0;
      $("empty-title").textContent = filtering ? "找不到符合條件的內容" : currentView === "pending" ? "目前沒有待確認紀錄" : currentView === "corrections" ? "尚無校對紀錄" : currentView === "fact-checks" ? "尚未收錄事實查核" : "尚無逐字稿內容";
      $("empty-description").textContent = filtering ? "請更換關鍵字，或重設說話者與查核結論篩選。" : "未列出紀錄不代表全部內容已完成查證。";
      $("empty-reset").hidden = !filtering;
    }
    function switchView(view, focus = false) {
      currentView = view;
      if (view !== "fact-checks" && window.location.hash === "#fact-checks") {
        history.replaceState(null, "", window.location.pathname + window.location.search);
      }
      tabs.forEach(({ button, view: tabView }) => {
        const selected = tabView === view;
        button.setAttribute("aria-selected", String(selected));
        button.tabIndex = selected ? 0 : -1;
        $(`panel-${tabView}`).hidden = !selected;
        if (selected && focus)
          button.focus();
      });
      render();
    }
    function resetFilters() {
      search.value = "";
      speakerFilter.value = "__all__";
      verdictFilter.value = "__all__";
      render();
    }
    function chapterAt(seconds) {
      return chapterLeaves.find(({ chapter }) => chapter.start <= seconds && seconds < chapter.end);
    }
    function renderChapters(chapters, ancestors = [], path = []) {
      const list = element("ol", "chapter-list");
      chapters.forEach((chapter) => {
        const item = element("li");
        const names = [...path, chapter.title];
        const button = element("button", "chapter-button");
        button.type = "button";
        button.dataset.chapterId = chapter.id;
        button.setAttribute("aria-label", `從 ${time(chapter.start)} 播放：${names.join("／")}`);
        button.append(element("span", "chapter-label", chapter.children ? "從此處開始" : chapter.title), element("span", "chapter-time", time(chapter.start)));
        button.addEventListener("click", () => {
          const cue = cueById.get(String(chapter.start_cue_id));
          if (cue)
            showTranscript(cue, true);
        });
        if (chapter.children) {
          const group = element("details", "chapter-group");
          group.open = ancestors.length === 0;
          group.dataset.chapterGroup = chapter.id;
          const summary = element("summary", "", chapter.title);
          button.classList.add("chapter-start");
          group.append(summary, button, renderChapters(chapter.children, [...ancestors, group], names));
          chapterGroups.push(group);
          item.append(group);
        } else {
          chapterLeaves.push({ chapter, button, ancestors });
          item.append(button);
        }
        list.append(item);
      });
      return list;
    }
    function revealHash() {
      if (window.location.hash === "#fact-checks") {
        switchView("fact-checks");
        $("record").scrollIntoView({ block: "start", behavior: "instant" });
        return;
      }
      const match = /^#cue-(\d+)$/.exec(window.location.hash);
      const clock = /^#time-(\d+(?:\.\d+)?)$/.exec(window.location.hash);
      const seconds = clock ? Number(clock[1]) : null;
      const validTime = seconds !== null && seconds >= 0 && seconds <= duration;
      const cue = match?.[1] !== undefined ? cueById.get(match[1]) : validTime ? chronological.find((item) => item.end > seconds) || chronological[chronological.length - 1] : null;
      if (!cue)
        return;
      search.value = "";
      speakerFilter.value = "__all__";
      verdictFilter.value = "__all__";
      switchView("transcript");
      seek(validTime ? { ...cue, start: seconds } : cue, false);
      requestAnimationFrame(() => {
        cueElements.get(String(cue.id))?.scrollIntoView({ block: "center", behavior: "instant" });
      });
    }
    function updatePlayback() {
      const now = pendingSeek?.seconds ?? player?.getCurrentTime() ?? 0;
      const state = player?.getPlayerState();
      const playing = state === 1;
      let active = null;
      for (const cue of chronological) {
        if (cue.start > now)
          break;
        if (cue.end > now)
          active = cue;
      }
      const nextId = active ? String(active.id) : null;
      if (nextId !== activeId) {
        const previous = activeId === null ? undefined : cueElements.get(activeId);
        previous?.classList.remove("is-active");
        previous?.removeAttribute("aria-current");
        activeId = nextId;
        const current = activeId === null ? undefined : cueElements.get(activeId);
        current?.classList.add("is-active");
        if (current)
          current.setAttribute("aria-current", "true");
      }
      if (player && !mediaFailed) {
        const label = playing ? "播放中" : state === 3 ? "載入中" : state === -1 || state === 5 ? "尚未播放" : "已暫停";
        $("playback-status").textContent = autoplayBlocked ? "請按 YouTube 播放按鈕開始播放" : `${label} ${time(now)} / ${time(duration)}`;
      }
      const currentChapter = chapterAt(now);
      chapterLeaves.forEach((entry) => {
        if (entry === currentChapter)
          entry.button.setAttribute("aria-current", "true");
        else
          entry.button.removeAttribute("aria-current");
      });
      chapterGroups.forEach((group) => {
        group.classList.toggle("is-active-section", currentChapter?.ancestors.includes(group) ?? false);
      });
      if (followPlayback.checked && playing && currentView === "transcript" && activeId !== lastFollowedId) {
        const current = activeId === null ? undefined : cueElements.get(activeId);
        if (current) {
          current.scrollIntoView({
            block: "center",
            behavior: reducedMotion.matches ? "instant" : "smooth"
          });
          lastFollowedId = activeId;
        }
      }
    }
    function mediaFailure(code) {
      mediaFailed = true;
      const restricted = code === 101 || code === 150;
      const message = $("media-error");
      message.hidden = false;
      message.textContent = restricted ? "YouTube 限制此影片的嵌入播放。請使用下方連結在 YouTube 開啟。逐字稿仍可閱讀與搜尋。" : "無法載入 YouTube 影音。請確認網路連線，或使用下方連結在 YouTube 開啟。逐字稿仍可閱讀與搜尋。";
      $("playback-status").textContent = restricted ? "請在 YouTube 開啟影片" : "YouTube 無法載入；文字功能仍可使用";
    }
    function loadYouTubePlayer() {
      const youtube = window;
      if (window.location.protocol === "http:" || window.location.protocol === "https:") {
        const source = new URL(video.src);
        source.searchParams.set("origin", window.location.origin);
        video.src = source.href;
      }
      const readyTimeout = window.setTimeout(mediaFailure, 15000);
      const failure = (code) => {
        window.clearTimeout(readyTimeout);
        mediaFailure(code);
      };
      const initialize = () => {
        const api = youtube.YT;
        if (!api)
          return;
        new api.Player(video, {
          events: {
            onReady: ({ target }) => {
              window.clearTimeout(readyTimeout);
              player = target;
              mediaFailed = false;
              $("media-error").hidden = true;
              applyPendingSeek();
              updatePlayback();
              window.setInterval(updatePlayback, 500);
            },
            onStateChange: () => {
              if (player?.getPlayerState() === 1) {
                mediaFailed = false;
                autoplayBlocked = false;
                $("media-error").hidden = true;
              }
              updatePlayback();
            },
            onError: ({ data }) => failure(data),
            onAutoplayBlocked: () => {
              autoplayBlocked = true;
              updatePlayback();
            }
          }
        });
      };
      if (youtube.YT?.Player)
        initialize();
      else {
        youtube.onYouTubeIframeAPIReady = initialize;
        const script = element("script");
        script.src = "https://www.youtube.com/iframe_api";
        script.async = true;
        script.addEventListener("error", () => failure());
        document.head.append(script);
      }
    }
    $("stat-duration").textContent = time(duration);
    $("stat-cues").textContent = formatNumber(cues.length);
    $("stat-speakers").textContent = formatNumber(knownSpeakers.length);
    $("stat-corrections").textContent = formatNumber(corrections.length);
    $("stat-pending").textContent = formatNumber(flags.length);
    $("model-info").textContent = data.metadata.model || "未提供";
    const stages = {
      diarize: "說話者分離",
      align: "時間對齊",
      transcribe: "語音辨識"
    };
    const stage = data.metadata.stage;
    $("stage-info").textContent = (stage === null ? undefined : stages[stage]) || stage || "未提供";
    $("method-info").textContent = textValue(data.review.method) || "未提供；請逐項檢視校對依據。";
    $("hash-info").textContent = textValue(data.review.source_sha256) || "未提供";
    [...speakers.filter((speaker) => speaker !== "UNKNOWN"), "UNKNOWN"].forEach((speaker) => {
      const cue = cues.find((item) => speakerKey(item) === speaker);
      const option = element("option", "", speakerName(speaker, cue));
      option.value = speaker;
      speakerFilter.append(option);
    });
    const chapters = data.chapters?.items ?? [];
    if (chapters.length)
      $("chapters").append(renderChapters(chapters));
    else
      $("chapters").append(element("p", "index-note", "尚無章節資料"));
    function syncReadingTools() {
      if (!compactTools.matches && document.activeElement === toolsSummary) {
        search.focus({ preventScroll: true });
      }
      readingTools.open = !compactTools.matches || readingTools.contains(document.activeElement);
    }
    syncReadingTools();
    compactTools.addEventListener("change", syncReadingTools);
    search.addEventListener("input", render);
    speakerFilter.addEventListener("change", render);
    verdictFilter.addEventListener("change", render);
    requiredElement("clear-search", HTMLButtonElement).addEventListener("click", () => {
      search.value = "";
      render();
      search.focus();
    });
    requiredElement("reset-filters", HTMLButtonElement).addEventListener("click", resetFilters);
    requiredElement("empty-reset", HTMLButtonElement).addEventListener("click", resetFilters);
    tabs.forEach(({ button, view }, index) => {
      button.addEventListener("click", () => switchView(view));
      button.addEventListener("keydown", (event) => {
        let next;
        if (event.key === "ArrowRight")
          next = (index + 1) % tabs.length;
        if (event.key === "ArrowLeft")
          next = (index - 1 + tabs.length) % tabs.length;
        if (event.key === "Home")
          next = 0;
        if (event.key === "End")
          next = tabs.length - 1;
        if (next !== undefined) {
          event.preventDefault();
          const nextTab = tabs[next];
          if (nextTab)
            switchView(nextTab.view, true);
        }
      });
    });
    followPlayback.addEventListener("change", () => {
      lastFollowedId = null;
      updatePlayback();
    });
    window.addEventListener("hashchange", revealHash);
    renderFactCheckOverview();
    render();
    revealHash();
    loadYouTubePlayer();
  })();
})();
