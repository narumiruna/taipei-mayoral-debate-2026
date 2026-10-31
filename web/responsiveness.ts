import type { Cue, TranscriptData } from "./transcript";

export type ResponseClass = "direct" | "partial" | "evasive" | "refusal" | "undetermined";
export type Score = 0 | 1 | 2 | 3 | 4 | 5;
export type QualityScores = [Score | null, Score | null, Score | null, Score | null];

export const dimensions = [
  { key: "directness", name: "直接性", weight: 40 },
  { key: "completeness", name: "完整性", weight: 25 },
  { key: "specificity", name: "具體性", weight: 20 },
  { key: "consistency", name: "一致性", weight: 15 },
] as const;

export const responseClasses: { key: ResponseClass; name: string; description: string }[] = [
  { key: "direct", name: "直接完整回答", description: "明確回答核心事項與全部適用子問題。" },
  { key: "partial", name: "部分回答", description: "回答部分子題，或說明尚不能確定立場的原因。" },
  {
    key: "evasive",
    name: "迴避回答",
    description: "轉移議題或使用模糊說法，沒有實質回應所問事項。",
  },
  { key: "refusal", name: "拒答", description: "明確表示不回答；不與模糊或缺漏的回答混為一類。" },
  {
    key: "undetermined",
    name: "無法判定",
    description: "問題、回答或上下文不足；排除於比率分母。",
  },
];

// Hypothetical counts only. Each example has 20 assessable questions and one unknown.
export const exampleDistributions: Record<ResponseClass, number>[] = [
  { direct: 12, partial: 4, evasive: 3, refusal: 1, undetermined: 1 },
  { direct: 4, partial: 5, evasive: 8, refusal: 3, undetermined: 1 },
];

export function responseMetrics(counts: Record<ResponseClass, number>): {
  assessable: number;
  direct: number | null;
  partial: number | null;
  evasive: number | null;
} {
  const assessable = counts.direct + counts.partial + counts.evasive + counts.refusal;
  const rate = (count: number): number | null => (assessable ? (count / assessable) * 100 : null);
  return {
    assessable,
    direct: rate(counts.direct),
    partial: rate(counts.partial),
    evasive: rate(counts.evasive),
  };
}

export function qualityTotal(scores: QualityScores): number | null {
  if (scores.some((score) => score === null)) return null;
  return scores.reduce<number>((sum, score, index) => {
    const dimension = dimensions[index];
    return sum + (score ?? 0) * ((dimension?.weight ?? 0) / 5);
  }, 0);
}

interface QuestionRange {
  title: string;
  question: [number, number];
  answers: { range: [number, number]; speaker: string; note: string }[];
  subquestions: string[];
}

export interface AlignedQuestion {
  title: string;
  question: Cue[];
  answers: { cues: Cue[]; note: string }[];
  subquestions: string[];
}

// These are source-specific alignment records, not classifications or ratings.
const sourceHash = "bcc1e56e8d98ed44e2c48d219314380627d9b3e02a76f3f6433645328899aae2";
const questionRanges: QuestionRange[] = [
  {
    title: "四年後，市民日常生活會如何改變？",
    question: [747, 764],
    subquestions: [
      "通勤到內湖或北市科，有何新選擇？是否更方便、安全？",
      "送孩子上學、托育或上幼兒園，如何更放心？",
      "照顧家中長輩的家庭，可獲得哪些實際支援？",
      "假日有哪些新的休閒、散步與休息空間？",
    ],
    answers: [
      {
        range: [766, 799],
        speaker: "SPEAKER_04",
        note: "末句未完，下一段 800 混有主持人發言。本對照保留原分段，不自行拼接；引用完整句前請回聽。",
      },
      { range: [801, 832], speaker: "SPEAKER_03", note: "" },
    ],
  },
  {
    title: "如何加速都更，兼顧高風險住宅安全與住戶權益？",
    question: [835, 851],
    subquestions: [
      "都更能否加速？目前最難突破的障礙是什麼？",
      "國際經驗中的主動清查、資訊公開與補強，有何可借鏡之處？",
      "高風險住戶長期無法取得共識，市府如何介入並兼顧權益？",
      "面對地震與極端氣候，首都居住韌性的願景是什麼？",
    ],
    answers: [
      { range: [853, 885], speaker: "SPEAKER_03", note: "" },
      { range: [887, 917], speaker: "SPEAKER_04", note: "" },
    ],
  },
];

export function alignedQuestions(data: TranscriptData): AlignedQuestion[] {
  if (data.review.source_sha256 !== sourceHash) return [];
  const byId = new Map(data.cues.map((cue) => [cue.id, cue]));
  const range = ([first, last]: [number, number]): Cue[] => {
    const cues: Cue[] = [];
    for (let id = first; id <= last; id++) {
      const cue = byId.get(id);
      if (!cue) return [];
      cues.push(cue);
    }
    return cues;
  };
  return questionRanges.flatMap((item) => {
    const question = range(item.question);
    const answers = item.answers.map((answer) => ({
      cues: range(answer.range),
      note: answer.note,
      speaker: answer.speaker,
    }));
    if (
      !question.length ||
      answers.some(
        (answer) => !answer.cues.length || answer.cues.some((c) => c.speaker !== answer.speaker),
      )
    )
      return [];
    return [{ title: item.title, question, answers, subquestions: item.subquestions }];
  });
}

