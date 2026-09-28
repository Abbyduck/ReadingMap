import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type CatalogEntity, type Creator, type ReadingList, type ReadingListItem } from "@/api/client";
import type { PrototypeBook, PrototypeStage } from "@/pages/readingMapPrototype.mock";

type CatalogState = { entities: CatalogEntity[]; creators: Creator[]; lists: ReadingList[]; loading: boolean; error: string };
const CatalogContext = createContext<CatalogState>({ entities: [], creators: [], lists: [], loading: true, error: "" });
export function CatalogProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<CatalogState>({ entities: [], creators: [], lists: [], loading: true, error: "" });
  useEffect(() => {
    let active = true;
    Promise.all([api.entities(), api.creators(), api.readingLists()]).then(([entities, creators, lists]) => { if (active) setState({ entities, creators, lists, loading: false, error: "" }); }).catch(reason => { if (active) setState(previous => ({ ...previous, loading: false, error: reason.message })); });
    return () => { active = false; };
  }, []);
  return <CatalogContext.Provider value={state}>{children}</CatalogContext.Provider>;
}
export const useCatalog = () => useContext(CatalogContext);
export const tones = ["#56a99a", "#6f90c8", "#d5769b", "#d99a48", "#75a85e", "#866db0"];
const entityLabels: Record<string, string> = { book: "单本", animation: "动画", reading_system: "阅读产品线", series: "系列", level: "级别", set: "组合" };
export function ageLabel(min?: number | null, max?: number | null) {
  const format = (months: number) => months % 12 === 0 ? `${months / 12} 岁` : `${months} 个月`;
  if (min != null && max != null) return min === max ? format(min) : `${format(min)} – ${format(max)}`;
  if (min != null) return `${format(min)}+`;
  if (max != null) return `${format(max)}以内`;
  return "未标注推荐年龄";
}
export function toBook(entity: CatalogEntity, lists: ReadingList[], item?: ReadingListItem, list?: ReadingList): PrototypeBook {
  const appearances = lists.filter(candidate => candidate.items?.some(entry => entry.entity.id === entity.id));
  const sourceList = list ?? appearances[0];
  const sourceItem = item ?? sourceList?.items.find(entry => entry.entity.id === entity.id);
  const min = sourceItem?.recommended_age_min_months ?? sourceList?.age_min_months;
  const max = sourceItem?.recommended_age_max_months ?? sourceList?.age_max_months;
  return {
    id: String(entity.id), entityId: entity.id, title: entity.title_en || entity.display_title, titleZh: entity.title_zh || (entity.title_en ? entity.display_title : ""), author: entity.work?.author_text || "作者暂未收录",
    age: ageLabel(min, max), readingMode: entity.independent_reading_suitable === true ? "目录标注可自主阅读" : entity.independent_reading_suitable === false ? "目录标注不适合自主阅读" : "阅读方式待评估",
    lexile: entity.work?.lexile_code || "Lexile 未收录", ar: entity.work?.ar_level != null ? String(entity.work.ar_level) : "未收录", length: entity.work?.page_count != null ? `${entity.work.page_count} 页` : entity.volume_count != null ? `${entity.volume_count} 册` : "篇幅未收录",
    summary: entity.description || "暂无内容介绍。", reason: sourceItem?.comment || sourceItem?.note || sourceList?.description || "暂无推荐说明；未根据孩子年龄或能力推断适读结论。",
    tags: [entityLabels[entity.entity_type], ...(entity.categories ?? []).map(category => category.name_zh), ...(entity.reading_pens ?? []).map(pen => pen.name)],
    source: sourceList ? `${sourceList.creator_name} · ${sourceList.title}` : "公共内容目录", status: "unknown",
    palette: [tones[entity.id % tones.length], "#315e52"], coverUrl: entity.cover_url || "", recommendationCount: new Set(appearances.map(entry => entry.creator_id)).size, listId: sourceList?.id
  };
}
export function stagesFromLists(lists: ReadingList[]): PrototypeStage[] {
  return lists.map((list, index) => ({ id: String(list.id), creatorId: list.creator_id, ageMin: list.age_min_months, ageMax: list.age_max_months, order: index + 1, age: ageLabel(list.age_min_months, list.age_max_months), title: list.stage_label || list.title, subtitle: list.creator_name, focus: list.title, target: list.description || "", duration: `${list.items?.length ?? 0} 条正式推荐`, x: index * 1650, y: index % 2 ? 220 : 920, tone: tones[index % tones.length], books: (list.items ?? []).map(item => toBook(item.entity, lists, item, list)) }));
}
