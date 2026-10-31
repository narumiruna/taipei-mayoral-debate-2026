export interface TranscriptMetadata {
  duration: number | null;
  model: string | null;
  stage: string | null;
}

export interface SpeakerRole {
  role: string;
  name: string;
}

export interface Cue {
  id: number;
  start: number;
  end: number;
  speaker: string;
  label: string;
  text: string;
  timing: string;
  original_text?: string;
  correction_id?: string;
}

export interface Correction {
  id: string;
  cue_id: number;
  before: string;
  after: string;
  reason: string;
  evidence: string;
}

export interface Flag {
  id: string;
  cue_id: number;
  reason: string;
  suggestion?: string;
}

export interface Review {
  corrections: Correction[];
  flags: Flag[];
  method: string;
  source_sha256: string;
}

export interface TranscriptData {
  metadata: TranscriptMetadata;
  display_language: string;
  roles: Record<string, SpeakerRole>;
  cues: Cue[];
  review: Review;
}
