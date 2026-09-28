// The ten circles correspond one-to-one to source book-list groups. The route
// is a visual reading path, not an invented mapping from 牛 levels to ages.
export type RouteWaypoint = {
  id: string;
  order: number;
  x: number;
  y: number;
  circleX: number;
  circleY: number;
  circleSize: number;
  tone: string;
  sourceSide: "right";
  targetSide: "left";
};

const tones = [
  "#62aa9b", "#7799c8", "#d184a4", "#d5a05f", "#82ad73",
  "#877db8", "#78a8b2", "#c98e73", "#8d9fbd", "#b39c6c"
];

function baseCircleSize(bookCount: number): number {
  if (bookCount >= 16) return 2200;
  if (bookCount >= 10) return 1700;
  if (bookCount >= 8) return 1500;
  if (bookCount >= 5) return 1300;
  if (bookCount >= 3) return 1200;
  return 950;
}

export function routeWaypointsForStages(bookCounts: number[], spacing: number): RouteWaypoint[] {
  const sizes = bookCounts.map(count => baseCircleSize(count) * spacing);
  const gap = 300 * spacing;
  const lefts = new Array<number>(bookCounts.length);
  let cursor = 0;
  for (let index = 0; index < bookCounts.length; index++) {
    lefts[index] = cursor;
    cursor += sizes[index] + gap;
  }
  // Alternating high/low stops make the single route meander rather than read
  // as a nearly straight horizontal row at the default overview zoom.
  const verticalOffsets = [700, -600, 1000, -350, 900, -650, 950, -300, 800, -500];
  return Array.from({ length: bookCounts.length }, (_, index) => {
    const circleSize = sizes[index];
    const circleX = lefts[index];
    const circleY = verticalOffsets[index % verticalOffsets.length] * spacing;
    return {
      id: `waypoint-${index + 1}`,
      order: index + 1,
      x: circleX + circleSize / 2 - 220,
      y: circleY - 220,
      circleX,
      circleY,
      circleSize,
      tone: tones[index % tones.length],
      sourceSide: "right",
      targetSide: "left"
    };
  });
}
