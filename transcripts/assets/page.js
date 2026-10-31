/* Generated from web/page.ts. Run bun run build to update. */ "use strict";
(() => {

  // web/responsiveness.ts
  var dimensions = [
    { key: "directness", name: "直接性", weight: 40 },
    { key: "completeness", name: "完整性", weight: 25 },
    { key: "specificity", name: "具體性", weight: 20 },
    { key: "consistency", name: "一致性", weight: 15 }
  ];
  var responseClasses = [
    { key: "direct", name: "直接完整回答", description: "明確回答核心事項與全部適用子問題。" },
    { key: "partial", name: "部分回答", description: "回答部分子題，或說明尚不能確定立場的原因。" },
    {
      key: "evasive",
      name: "迴避回答",
      description: "轉移議題或使用模糊說法，沒有實質回應所問事項。"
    },
    { key: "refusal", name: "拒答", description: "明確表示不回答；不與模糊或缺漏的回答混為一類。" },
    {
      key: "undetermined",
      name: "無法判定",
      description: "問題、回答或上下文不足；排除於比率分母。"
    }
  ];
  var exampleDistributions = [
    { direct: 12, partial: 4, evasive: 3, refusal: 1, undetermined: 1 },
    { direct: 4, partial: 5, evasive: 8, refusal: 3, undetermined: 1 }
  ];
  function responseMetrics(counts) {
    const assessable = counts.direct + counts.partial + counts.evasive + counts.refusal;
    const rate = (count) => assessable ? count / assessable * 100 : null;
    return {
      assessable,
      direct: rate(counts.direct),
      partial: rate(counts.partial),
      evasive: rate(counts.evasive)
    };
  }
  function qualityTotal(scores) {
    if (scores.some((score) => score === null))
      return null;
    return scores.reduce((sum, score, index) => {
      const dimension = dimensions[index];
      return sum + (score ?? 0) * ((dimension?.weight ?? 0) / 5);
    }, 0);
  }
  var sourceHash = "bcc1e56e8d98ed44e2c48d219314380627d9b3e02a76f3f6433645328899aae2";
  var questionRanges = [
    {
      title: "四年後，市民日常生活會如何改變？",
      question: [747, 764],
      subquestions: [
        "通勤到內湖或北市科，有何新選擇？是否更方便、安全？",
        "送孩子上學、托育或上幼兒園，如何更放心？",
        "照顧家中長輩的家庭，可獲得哪些實際支援？",
        "假日有哪些新的休閒、散步與休息空間？"
      ],
      answers: [
        {
          range: [766, 799],
          speaker: "SPEAKER_04",
          note: "末句未完，下一段 800 混有主持人發言。本對照保留原分段，不自行拼接；引用完整句前請回聽。"
        },
        { range: [801, 832], speaker: "SPEAKER_03", note: "" }
      ]
    },
    {
      title: "如何加速都更，兼顧高風險住宅安全與住戶權益？",
      question: [835, 851],
      subquestions: [
        "都更能否加速？目前最難突破的障礙是什麼？",
        "國際經驗中的主動清查、資訊公開與補強，有何可借鏡之處？",
        "高風險住戶長期無法取得共識，市府如何介入並兼顧權益？",
        "面對地震與極端氣候，首都居住韌性的願景是什麼？"
      ],
      answers: [
        { range: [853, 885], speaker: "SPEAKER_03", note: "" },
        { range: [887, 917], speaker: "SPEAKER_04", note: "" }
      ]
    }
  ];
  function alignedQuestions(data) {
    if (data.review.source_sha256 !== sourceHash)
      return [];
    const byId = new Map(data.cues.map((cue) => [cue.id, cue]));
    const range = ([first, last]) => {
      const cues = [];
      for (let id = first;id <= last; id++) {
        const cue = byId.get(id);
        if (!cue)
          return [];
        cues.push(cue);
      }
      return cues;
    };
    return questionRanges.flatMap((item) => {
      const question = range(item.question);
      const answers = item.answers.map((answer) => ({
        cues: range(answer.range),
        note: answer.note,
        speaker: answer.speaker
      }));
      if (!question.length || answers.some((answer) => !answer.cues.length || answer.cues.some((c) => c.speaker !== answer.speaker)))
        return [];
      return [{ title: item.title, question, answers, subquestions: item.subquestions }];
    });
  }
  function node(tag, className, text) {
    const result = document.createElement(tag);
    result.className = className;
    if (text !== undefined)
      result.textContent = String(text);
    return result;
  }
  function required(id, type) {
    const result = document.getElementById(id);
    if (!(result instanceof type))
      throw new Error(`Missing assessment element #${id}`);
    return result;
  }
  function mountResponsiveness(data, tools) {
    const questions = alignedQuestions(data);
    const selector = required("assessment-question", HTMLSelectElement);
    const evidence = required("assessment-evidence", HTMLElement);
    required("assessment-aligned-count", HTMLElement).textContent = String(questions.length);
    required("assessment-alignment-status", HTMLElement).textContent = questions.length ? `已對齊 ${questions.length} 題共同提問、${questions.length * 2} 段回答。皆為首次回答，每段限時三分鐘；尚未分類或評分，不代表完整場次。` : "此逐字稿尚無已對齊的共同提問。沒有評分資料時，不顯示 0 分或 0% 回答率。";
    required("assessment-question-label", HTMLElement).hidden = !questions.length;
    selector.hidden = !questions.length;
    function sourceDetails(cues) {
      const details = node("details", "evidence-source");
      const ids = new Set(cues.map((cue) => cue.id));
      const flags = data.review.flags.filter((flag) => ids.has(flag.cue_id));
      const unknown = cues.some((cue) => cue.speaker === "UNKNOWN");
      details.append(node("summary", "", `原文與校對提示 · ${cues.length} 段／${flags.length} 項待確認`));
      const quote = node("blockquote", "evidence-quote");
      cues.forEach((cue) => {
        const line = node("p", "");
        line.append(tools.timestampButton(cue), document.createTextNode(cue.text));
        quote.append(line);
      });
      details.append(quote);
      if (unknown)
        details.append(node("p", "assessment-caution", "含說話者未確認的片段，請回聽確認。"));
      if (flags.length) {
        const list = node("ul", "evidence-flags");
        flags.forEach((flag) => {
          const cue = cues.find((item) => item.id === flag.cue_id);
          const item = node("li", "");
          if (cue)
            item.append(tools.timestampButton(cue));
          item.append(document.createTextNode(flag.reason));
          list.append(item);
        });
        details.append(list);
      }
      return details;
    }
    function showQuestion() {
      evidence.replaceChildren();
      const question = questions[Number(selector.value)];
      if (!question)
        return;
      const prompt = node("article", "question-card");
      const header = node("div", "evidence-header");
      const first = question.question[0];
      if (first)
        header.append(tools.speakerBadge(first), tools.timestampButton(first));
      const subquestions = node("ol", "subquestions");
      question.subquestions.forEach((text) => {
        subquestions.append(node("li", "", text));
      });
      prompt.append(header, node("p", "assessment-caption", "子問題整理（非逐字引文）；完整措辭以原文為準。"), subquestions, sourceDetails(question.question));
      evidence.append(prompt);
      question.answers.forEach((answer) => {
        const first = answer.cues[0];
        if (!first)
          return;
        const card = node("article", "answer-card");
        const header = node("div", "evidence-header");
        header.append(tools.speakerBadge(first), tools.timestampButton(first));
        const open = node("button", "evidence-link", "閱讀逐字稿 →");
        open.type = "button";
        open.addEventListener("click", () => tools.openTranscript(first));
        header.append(open);
        card.append(header, node("p", "assessment-caption", "未分類 · 四維分數、總分與迴避策略均未評估"));
        if (answer.note)
          card.append(node("p", "assessment-caution", answer.note));
        card.append(sourceDetails(answer.cues));
        evidence.append(card);
      });
    }
    questions.forEach((question, index) => {
      const option = node("option", "", question.title);
      option.value = String(index);
      selector.append(option);
    });
    selector.addEventListener("change", showQuestion);
    showQuestion();
    const classificationList = required("assessment-classes", HTMLElement);
    responseClasses.forEach((item) => {
      const entry = node("div", "classification-item");
      entry.append(node("dt", `response-label response-${item.key}`, item.name), node("dd", "", item.description));
      classificationList.append(entry);
    });
    const distribution = required("example-distribution", HTMLElement);
    responseClasses.forEach((item) => {
      const row = node("tr", "");
      const label = node("th", `response-label response-${item.key}`, item.name);
      label.scope = "row";
      row.append(label);
      exampleDistributions.forEach((counts) => {
        const cell = node("td", "");
        const bar = node("span", `distribution-bar response-${item.key}`);
        bar.style.width = `${counts[item.key] / 21 * 100}%`;
        bar.setAttribute("aria-hidden", "true");
        cell.append(bar, node("span", "distribution-count", counts[item.key]));
        row.append(cell);
      });
      distribution.append(row);
    });
    const rateRows = required("example-rates", HTMLElement);
    const percent = (value) => value === null ? "—" : `${value.toFixed(0)}%`;
    for (const [index, counts] of exampleDistributions.entries()) {
      const rates = responseMetrics(counts);
      const row = node("tr", "");
      const label = node("th", "", `示例 ${index === 0 ? "A" : "B"}`);
      label.scope = "row";
      row.append(label, node("td", "", percent(rates.direct)), node("td", "", percent(rates.partial)), node("td", "", percent(rates.evasive)));
      rateRows.append(row);
    }
    const controls = required("quality-controls", HTMLElement);
    const inputs = dimensions.map((dimension) => {
      const label = node("label", "quality-control");
      const name = node("span", "", `${dimension.name} · ${dimension.weight}%`);
      const input = node("select", "");
      input.id = `score-${dimension.key}`;
      label.htmlFor = input.id;
      const empty = node("option", "", "未評估");
      empty.value = "";
      input.append(empty);
      for (let score = 0;score <= 5; score++) {
        const option = node("option", "", `${score} 分`);
        option.value = String(score);
        input.append(option);
      }
      label.append(name, input);
      controls.append(label);
      return input;
    });
    function updateScore() {
      const scores = inputs.map((input) => input.value === "" ? null : Number(input.value));
      const total = qualityTotal(scores);
      required("quality-total", HTMLOutputElement).value = total === null ? "— / 100" : `${total} / 100`;
      required("quality-status", HTMLElement).textContent = total === null ? "四項皆須評估才計算總分。未評估不等於 0 分，也不重新分配權重。" : "此數字僅為量表試算，不會儲存，也不列入本場候選人統計。";
    }
    inputs.forEach((input) => {
      input.addEventListener("change", updateScore);
    });
    required("reset-quality", HTMLButtonElement).addEventListener("click", () => {
      inputs.forEach((input) => {
        input.value = "";
      });
      updateScore();
    });
    updateScore();
  }

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
    const video = requiredElement("debate-video", HTMLIFrameElement);
    const videoLink = requiredElement("video-link", HTMLAnchorElement);
    const videoId = new URL(video.src).pathname.split("/").pop() || "";
    const search = requiredElement("search", HTMLInputElement);
    const speakerFilter = requiredElement("speaker-filter", HTMLSelectElement);
    const followPlayback = requiredElement("follow-playback", HTMLInputElement);
    const tabs = [...document.querySelectorAll('[role="tab"]')].map((button) => {
      if (!(button instanceof HTMLButtonElement)) {
        throw new Error("Each tab must be a button");
      }
      const view = button.dataset.view;
      if (view !== "transcript" && view !== "corrections" && view !== "pending" && view !== "responsiveness") {
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
      if (currentView === "responsiveness") {
        $("empty-state").hidden = true;
        return;
      }
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
      const assessment = view === "responsiveness";
      $("reader-filters").hidden = assessment;
      $("reader-results").hidden = assessment;
      $("reader-end-note").hidden = assessment;
      $("record-heading").textContent = assessment ? "問答回應品質評估" : "發言紀錄";
      $("record-heading-note").textContent = assessment ? "分類、品質與事實分開看" : "依影音時間排序";
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
    function navigateTab(view, focus = false) {
      switchView(view, focus);
      const hash = view === "responsiveness" ? "#responsiveness" : window.location.hash === "#responsiveness" ? "#record" : null;
      if (!hash)
        return;
      try {
        history.replaceState(null, "", hash);
      } catch {}
    }
    function resetFilters() {
      search.value = "";
      speakerFilter.value = "__all__";
      render();
    }
    function revealHash() {
      if (!window.location.hash || window.location.hash === "#responsiveness" || window.location.hash === "#record") {
        switchView(window.location.hash === "#responsiveness" ? "responsiveness" : "transcript");
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
      const chapter = Math.floor(now / 600);
      chapterButtons.forEach((button, index) => {
        if (index === chapter)
          button.setAttribute("aria-current", "true");
        else
          button.removeAttribute("aria-current");
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
    mountResponsiveness(data, {
      speakerBadge,
      timestampButton,
      openTranscript: (cue) => {
        resetFilters();
        switchView("transcript");
        seek(cue);
        requestAnimationFrame(() => {
          $("panel-transcript").focus({ preventScroll: true });
          cueElements.get(String(cue.id))?.scrollIntoView({ block: "center", behavior: "instant" });
        });
      }
    });
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
      button.addEventListener("click", () => navigateTab(view));
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
            navigateTab(nextTab.view, true);
        }
      });
    });
    followPlayback.addEventListener("change", () => {
      lastFollowedId = null;
      updatePlayback();
    });
    document.querySelectorAll('a[href="#record"]').forEach((link) => {
      link.addEventListener("click", () => switchView("transcript"));
    });
    window.addEventListener("hashchange", revealHash);
    render();
    revealHash();
    loadYouTubePlayer();
  })();
})();
