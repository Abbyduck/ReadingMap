import { useEffect, useMemo, useState, type CSSProperties } from "react";
import {
  Background, BackgroundVariant, BaseEdge, Controls, type Edge, type EdgeProps,
  getBezierPath, Handle, MiniMap, type Node, type NodeProps, Panel, Position, ReactFlow, useViewport
} from "@xyflow/react";
import { Settings2 } from "lucide-react";
import { BookCover } from "@/components/books/BookCover";
import { WorkDrawer } from "@/components/books/WorkDrawer";
import { ProductHeader } from "@/components/layout/ProductHeader";
import { api, type StageEntityImportance } from "@/api/client";
import { toBook, useCatalog } from "@/lib/catalog";
import { bananaN1Source, prototypeStages, type PrototypeBook, type PrototypeStage } from "./readingMapPrototype.mock";
import { routeWaypointsForStages, type RouteWaypoint } from "./readingMapRoute.mock";
import { importanceScale, sortStageItems, type MapSort } from "./readingMapImportance";

type StageLayout = "organic" | "grid" | "spaced";
type BookNodeData = {
  book: PrototypeBook;
  stageId: string;
  detailZoom: number;
  displayScale: number;
  onOpen: (book: PrototypeBook) => void;
} & Record<string, unknown>;
type BookFlowNode = Node<BookNodeData, "book">;
type WaypointNodeData = { waypoint: RouteWaypoint; count: number } & Record<string, unknown>;
type WaypointFlowNode = Node<WaypointNodeData, "waypoint">;
type StageCircleNodeData = { waypoint: RouteWaypoint; title: string } & Record<string, unknown>;
type StageCircleFlowNode = Node<StageCircleNodeData, "stage-circle">;
type MapFlowNode = BookFlowNode | WaypointFlowNode | StageCircleFlowNode;
type RouteEdgeData = { from: RouteWaypoint; to: RouteWaypoint } & Record<string, unknown>;
type RouteFlowEdge = Edge<RouteEdgeData, "route">;

const STAGE_SPACING = .9;
const BOOK_DETAIL_ZOOM = .85;
const DEFAULT_BOOK_SPACING = .75;

const handlePosition = {
  left: Position.Left,
  right: Position.Right,
  top: Position.Top,
  bottom: Position.Bottom
};

function StageCircleNode({ data }: NodeProps<StageCircleFlowNode>) {
  return (
    <div
      className="rmp-stage-circle"
      data-stage-id={prototypeStages[data.waypoint.order - 1].id}
      title={data.title}
      style={{ "--rmp-tone": data.waypoint.tone } as CSSProperties}
    />
  );
}

function WaypointNode({ data }: NodeProps<WaypointFlowNode>) {
  return (
    <div
      className="rmp-route-waypoint"
      aria-label={`路径节点 ${data.waypoint.order}`}
      style={{ "--rmp-tone": data.waypoint.tone } as CSSProperties}
    >
      <Handle id="route-target" type="target" position={handlePosition[data.waypoint.targetSide]} className="rmp-flow-handle" />
      <span>{String(data.waypoint.order).padStart(2, "0")}</span>
      <small>{data.count} 本</small>
      <Handle id="route-source" type="source" position={handlePosition[data.waypoint.sourceSide]} className="rmp-flow-handle" />
    </div>
  );
}

function RouteEdge(props: EdgeProps<RouteFlowEdge>) {
  const [bezierPath] = getBezierPath({
    sourceX: props.sourceX,
    sourceY: props.sourceY,
    sourcePosition: props.sourcePosition,
    targetX: props.targetX,
    targetY: props.targetY,
    targetPosition: props.targetPosition,
    curvature: .38
  });
  const from = props.data?.from;
  const to = props.data?.to;
  const path = from && to
    ? (() => {
      const sourceX = from.circleX + from.circleSize * .94;
      const sourceY = from.circleY + from.circleSize * .5;
      const targetX = to.circleX + to.circleSize * .06;
      const targetY = to.circleY + to.circleSize * .5;
      const bend = Math.max(130, (targetX - sourceX) * .36);
      return `M ${sourceX},${sourceY} C ${sourceX + bend},${sourceY} ${targetX - bend},${targetY} ${targetX},${targetY}`;
    })()
    : bezierPath;
  return (
    <>
      <BaseEdge path={path} style={{ stroke: "rgba(29, 65, 56, .14)", strokeWidth: 44 }} />
      <BaseEdge path={path} style={{ stroke: "#4d8f80", strokeWidth: 18 }} />
    </>
  );
}

