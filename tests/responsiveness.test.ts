import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import {
  alignedQuestions,
  dimensions,
  exampleDistributions,
  type QualityScores,
  qualityTotal,
  responseMetrics,
  type Score,
} from "../web/responsiveness";
import type { TranscriptData } from "../web/transcript";

const data = JSON.parse(
  readFileSync(new URL("../data/transcript.json", import.meta.url), "utf8"),
) as TranscriptData;

describe("quality scoring", () => {
  test("uses the requested weights", () => {
    expect(dimensions.map((item) => item.weight)).toEqual([40, 25, 20, 15]);
    expect(qualityTotal([5, 4, 3, 2])).toBe(78);
    expect(qualityTotal([0, 0, 0, 0])).toBe(0);
    expect(qualityTotal([5, 5, 5, 5])).toBe(100);
  });

  test("does not turn an unassessed dimension into zero or redistribute weight", () => {
    expect(qualityTotal([null, null, null, null])).toBeNull();
    for (let index = 0; index < 4; index++) {
      const scores: QualityScores = [5, 5, 5, 5];
      scores[index] = null;
      expect(qualityTotal(scores)).toBeNull();
    }
  });

  test("all integer inputs produce exact scores within 0–100", () => {
    const values: Score[] = [0, 1, 2, 3, 4, 5];
    for (const d of values)
      for (const c of values)
        for (const s of values)
          for (const k of values) {
            expect(qualityTotal([d, c, s, k])).toBe(d * 8 + c * 5 + s * 4 + k * 3);
          }
  });
});

describe("response rates", () => {
  test("excludes unknowns but includes explicit refusals in the denominator", () => {
    expect(
      responseMetrics({ direct: 2, partial: 1, evasive: 1, refusal: 1, undetermined: 5 }),
    ).toEqual({ assessable: 5, direct: 40, partial: 20, evasive: 20 });
  });

  test("has no rate when nothing is assessable", () => {
    expect(
      responseMetrics({ direct: 0, partial: 0, evasive: 0, refusal: 0, undetermined: 3 }),
    ).toEqual({ assessable: 0, direct: null, partial: null, evasive: null });
  });

  test("hypothetical examples have equal assessable sample sizes", () => {
    expect(
      exampleDistributions.map((counts) => Object.values(counts).reduce((a, b) => a + b, 0)),
    ).toEqual([21, 21]);
    expect(exampleDistributions.map(responseMetrics)).toEqual([
      { assessable: 20, direct: 60, partial: 20, evasive: 15 },
      { assessable: 20, direct: 20, partial: 25, evasive: 40 },
    ]);
  });
});

describe("source-aligned evidence", () => {
  test("uses both common reporter questions and complete recorded cue ranges", () => {
    const questions = alignedQuestions(data);
    expect(questions).toHaveLength(2);
    expect(
      questions.map((question) => [question.question[0]?.id, question.question.at(-1)?.id]),
    ).toEqual([
      [747, 764],
      [835, 851],
    ]);
    expect(
      questions.flatMap((question) =>
        question.answers.map((answer) => [answer.cues[0]?.id, answer.cues.at(-1)?.id]),
      ),
    ).toEqual([
      [766, 799],
      [801, 832],
      [853, 885],
      [887, 917],
    ]);
    for (const question of questions) {
      expect(question.subquestions).toHaveLength(4);
      expect(new Set(question.answers.map((answer) => answer.cues[0]?.speaker)).size).toBe(2);
      for (const cue of [
        ...question.question,
        ...question.answers.flatMap((answer) => answer.cues),
      ]) {
        expect(cue).toBe(data.cues.find((source) => source.id === cue.id));
      }
    }
    expect(questions[0]?.question.some((cue) => cue.speaker === "UNKNOWN")).toBe(true);
    expect(questions[0]?.answers[0]?.note).toContain("800");
    expect(questions[0]?.answers[0]?.cues.some((cue) => cue.id === 800)).toBe(false);
  });

  test("does not apply source-specific alignments to another transcript", () => {
    expect(
      alignedQuestions({ ...data, review: { ...data.review, source_sha256: "another" } }),
    ).toEqual([]);
    expect(alignedQuestions({ ...data, cues: [] })).toEqual([]);
  });

  test("drops a question if an answer cue is missing or has another speaker", () => {
    expect(
      alignedQuestions({ ...data, cues: data.cues.filter((cue) => cue.id !== 766) }),
    ).toHaveLength(1);
    expect(
      alignedQuestions({
        ...data,
        cues: data.cues.map((cue) => (cue.id === 766 ? { ...cue, speaker: "UNKNOWN" } : cue)),
      }),
    ).toHaveLength(1);
  });
});
