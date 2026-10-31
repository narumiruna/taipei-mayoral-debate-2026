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
    const cueById = new Map(cues.map((cue) => [String(cue.id), cue]));
    const chronological = [...cues].sort((a, b) => a.start - b.start);
    const speakerKey = (cue) => cue?.speaker || "UNKNOWN";
    const speakers = [...new Set(cues.map(speakerKey))];
    const knownSpeakers = speakers.filter((speaker) => speaker !== "UNKNOWN");
    const speakerIndex = new Map(knownSpeakers.map((speaker, index) => [speaker, index]));
    const correctedIds = new Set(corrections.map((item) => String(item.cue_id)));
    const pendingIds = new Set(flags.map((item) => String(item.cue_id)));
    const video = requiredElement("debate-video", HTMLVideoElement);
    const search = requiredElement("search", HTMLInputElement);
    const speakerFilter = requiredElement("speaker-filter", HTMLSelectElement);
    const followPlayback = requiredElement("follow-playback", HTMLInputElement);
    const tabs = [...document.querySelectorAll('[role="tab"]')].map((button) => {
      if (!(button instanceof HTMLButtonElement)) {
        throw new Error("Each tab must be a button");
      }
      const view = button.dataset.view;
      if (view !== "transcript" && view !== "corrections" && view !== "pending") {
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
    let pendingSeek = null;
    let lastFollowedId = null;
    let cueElements = new Map;
    const chapterButtons = [];
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
      const role = data.roles[speaker];
      if (role)
        return [role.role, role.name].filter(Boolean).join("／") || "說話者未確認";
      return cue?.label || (speaker === "UNKNOWN" ? "說話者未確認" : `${speaker}（角色未確認）`);
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
    function seek(cue, play = false) {
      const seconds = Number(cue.start) || 0;
      pendingSeek = seconds;
      try {
        video.currentTime = seconds;
        if (video.readyState > 0)
          pendingSeek = null;
      } catch {}
      setTarget(String(cue.id));
      try {
        const original = cueById.get(String(cue.id));
        const hash = original && Number(original.start) === seconds ? `#cue-${cue.id}` : `#time-${seconds}`;
        history.replaceState(null, "", hash);
      } catch {}
      if (play) {
        const promise = video.play();
        if (promise)
          promise.catch(() => {
            $("playback-status").textContent = "請使用播放器播放；若無法載入，請檢查影片檔案。";
          });
      }
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
          const corrected = correctedIds.has(id) || Boolean(cue.correction_id);
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
            ["before", "辨識原文", item.before],
            ["after", "修訂文字", item.after]
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
      const counts = {
        transcript: visibleCues.length,
        corrections: visibleCorrections.length,
        pending: visibleFlags.length
      };
      Object.entries(counts).forEach(([view, count]) => {
        $(`count-${view}`).textContent = formatNumber(count);
      });
      if (currentView === "transcript")
        renderTranscript(visibleCues);
      else
        renderReview(currentView === "corrections" ? visibleCorrections : visibleFlags, currentView === "pending");
      const count = counts[currentView];
      const noun = currentView === "transcript" ? "段發言" : currentView === "corrections" ? "筆校對紀錄" : "筆待確認項目";
      $("result-status").textContent = `${query || selectedSpeaker !== "__all__" ? "符合條件" : "共"} ${formatNumber(count)} ${noun}`;
      $("empty-state").hidden = count > 0;
      const filtering = Boolean(query || selectedSpeaker !== "__all__");
      $("empty-title").textContent = filtering ? "找不到符合條件的內容" : currentView === "pending" ? "目前沒有待確認紀錄" : currentView === "corrections" ? "尚無校對紀錄" : "尚無逐字稿內容";
      $("empty-description").textContent = filtering ? "請更換關鍵字，或重設說話者篩選。" : "未列出紀錄不代表全部內容已完成查證。";
      $("empty-reset").hidden = !filtering;
    }
    function switchView(view, focus = false) {
      currentView = view;
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
      render();
    }
    function revealHash() {
      const match = /^#cue-(\d+)$/.exec(window.location.hash);
      const clock = /^#time-(\d+(?:\.\d+)?)$/.exec(window.location.hash);
      const seconds = clock ? Number(clock[1]) : null;
      const validTime = seconds !== null && seconds >= 0 && seconds <= duration;
      const cue = match?.[1] !== undefined ? cueById.get(match[1]) : validTime ? chronological.find((item) => item.end > seconds) || chronological[chronological.length - 1] : null;
      if (!cue)
        return;
      search.value = "";
      speakerFilter.value = "__all__";
      switchView("transcript");
      seek(validTime ? { ...cue, start: seconds } : cue, false);
      requestAnimationFrame(() => {
        cueElements.get(String(cue.id))?.scrollIntoView({ block: "center", behavior: "instant" });
      });
    }
    function updatePlayback() {
      const now = video.currentTime || 0;
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
      if (!video.error)
        $("playback-status").textContent = `${video.paused ? "已暫停" : "播放中"} ${time(now)} / ${time(duration)}`;
      const chapter = Math.floor(now / 600);
      chapterButtons.forEach((button, index) => {
        if (index === chapter)
          button.setAttribute("aria-current", "true");
        else
          button.removeAttribute("aria-current");
      });
      if (followPlayback.checked && !video.paused && currentView === "transcript" && activeId !== lastFollowedId) {
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
    function mediaFailure() {
      $("media-error").hidden = false;
      $("playback-status").textContent = "影音無法載入；文字功能仍可使用";
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
    for (let start = 0;start < duration; start += 600) {
      const cue = chronological.find((item) => item.end > start) || chronological[chronological.length - 1];
      if (!cue)
        break;
      const button = element("button", "chapter-button", time(start));
      button.type = "button";
      button.setAttribute("aria-label", `播放 ${time(start)} 起的影音`);
      button.addEventListener("click", () => {
        seek({ ...cue, start }, true);
      });
      $("chapters").append(button);
      chapterButtons.push(button);
    }
    if (!chapterButtons.length)
      $("chapters").append(element("p", "index-note", "尚無時間索引"));
    search.addEventListener("input", render);
    speakerFilter.addEventListener("change", render);
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
    ["timeupdate", "play", "pause", "seeked"].forEach((event) => {
      video.addEventListener(event, updatePlayback);
    });
    video.addEventListener("loadedmetadata", () => {
      $("media-error").hidden = true;
      if (pendingSeek !== null) {
        video.currentTime = pendingSeek;
        pendingSeek = null;
      }
    });
    video.addEventListener("error", mediaFailure);
    const source = video.querySelector("source");
    if (!source)
      throw new Error("Required video source is missing");
    source.addEventListener("error", mediaFailure);
    if (video.error)
      mediaFailure();
    followPlayback.addEventListener("change", () => {
      lastFollowedId = null;
      updatePlayback();
    });
    window.addEventListener("hashchange", revealHash);
    render();
    revealHash();
  })();
})();