function BookNode({ data }: NodeProps<BookFlowNode>) {
  const { zoom } = useViewport();
  const { book } = data;
  const scale = data.displayScale;
  const detailed = zoom >= data.detailZoom;
  return (
    <button
      type="button"
      className={`rmp-flow-book ${detailed ? "rmp-book-detailed" : "rmp-book-cover-only"} nodrag nopan`}
      data-stage-id={data.stageId}
      data-importance-score={book.importanceScore?.toFixed(1) ?? "22.0"}
      style={{ "--rmp-importance-scale": scale } as CSSProperties}
      onClick={() => data.onOpen(book)}
      aria-label={`打开 ${book.title} 详情，综合推荐 ${book.importanceScore?.toFixed(1) ?? "22.0"} 分`}
    >
      <BookCover book={book} />
      {detailed ? (
        <span className="rmp-flow-book-summary">
          <span className="rmp-book-badges">
            <em className="score">{book.importanceScore?.toFixed(1) ?? "22.0"} 分</em>
            {book.strongNow ? <em className="strong">★ 强烈推荐</em> : null}
          </span>
          <strong>{book.title}</strong>
          {book.titleZh ? <small>{book.titleZh}</small> : null}
          <span>{book.ar}</span>
        </span>
      ) : null}
    </button>
  );
}

const nodeTypes = { book: BookNode, waypoint: WaypointNode, "stage-circle": StageCircleNode };
const edgeTypes = { route: RouteEdge };

function positionedRoute(waypoints: RouteWaypoint[], stages: PrototypeStage[]): Array<WaypointFlowNode | StageCircleFlowNode> {
  return waypoints.flatMap((waypoint, index) => [
    {
      id: `circle-${waypoint.id}`,
      type: "stage-circle" as const,
      position: { x: waypoint.circleX, y: waypoint.circleY },
      data: { waypoint, title: prototypeStages[index].title },
      draggable: false,
      selectable: false,
      connectable: false,
      zIndex: -2,
      width: waypoint.circleSize,
      height: waypoint.circleSize,
      style: { width: waypoint.circleSize, height: waypoint.circleSize }
    },
    {
      id: waypoint.id,
      type: "waypoint" as const,
      position: { x: waypoint.x, y: waypoint.y },
      data: { waypoint, count: stages[index].books.length },
      draggable: false,
      selectable: false,
      connectable: false,
      zIndex: 5,
      width: 440,
      height: 220,
      style: { width: 440, height: 220 }
    }
  ]);
}

function routeConnections(waypoints: RouteWaypoint[]): RouteFlowEdge[] {
  return waypoints.slice(0, -1).map((waypoint, index) => ({
    id: `route-${waypoint.id}-${waypoints[index + 1].id}`,
    type: "route",
    source: waypoint.id,
    sourceHandle: "route-source",
    target: waypoints[index + 1].id,
    targetHandle: "route-target",
    data: { from: waypoint, to: waypoints[index + 1] },
    selectable: false,
    zIndex: 1
  }));
}

type BookSlot = { dx: number; dy: number };

function stageSlots(count: number, columns: number, pitchX: number, pitchY: number): BookSlot[] {
  const rows = Math.ceil(count / columns);
  return Array.from({ length: count }, (_, index) => {
    const row = Math.floor(index / columns);
    const column = index % columns;
    const itemsInRow = Math.min(columns, count - row * columns);
    return {
      dx: (column - (itemsInRow - 1) / 2) * pitchX,
      dy: (row - (rows - 1) / 2) * pitchY
    };
  });
}

function centerFirst(slots: BookSlot[]): BookSlot[] {
  return [...slots].sort((a, b) =>
    a.dx * a.dx + a.dy * a.dy - b.dx * b.dx - b.dy * b.dy
    || a.dy - b.dy || a.dx - b.dx
  );
}

