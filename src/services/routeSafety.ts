export interface RouteRisk {
  id: number
  totalRisk: number
  crimeRisk: number
  hazardRisk: number
  safetyScore: number
}

export interface SafetyAssessment {
  routes: RouteRisk[]
  assessedAt: string
  dataFetchedAt: string
  sources: { policeCalls: number; open311Reports: number }
}

export async function assessRouteSafety(
  routes: Array<{ id: number; coordinates: Array<{ lat: number; lng: number }> }>
): Promise<SafetyAssessment> {
  const endpoint = process.env.REACT_APP_API_ENDPOINT?.replace(/\/+$/, "")
  if (!endpoint) throw new Error("Route safety service is not configured.")
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 28000)
  try {
    const response = await fetch(`${endpoint}/score-routes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ routes }),
      signal: controller.signal,
    })
    if (!response.ok) {
      const message = response.status === 400
        ? "Safety scoring is available for walking routes within San Francisco."
        : "Safety data is unavailable. Please try again later."
      throw new Error(message)
    }
    const data: SafetyAssessment = await response.json()
    if (!Array.isArray(data.routes) || data.routes.length !== routes.length ||
        new Set(data.routes.map(r => r.id)).size !== routes.length ||
        typeof data.assessedAt !== "string" || !Number.isFinite(Date.parse(data.assessedAt)) ||
        typeof data.dataFetchedAt !== "string" || !Number.isFinite(Date.parse(data.dataFetchedAt)) ||
        !data.sources || !Number.isInteger(data.sources.policeCalls) || data.sources.policeCalls < 0 ||
        !Number.isInteger(data.sources.open311Reports) || data.sources.open311Reports < 0 ||
        data.routes.some(r => !routes.some(route => route.id === r.id) ||
          ![r.totalRisk, r.crimeRisk, r.hazardRisk, r.safetyScore].every(Number.isFinite) ||
          r.totalRisk < 0 || r.crimeRisk < 0 || r.hazardRisk < 0 ||
          r.safetyScore < 0 || r.safetyScore > 100)) {
      throw new Error("The safety service returned an invalid assessment. Please try again.")
    }
    return data
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("Safety analysis timed out. Please try again.")
    }
    throw error
  } finally {
    clearTimeout(timeout)
  }
}
