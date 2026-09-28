import draft from "./bananaN1Incremental.mock.json";

export type PrototypeBookStatus = "ready" | "stretch" | "later" | "unknown";

export type PrototypeBook = {
  id: string;
  title: string;
  titleZh: string;
  author: string;
  age: string;
  readingMode: string;
  lexile: string;
  ar: string;
  length: string;
  summary: string;
  reason: string;
  tags: string[];
  source: string;
  status: PrototypeBookStatus;
  palette: [string, string];
  coverUrl: string;
  entityId?: number;
  recommendationCount?: number;
  recommendationStrength?: 1 | 2 | 3 | null;
  recommendationStrengthText?: string | null;
  creatorCount?: number;
  position?: number | null;
  amazonRating?: number | null;
  amazonRatingMax?: number | null;
  amazonRatingCount?: number | null;
  myRating?: number | null;
  importanceScore?: number;
  importanceLevel?: "featured" | "normal" | "compact";
  recommendationScore?: number;
  strongNow?: boolean;
  isOwned?: boolean;
  recommendations?: Array<{
    creatorName: string;
    creatorId?: number;
    avatarUrl?: string | null;
    readingListTitle: string;
    stageLabel?: string | null;
    isStrongRecommendation?: boolean;
    emphasisText?: string | null;
    recommendationStrength: 1 | 2 | 3 | null;
    recommendationStrengthText?: string | null;
    comment?: string | null;
    note?: string | null;
  }>;
  listId?: number;
};

export type PrototypeStage = {
  id: string;
  order: number;
  age: string;
  title: string;
  subtitle: string;
  focus: string;
  target: string;
  duration: string;
  x: number;
  y: number;
  tone: string;
  books: PrototypeBook[];
  creatorId?: number;
  ageMin?: number | null;
  ageMax?: number | null;
  stageLabel?: string;
};

type SourceItem = {
  sequence: number;
  position: number | null;
  rawTitle: string;
  levelText: string | null;
  arText: string | null;
  lexileText: string | null;
  comment: string | null;
  note: string | null;
  audioText: string | null;
  sourceSection: string | null;
  sourcePageLabel: string | null;
  sourceRow: number | null;
  possibleEntityType: string | null;
  recommendationStrength: 3 | null;
  recommendationStrengthText: string | null;
};
type SourceStage = {
  id: string;
  order: number;
  sourceOrder: number;
  title: string;
  sourcePageLabel: string | null;
  description: string | null;
  items: SourceItem[];
};
type SourceDraft = {
  sourceFile: string;
  listTitle: string;
  listDescription: string;
  creatorName: string;
  stages: SourceStage[];
};

export const bananaN1Source = draft as SourceDraft;
const coverTones: Array<[string, string]> = [
  ["#d98162", "#9d4d49"],
  ["#5f997f", "#315c54"],
  ["#ddb866", "#a16b43"],
  ["#608ca7", "#3d587e"],
  ["#b78291", "#79566b"],
  ["#838abd", "#4d5d92"],
  ["#69a9ad", "#307777"]
];

function sourceBook(item: SourceItem, stage: SourceStage): PrototypeBook {
  const sourcePosition = item.sourcePageLabel && item.sourceRow != null
    ? `${item.sourcePageLabel}第 ${item.sourceRow} 行`
    : "缺页待补证";
  const description = item.comment || "来源仅列出书目，未附内容说明。";
  return {
    id: `source-${item.sequence}`,
    title: item.rawTitle,
    titleZh: item.levelText ?? item.sourceSection ?? "等级未标注",
    author: "来源未记录作者",
    age: item.levelText ?? "等级未标注",
    readingMode: item.audioText ? `音频：${item.audioText}` : "音频未标注",
    lexile: item.lexileText ?? "未标注",
    ar: item.arText ?? "未标注",
    length: "篇幅未标注",
    summary: `${description}（${sourcePosition}）`,
    reason: item.recommendationStrengthText
      ? `来源明确标注“${item.recommendationStrengthText}”。${description}`
      : `收录于${stage.title}；来源没有明确推荐强度。`,
    tags: [item.sourceSection ?? stage.title, item.possibleEntityType ?? "书目", sourcePosition],
    source: `${bananaN1Source.creatorName} · ${bananaN1Source.listTitle}`,
    status: "unknown",
    palette: coverTones[(item.sequence - 1) % coverTones.length],
    coverUrl: "",
    recommendationCount: 1,
    recommendationStrength: item.recommendationStrength,
    recommendationStrengthText: item.recommendationStrengthText,
    creatorCount: 1,
    position: item.position,
    amazonRating: null,
    amazonRatingMax: null,
    amazonRatingCount: null,
    myRating: null,
    recommendations: [{
      creatorName: bananaN1Source.creatorName,
      readingListTitle: bananaN1Source.listTitle,
      recommendationStrength: item.recommendationStrength,
      recommendationStrengthText: item.recommendationStrengthText,
      comment: item.comment,
      note: item.note
    }]
  };
}

export const prototypeStages: PrototypeStage[] = bananaN1Source.stages.map(stage => ({
  id: stage.id,
  stageLabel: stage.title,
  order: stage.order,
  age: stage.sourcePageLabel ?? "旧版",
  title: stage.title,
  subtitle: stage.description ?? "原图增量转录",
  focus: stage.title,
  target: "来源事实转录，待 Research 与人工审核",
  duration: `${stage.items.length} 条来源书目`,
  x: 0,
  y: 0,
  tone: "#3d8f80",
  books: stage.items.map(item => sourceBook(item, stage))
}));

export const prototypeBookCount = prototypeStages.reduce((total, stage) => total + stage.books.length, 0);