function fittedStageSlots(
  books: PrototypeBook[], columns: number, circleSize: number, spacing: number, bookSpacing: number, centerOut: boolean
): { slots: BookSlot[]; fitScale: number } {
  const maxScale = Math.max(1, ...books.map(book => importanceScale[book.importanceLevel ?? "normal"]));
  const gap = (16 + 24 * bookSpacing) * spacing;
  const safeRadius = circleSize / 2 - 36 * spacing;
  for (let fitScale = 1; fitScale >= .4; fitScale -= .025) {
    const pitchX = 150 * maxScale * fitScale + gap;
    const pitchY = 260 * maxScale * fitScale + gap;
    const slots = stageSlots(books.length, columns, pitchX, pitchY);
    const orderedSlots = centerOut ? centerFirst(slots) : slots;
    const fits = books.every((book, index) => {
      const slot = orderedSlots[index];
      const scale = importanceScale[book.importanceLevel ?? "normal"] * fitScale;
      const halfWidth = 75 * scale;
      const halfHeight = 130 * scale;
      return Math.hypot(Math.abs(slot.dx) + halfWidth, Math.abs(slot.dy) + halfHeight) <= safeRadius;
    });
    if (fits) return { slots, fitScale };
  }
  return {
    slots: stageSlots(books.length, columns, 150 * maxScale * .4 + gap, 260 * maxScale * .4 + gap),
    fitScale: .4
  };
}

function positionedBooks(
  waypoints: RouteWaypoint[],
  stages: PrototypeStage[],
  layout: StageLayout,
  sort: MapSort,
  spacing: number,
  bookSpacing: number,
  detailZoom: number,
  onOpen: (book: PrototypeBook) => void
): BookFlowNode[] {
  return stages.flatMap((stage, stageIndex) => {
    const ordered = sortStageItems(stage.books, layout === "grid" ? sort : "comprehensive");
    const columns = ordered.length >= 16 ? 5 : ordered.length >= 10 ? 4 : ordered.length >= 5 ? 3 : 2;
    const waypoint = waypoints[stageIndex];
    const centerX = waypoint.circleX + waypoint.circleSize / 2;
    const centerY = waypoint.circleY + waypoint.circleSize / 2;
    const fitted = layout === "organic" ? null : fittedStageSlots(ordered, columns, waypoint.circleSize, spacing, bookSpacing, layout === "spaced");
    const slots = fitted
      ? layout === "spaced" ? centerFirst(fitted.slots) : fitted.slots
      : centerFirst(stageSlots(ordered.length, columns, 230 * spacing * bookSpacing, 310 * spacing * bookSpacing));
    return ordered.map((book, index) => {
      const scale = importanceScale[book.importanceLevel ?? "normal"] * (fitted?.fitScale ?? 1);
      const jitterX = layout === "organic" ? ((index * 37) % 7 - 3) * 4 * spacing * bookSpacing : 0;
      const jitterY = layout === "organic" ? ((index * 17) % 5 - 2) * 6 * spacing * bookSpacing : 0;
      const x = centerX + slots[index].dx - 75 * scale + jitterX;
      const y = centerY + slots[index].dy - 130 * scale + jitterY;
      return {
        id: `book-${book.id}`,
        type: "book",
        position: { x, y },
        data: { book, stageId: stage.id, detailZoom, displayScale: scale, onOpen },
        draggable: false,
        selectable: false,
        connectable: false,
        zIndex: 10 + Math.round(book.importanceScore ?? 0),
        width: 150 * scale,
        height: 260 * scale,
        style: { width: 150 * scale, height: 260 * scale }
      };
    });
  });
}

