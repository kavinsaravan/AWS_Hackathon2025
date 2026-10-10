export interface AnalyticsBounds { north: number; south: number; east: number; west: number }
export interface CrimeCell { south: number; north: number; west: number; east: number; count: number; categories: Array<[string, number]>; days: Array<[string, number]> }
export interface CrimeSnapshot { version: number; refreshedUTC: string; windowDays: number; geocodedRecords: number; dates: string[]; cells: CrimeCell[] }

export function summarizeCrimeArea(snapshot: CrimeSnapshot, bounds?: AnalyticsBounds) {
  const cells = snapshot.cells.filter(cell => !bounds ||
    (cell.north >= bounds.south && cell.south <= bounds.north && cell.east >= bounds.west && cell.west <= bounds.east))
  const categories = new Map<string, number>(), days = new Map<string, number>()
  let count = 0
  cells.forEach(cell => {
    count += cell.count
    cell.categories.forEach(([key, n]) => categories.set(key, (categories.get(key) || 0) + n))
    cell.days.forEach(([key, n]) => days.set(key, (days.get(key) || 0) + n))
  })
  return { count,
    categories: Array.from(categories).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([name, count]) => ({ name, count })),
    days: snapshot.dates.map(date => ({ date, count: days.get(date) || 0 })) }
}

export function routeArea(coordinates: Array<{ lat: number; lng: number }>): AnalyticsBounds {
  if (!coordinates.length) throw new Error("A route is required")
  return {
    north: Math.max(...coordinates.map(p => p.lat)) + .003,
    south: Math.min(...coordinates.map(p => p.lat)) - .003,
    east: Math.max(...coordinates.map(p => p.lng)) + .004,
    west: Math.min(...coordinates.map(p => p.lng)) - .004,
  }
}
