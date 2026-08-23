export type LayoutType =
  | 'overview'
  | 'question'
  | 'principle'
  | 'evidence'
  | 'case'
  | 'path'
  | 'flow'
  | 'comparison'
  | 'layers'
  | 'cause'
  | 'cycle'
  | 'timeline'
  | 'focus'
  | 'summary';

export type CompositionType =
  | 'split-right'
  | 'split-left'
  | 'center-stage'
  | 'top-bottom'
  | 'full-width';

export type TimedCue = {
  id: string;
  anchorText: string;
  startFrame: number;
  endFrame: number;
  spokenStartMs: number;
  spokenEndMs: number;
  enterIds: string[];
  focusId: string;
  alignmentCoverage: number;
  alignmentConfidence: number;
};

export type InfographicPage = {
  id: string;
  image: string;
  startFrame: number;
  endFrame: number;
  seriesTitle: string;
  chapterTitle: string;
  pageTitle: string;
  layoutType: LayoutType;
  composition: CompositionType;
  slideRole: 'overview' | 'detail' | 'transition' | 'summary';
  relationshipType: 'none' | 'sequence' | 'cause' | 'comparison' | 'hierarchy';
  coreIdea: string;
  visualStrategy: string;
  narrativeLink: string;
  nodes: string[];
  conclusion: string;
  cues: TimedCue[];
  seriesPersistent: boolean;
  chapterPersistent: boolean;
};

export type InfographicVideoProps = {
  fps: number;
  width: number;
  height: number;
  totalDurationMs: number;
  totalDurationFrames: number;
  style: string;
  subtitlesEnabled?: boolean;
  pages: InfographicPage[];
};