function DebugPanel({
  layout, setLayout, sort, setSort, bookSpacing, setBookSpacing
}: {
  layout: StageLayout;
  setLayout: (value: StageLayout) => void;
  sort: MapSort;
  setSort: (value: MapSort) => void;
  bookSpacing: number;
  setBookSpacing: (value: number) => void;
}) {
  const { zoom } = useViewport();
  return (
    <Panel position="bottom-left" className="rmp-debug-panel" aria-label="地图调试参数">
      <div className="rmp-debug-head"><strong>地图调试参数</strong><span>当前 {zoom.toFixed(2)}×</span></div>
      <div className="rmp-debug-layout">
        <span>书目排布</span>
        <div className="rmp-debug-layout-options" role="group" aria-label="书目重叠方式">
          <button type="button" className={layout === "organic" ? "active" : ""} aria-pressed={layout === "organic"} onClick={() => setLayout("organic")}>重叠</button>
          <button type="button" className={layout === "grid" ? "active" : ""} aria-pressed={layout === "grid"} onClick={() => setLayout("grid")}>整齐排列</button>
          <button type="button" className={layout === "spaced" ? "active" : ""} aria-pressed={layout === "spaced"} onClick={() => setLayout("spaced")}>不重叠</button>
        </div>
      </div>
      {layout === "grid" ? <label>排序<select value={sort} onChange={event => setSort(event.target.value as MapSort)}><option value="comprehensive">综合推荐</option><option value="creator">达人推荐</option><option value="title">书名</option></select></label> : null}
      <label>
        <span>书与书间距 <output>{bookSpacing.toFixed(2)}×</output></span>
        <input aria-label="书与书间距" type="range" min="0.4" max="1.15" step="0.05" value={bookSpacing} onChange={event => setBookSpacing(Number(event.target.value))} />
      </label>
      <button type="button" onClick={() => { setLayout("organic"); setSort("comprehensive"); setBookSpacing(DEFAULT_BOOK_SPACING); }}>恢复默认</button>
    </Panel>
  );
}

function MapNavigator() {
  const { zoom } = useViewport();
  return (
    <Panel position="top-right" className="rmp-map-navigator" aria-label="地图总览与当前视野">
      <div className="rmp-navigator-heading"><span>地图总览</span><strong>{zoom.toFixed(2)}×</strong></div>
      <MiniMap<MapFlowNode>
        position="top-right"
        className="rmp-navigator-minimap"
        style={{ width: 188, height: 98 }}
        pannable
        zoomable
        ariaLabel="地图总览，框内为当前视野"
        nodeClassName={node => node.type === "stage-circle" ? "rmp-mini-stage" : "rmp-mini-hidden"}
        nodeColor={node => node.type === "stage-circle" ? (node.data as StageCircleNodeData).waypoint.tone : "transparent"}
        nodeBorderRadius={1100}
        nodeStrokeColor="rgba(63, 111, 94, .3)"
        maskColor="rgba(230, 239, 233, .55)"
        maskStrokeColor="#376f60"
        maskStrokeWidth={3}
        offsetScale={12}
      />
    </Panel>
  );
}

function mapBook(row: StageEntityImportance, lists: ReturnType<typeof useCatalog>["lists"]): PrototypeBook {
  const book = toBook(row.entity, lists);
  return {
    ...book,
    recommendationScore: row.recommendation_score,
    strongNow: row.recommendation_meta.strong_now,
    creatorCount: row.recommendation_meta.creator_count,
    recommendationCount: row.recommendation_meta.creator_count,
    importanceScore: row.importance_score,
    importanceLevel: row.importance_level,
    position: row.position,
    amazonRating: row.amazon_rating,
    amazonRatingCount: row.amazon_rating_count,
    recommendations: row.recommendations.map(relation => ({
      creatorId: relation.creator_id,
      creatorName: relation.creator_name,
      avatarUrl: relation.creator_avatar_url,
      readingListTitle: relation.reading_list_title,
      stageLabel: relation.stage_label,
      isStrongRecommendation: relation.is_strong_recommendation,
      emphasisText: relation.recommendation_emphasis_text,
      recommendationStrength: relation.is_strong_recommendation ? 3 : null,
      recommendationStrengthText: relation.recommendation_emphasis_text,
      comment: relation.comment,
      note: relation.note
    }))
  };
}

