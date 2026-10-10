export interface AnalyticsBounds { north: number; south: number; east: number; west: number }
export interface PowerBIReport { url: string; mode: "secure" | "public" }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function parsePowerBIReport(value: string): PowerBIReport {
  const source = new URL(value.trim())
  if (source.protocol !== "https:" || source.hostname !== "app.powerbi.com" || source.username || source.password || source.port) {
    throw new Error("Use a report link from https://app.powerbi.com.")
  }
  if (source.pathname === "/view") {
    const token = source.searchParams.get("r")
    if (!token || token.length > 4096) throw new Error("This public Power BI report link is incomplete.")
    const url = new URL("https://app.powerbi.com/view")
    url.searchParams.set("r", token)
    return { url: url.toString(), mode: "public" }
  }
  const match = source.pathname.match(/^\/groups\/([^/]+)\/reports\/([^/]+)/)
  const reportId = match?.[2] || source.searchParams.get("reportId")
  if (!reportId || !UUID.test(reportId) || (!match && source.pathname !== "/reportEmbed")) {
    throw new Error("Paste the report's Website or portal embed link, or its full report URL.")
  }
  const url = new URL("https://app.powerbi.com/reportEmbed")
  url.searchParams.set("reportId", reportId)
  url.searchParams.set("autoAuth", "true")
  const groupId = match?.[1] || source.searchParams.get("groupId")
  if (groupId && UUID.test(groupId)) url.searchParams.set("groupId", groupId)
  const tenant = source.searchParams.get("ctid")
  if (tenant && UUID.test(tenant)) url.searchParams.set("ctid", tenant)
  return { url: url.toString(), mode: "secure" }
}

export function powerBIEmbedUrl(report: PowerBIReport, bounds?: AnalyticsBounds): string {
  const url = new URL(report.url)
  if (report.mode === "secure" && bounds) {
    if (!Object.values(bounds).every(Number.isFinite) || bounds.north < bounds.south || bounds.east < bounds.west) {
      throw new Error("Invalid analytics area")
    }
    const filters = ["Incidents", "RiskLocations"].flatMap(table => [
      `${table}/Latitude ge ${bounds.south.toFixed(6)}`,
      `${table}/Latitude le ${bounds.north.toFixed(6)}`,
      `${table}/Longitude ge ${bounds.west.toFixed(6)}`,
      `${table}/Longitude le ${bounds.east.toFixed(6)}`,
    ])
    url.searchParams.set("filter", filters.join(" and "))
  }
  return url.toString()
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
