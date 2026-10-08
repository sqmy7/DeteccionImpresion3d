// The same four-point homography the backend computes (app/services/bed_map.py), used here only
// to preview a calibration: the bed grid drawn over the photo before saving.

export type Point = [number, number];
export type Matrix = number[]; // 3x3 row-major

export function solveHomography(src: Point[], dst: Point[]): Matrix | null {
  if (src.length !== 4 || dst.length !== 4) return null;
  const rows: number[][] = [];
  src.forEach(([x, y], index) => {
    const [u, v] = dst[index];
    rows.push([x, y, 1, 0, 0, 0, -u * x, -u * y, u]);
    rows.push([0, 0, 0, x, y, 1, -v * x, -v * y, v]);
  });
  for (let col = 0; col < 8; col += 1) {
    let pivot = col;
    for (let row = col + 1; row < 8; row += 1) if (Math.abs(rows[row][col]) > Math.abs(rows[pivot][col])) pivot = row;
    if (Math.abs(rows[pivot][col]) < 1e-12) return null;
    [rows[col], rows[pivot]] = [rows[pivot], rows[col]];
    for (let row = 0; row < 8; row += 1) {
      if (row === col) continue;
      const factor = rows[row][col] / rows[col][col];
      rows[row] = rows[row].map((value, index) => value - factor * rows[col][index]);
    }
  }
  return [...rows.map((row, index) => row[8] / row[index]), 1];
}

export function applyHomography(h: Matrix, x: number, y: number): Point {
  const w = h[6] * x + h[7] * y + h[8];
  return [(h[0] * x + h[1] * y + h[2]) / w, (h[3] * x + h[4] * y + h[5]) / w];
}

/** True if the points, in order, form a convex quadrilateral (marks not crossed). */
export function isConvexInOrder(points: Point[]): boolean {
  if (points.length !== 4) return false;
  const signs = points.map((_, index) => {
    const [x1, y1] = points[index];
    const [x2, y2] = points[(index + 1) % 4];
    const [x3, y3] = points[(index + 2) % 4];
    return (x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2);
  });
  return signs.every((sign) => sign > 0) || signs.every((sign) => sign < 0);
}