export function ReadingMapPage() {
  const { creators, lists, loading } = useCatalog();
  const [selectedBook, setSelectedBook] = useState<PrototypeBook | null>(null);
  const [stages, setStages] = useState<PrototypeStage[]>(() => prototypeStages.map(stage => ({ ...stage, books: [] })));
  const [loadError, setLoadError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [layout, setLayout] = useState<StageLayout>("organic");
  const [sort, setSort] = useState<MapSort>("comprehensive");
  const [bookSpacing, setBookSpacing] = useState(DEFAULT_BOOK_SPACING);
  const [debugOpen, setDebugOpen] = useState(false);
  const params = new URLSearchParams(window.location.search);
  const requestedCreatorId = Number(params.get("creator")) || undefined;
  const selectedListId = Number(params.get("list")) || (!requestedCreatorId
    ? lists.find(list => list.creator_name === bananaN1Source.creatorName && list.title === bananaN1Source.listTitle)?.id
    : undefined);
  const selectedCreatorId = requestedCreatorId || creators.find(creator => creator.name === bananaN1Source.creatorName)?.id;
  useEffect(() => {
    const refreshOnFocus = () => setRefreshKey(key => key + 1);
    window.addEventListener("focus", refreshOnFocus);
    return () => window.removeEventListener("focus", refreshOnFocus);
  }, []);
  useEffect(() => {
    if (loading) return;
    if (!selectedCreatorId && !selectedListId) {
      setLoadError("这条路线尚未关联正式达人书单。");
      return;
    }
    let active = true;
    Promise.all(prototypeStages.map(stage => api.readingMapStage(stage.stageLabel || stage.title, {
      creatorId: selectedListId ? undefined : selectedCreatorId,
      readingListId: selectedListId
    }))).then(responses => {
      if (!active) return;
      setStages(prototypeStages.map((stage, index) => ({
        ...stage,
        books: responses[index].entities.map(row => mapBook(row, lists))
      })));
      setLoadError("");
    }).catch(error => { if (active) setLoadError(error instanceof Error ? error.message : "地图推荐加载失败"); });
    return () => { active = false; };
  }, [loading, selectedCreatorId, selectedListId, lists, refreshKey]);
  useEffect(() => {
    if (!selectedBook) return;
    const updated = stages.flatMap(stage => stage.books).find(book => book.entityId === selectedBook.entityId);
    if (updated && updated !== selectedBook) setSelectedBook(updated);
  }, [stages]);
  const waypoints = useMemo(() => routeWaypointsForStages(stages.map(stage => stage.books.length), STAGE_SPACING), [stages]);
  const routeNodes = useMemo(() => positionedRoute(waypoints, stages), [waypoints, stages]);
  const routeEdges = useMemo(() => routeConnections(waypoints), [waypoints]);
  const bookNodes = useMemo(
    () => positionedBooks(waypoints, stages, layout, sort, STAGE_SPACING, bookSpacing, BOOK_DETAIL_ZOOM, setSelectedBook),
    [waypoints, stages, layout, sort, bookSpacing]
  );
  const nodes: MapFlowNode[] = [...routeNodes, ...bookNodes];

  return (
    <main className="rmp-app rmp-continuous-map rmp-chapter-map rmp-source-route">
      <ProductHeader current="map" overlay />
      <section className="rmp-flow-shell" aria-label="连续缩放的阅读路径与香蕉妈妈书目">
        {loadError ? <p role="alert" className="absolute left-1/2 top-20 z-20 -translate-x-1/2 rounded-xl bg-white px-4 py-2 text-sm text-red-700 shadow">{loadError}</p> : null}
        <ReactFlow<MapFlowNode, RouteFlowEdge>
          nodes={nodes}
          edges={routeEdges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          minZoom={.06}
          maxZoom={2.5}
          fitView
          fitViewOptions={{ padding: .08, minZoom: .06, maxZoom: .18 }}
          zoomOnScroll
          zoomOnPinch
          panOnDrag
          panOnScroll={false}
          zoomOnDoubleClick={false}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          onNodeClick={(_, node) => { if (node.type === "book") setSelectedBook((node.data as BookNodeData).book); }}
          deleteKeyCode={null}
          selectionKeyCode={null}
          multiSelectionKeyCode={null}
        >
          <Background variant={BackgroundVariant.Dots} gap={76} size={1.7} color="#c9d9d0" />
          <Panel position="bottom-left" className="rmp-map-toolbar" aria-label="地图布局">
            <button type="button" className={debugOpen ? "active" : ""} aria-expanded={debugOpen} onClick={() => setDebugOpen(value => !value)}><Settings2 size={14} />调试参数</button>
          </Panel>
          {debugOpen ? <DebugPanel layout={layout} setLayout={setLayout} sort={sort} setSort={setSort} bookSpacing={bookSpacing} setBookSpacing={setBookSpacing} /> : null}
          <MapNavigator />
          <Controls position="bottom-right" orientation="horizontal" showInteractive={false} fitViewOptions={{ padding: .08, minZoom: .06, maxZoom: .28, duration: 350 }} />
        </ReactFlow>
      </section>
      <WorkDrawer book={selectedBook} onClose={() => setSelectedBook(null)} />
    </main>
  );
}

export const ReadingMapPrototype = ReadingMapPage;