function node<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className: string,
  text?: string | number,
): HTMLElementTagNameMap[K] {
  const result = document.createElement(tag);
  result.className = className;
  if (text !== undefined) result.textContent = String(text);
  return result;
}

function required<T extends HTMLElement>(id: string, type: new () => T): T {
  const result = document.getElementById(id);
  if (!(result instanceof type)) throw new Error(`Missing assessment element #${id}`);
  return result;
}

interface EvidenceTools {
  speakerBadge: (cue: Cue) => HTMLElement;
  timestampButton: (cue: Cue) => HTMLButtonElement;
  openTranscript: (cue: Cue) => void;
}

export function mountResponsiveness(data: TranscriptData, tools: EvidenceTools): void {
  const questions = alignedQuestions(data);
  const selector = required("assessment-question", HTMLSelectElement);
  const evidence = required("assessment-evidence", HTMLElement);
  required("assessment-aligned-count", HTMLElement).textContent = String(questions.length);
  required("assessment-alignment-status", HTMLElement).textContent = questions.length
    ? `已對齊 ${questions.length} 題共同提問、${questions.length * 2} 段回答。皆為首次回答，每段限時三分鐘；尚未分類或評分，不代表完整場次。`
    : "此逐字稿尚無已對齊的共同提問。沒有評分資料時，不顯示 0 分或 0% 回答率。";
  required("assessment-question-label", HTMLElement).hidden = !questions.length;
  selector.hidden = !questions.length;

  function sourceDetails(cues: Cue[]): HTMLDetailsElement {
    const details = node("details", "evidence-source");
    const ids = new Set(cues.map((cue) => cue.id));
    const flags = data.review.flags.filter((flag) => ids.has(flag.cue_id));
    const unknown = cues.some((cue) => cue.speaker === "UNKNOWN");
    details.append(
      node("summary", "", `原文與校對提示 · ${cues.length} 段／${flags.length} 項待確認`),
    );
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
        if (cue) item.append(tools.timestampButton(cue));
        item.append(document.createTextNode(flag.reason));
        list.append(item);
      });
      details.append(list);
    }
    return details;
  }

  function showQuestion(): void {
    evidence.replaceChildren();
    const question = questions[Number(selector.value)];
    if (!question) return;
    const prompt = node("article", "question-card");
    const header = node("div", "evidence-header");
    const first = question.question[0];
    if (first) header.append(tools.speakerBadge(first), tools.timestampButton(first));
    const subquestions = node("ol", "subquestions");
    question.subquestions.forEach((text) => {
      subquestions.append(node("li", "", text));
    });
    prompt.append(
      header,
      node("p", "assessment-caption", "子問題整理（非逐字引文）；完整措辭以原文為準。"),
      subquestions,
      sourceDetails(question.question),
    );
    evidence.append(prompt);
    question.answers.forEach((answer) => {
      const first = answer.cues[0];
      if (!first) return;
      const card = node("article", "answer-card");
      const header = node("div", "evidence-header");
      header.append(tools.speakerBadge(first), tools.timestampButton(first));
      const open = node("button", "evidence-link", "閱讀逐字稿 →");
      open.type = "button";
      open.addEventListener("click", () => tools.openTranscript(first));
      header.append(open);
      card.append(
        header,
        node("p", "assessment-caption", "未分類 · 四維分數、總分與迴避策略均未評估"),
      );
      if (answer.note) card.append(node("p", "assessment-caution", answer.note));
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
    entry.append(
      node("dt", `response-label response-${item.key}`, item.name),
      node("dd", "", item.description),
    );
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
      bar.style.width = `${(counts[item.key] / 21) * 100}%`;
      bar.setAttribute("aria-hidden", "true");
      cell.append(bar, node("span", "distribution-count", counts[item.key]));
      row.append(cell);
    });
    distribution.append(row);
  });
  const rateRows = required("example-rates", HTMLElement);
  const percent = (value: number | null): string => (value === null ? "—" : `${value.toFixed(0)}%`);
  for (const [index, counts] of exampleDistributions.entries()) {
    const rates = responseMetrics(counts);
    const row = node("tr", "");
    const label = node("th", "", `示例 ${index === 0 ? "A" : "B"}`);
    label.scope = "row";
    row.append(
      label,
      node("td", "", percent(rates.direct)),
      node("td", "", percent(rates.partial)),
      node("td", "", percent(rates.evasive)),
    );
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
    for (let score = 0; score <= 5; score++) {
      const option = node("option", "", `${score} 分`);
      option.value = String(score);
      input.append(option);
    }
    label.append(name, input);
    controls.append(label);
    return input;
  });
  function updateScore(): void {
    const scores = inputs.map((input) =>
      input.value === "" ? null : Number(input.value),
    ) as QualityScores;
    const total = qualityTotal(scores);
    required("quality-total", HTMLOutputElement).value =
      total === null ? "— / 100" : `${total} / 100`;
    required("quality-status", HTMLElement).textContent =
      total === null
        ? "四項皆須評估才計算總分。未評估不等於 0 分，也不重新分配權重。"
        : "此數字僅為量表試算，不會儲存，也不列入本場候選人統計。";
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
