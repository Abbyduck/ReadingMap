export type ImportanceLevel = "featured" | "normal" | "compact";
export type MapSort = "comprehensive" | "creator" | "amazon" | "mine" | "title";

export type ImportanceInput = {
  id: string;
  title: string;
  recommendationScore?: number;
  position?: number | null;
  amazonRating?: number | null;
  amazonRatingCount?: number | null;
  myRating?: number | null;
  importanceScore?: number;
  importanceLevel?: ImportanceLevel;
};

export const importanceScale: Record<ImportanceLevel, number> = {
  featured: 1.25,
  normal: 1,
  compact: .82
};

export function sortStageItems<T extends ImportanceInput>(items: T[], sort: MapSort): T[] {
  return [...items].sort((left, right) => {
    if (sort === "creator") {
      return (right.recommendationScore ?? 0) - (left.recommendationScore ?? 0)
        || (left.position ?? Number.MAX_SAFE_INTEGER) - (right.position ?? Number.MAX_SAFE_INTEGER)
        || left.id.localeCompare(right.id);
    }
    if (sort === "amazon") {
      return (right.amazonRating ?? -1) - (left.amazonRating ?? -1)
        || (right.amazonRatingCount ?? -1) - (left.amazonRatingCount ?? -1)
        || left.id.localeCompare(right.id);
    }
    if (sort === "mine") return (right.myRating ?? -1) - (left.myRating ?? -1) || left.id.localeCompare(right.id);
    if (sort === "title") return left.title.localeCompare(right.title, "zh-CN");
    return (right.importanceScore ?? 0) - (left.importanceScore ?? 0)
      || (left.position ?? Number.MAX_SAFE_INTEGER) - (right.position ?? Number.MAX_SAFE_INTEGER)
      || left.id.localeCompare(right.id);
  });
}
