import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const workspaceDir = path.resolve(scriptDir, "../..");
const sourcePath = path.join(
  workspaceDir,
  "source_data/drafts/reading_lists/香蕉妈妈__065__2026年香蕉妈妈牛1-高章泛听泛读书单-小红书__incremental-v2.json"
);
const targetPath = path.join(scriptDir, "../src/pages/bananaN1Incremental.mock.json");
const source = JSON.parse(readFileSync(sourcePath, "utf8"));
const sourceStages = source.list?.other_info?.stages ?? [];
const sourceItems = source.items ?? [];

if (sourceStages.length !== 10 || sourceItems.length !== 111) {
  throw new Error(`Unexpected incremental-v2 source size: ${sourceStages.length} stages, ${sourceItems.length} items`);
}

const stages = sourceStages.map((stage, index) => ({
  id: `source-stage-${index + 1}`,
  order: index + 1,
  sourceOrder: stage.stage_order,
  title: stage.title,
  sourcePageLabel: stage.source_page_label ?? null,
  description: stage.description ?? null,
  items: []
}));
const stagesByTitle = new Map(stages.map(stage => [stage.title, stage]));
const sequences = new Set();

for (const item of sourceItems) {
  const extracted = item.extracted ?? {};
  const details = extracted.other_info ?? {};
  const stage = stagesByTitle.get(details.stage?.title);
  if (!stage || sequences.has(item.sequence)) {
    throw new Error(`Missing stage or duplicate sequence for item ${item.sequence}`);
  }
  sequences.add(item.sequence);
  const note = extracted.note ?? null;
  const explicitStrong = /强烈推荐|重点推荐|必读/.test(note ?? "");
  stage.items.push({
    sequence: item.sequence,
    position: item.position ?? null,
    rawTitle: item.raw_title,
    levelText: extracted.level ?? null,
    arText: extracted.ar?.raw ?? null,
    lexileText: extracted.lexile?.raw ?? null,
    comment: extracted.comment ?? null,
    note,
    audioText: details.audio_text ?? null,
    sourceSection: details.source_section ?? null,
    sourcePageLabel: details.source_page_label ?? stage.sourcePageLabel,
    sourceRow: details.source_row ?? null,
    possibleEntityType: item.analysis?.possible_entity_type ?? null,
    recommendationStrength: explicitStrong ? 3 : null,
    recommendationStrengthText: explicitStrong ? "强烈推荐" : null
  });
}

for (const stage of stages) {
  stage.items.sort((left, right) => (left.position ?? Infinity) - (right.position ?? Infinity) || left.sequence - right.sequence);
}

const output = {
  sourceFile: path.relative(workspaceDir, sourcePath).replaceAll("\\", "/"),
  listTitle: source.list.title,
  listDescription: source.list.description,
  creatorName: source.creator.name,
  stages
};
const rendered = `${JSON.stringify(output, null, 2)}\n`;
let current = null;
try { current = readFileSync(targetPath, "utf8"); } catch { /* First generation. */ }
if (current !== rendered) writeFileSync(targetPath, rendered, "utf8");
console.log(`Generated ${path.relative(workspaceDir, targetPath)} from ${stages.length} stages and ${sourceItems.length} items.`);
