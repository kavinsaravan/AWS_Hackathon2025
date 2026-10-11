import type { Route } from "@/components/safe-path-app"
import { assessRouteSafety } from "./routeSafety"

const ROUTING_ENDPOINT = process.env.REACT_APP_API_ENDPOINT?.replace(/\/+$/, "") || ""

async function requestRouting<T>(path: string, body: unknown): Promise<T> {
  if (!ROUTING_ENDPOINT) throw new Error("Routing service is not configured.")
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 25000)
  try {
    const response = await fetch(`${ROUTING_ENDPOINT}/routing/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    })
    if (!response.ok) {
      throw new Error(response.status === 400
        ? "Please choose locations within San Francisco."
        : "Routing is unavailable. Please try again later.")
    }
    return await response.json()
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("Routing timed out. Please try again.")
    }
    throw error
  } finally { clearTimeout(timeout) }
}

interface GeocodingResult {
  hits: Array<{
    point: {
      lat: number
      lng: number
    }
    name: string
  }>
}

interface GraphHopperRoute {
  distance: number // in meters
  time: number // in milliseconds
  points: {
    coordinates: Array<[number, number]> // [lng, lat]
  }
}

interface RoutingResult {
  paths: GraphHopperRoute[]
}

/**
 * Convert address to coordinates using GraphHopper Geocoding API
 */
export async function geocodeAddress(address: string): Promise<{ lat: number; lng: number } | null> {
  try {
    const data = await requestRouting<GeocodingResult>("geocode", { address })

    if (data.hits && data.hits.length > 0) {
      return data.hits[0].point
    }

    return null
  } catch (error) {
    console.error("Geocoding error:", error)
    return null
  }
}

/**
 * Calculate routes between two points using GraphHopper Routing API
 */
export async function calculateRoutes(
  origin: string,
  destination: string
): Promise<{ routes: Route[]; originCoords: { lat: number; lng: number }; destCoords: { lat: number; lng: number } } | null> {
  try {
    // Step 1: Geocode origin and destination
    const originCoords = await geocodeAddress(origin)
    const destCoords = await geocodeAddress(destination)

    if (!originCoords || !destCoords) {
      throw new Error("Could not geocode addresses")
    }

    const data = await requestRouting<RoutingResult>("route", {
      origin: originCoords, destination: destCoords,
    })

    if (!data.paths || data.paths.length === 0) {
      throw new Error("No routes found")
    }

    // Keep actual distinct alternatives; never manufacture additional routes.
    const uniquePaths = data.paths.filter((path, index, paths) =>
      paths.findIndex(other => JSON.stringify(other.points.coordinates) ===
        JSON.stringify(path.points.coordinates)) === index
    ).slice(0, 3)
    const candidates = uniquePaths.map((path, index) => ({
      id: index + 1,
      coordinates: path.points.coordinates.map(([lng, lat]) => ({ lat, lng })),
    }))
    const assessment = await assessRouteSafety(candidates)
    const fastestId = candidates.reduce((fastest, candidate) =>
      uniquePaths[candidate.id - 1].time < uniquePaths[fastest.id - 1].time ? candidate : fastest
    ).id
    const ranked = [...assessment.routes].sort((a, b) =>
      a.totalRisk - b.totalRisk || uniquePaths[a.id - 1].time - uniquePaths[b.id - 1].time
    )
    const routes: Route[] = ranked.map((risk, index) => {
      const path = uniquePaths[risk.id - 1]
      const isFastest = risk.id === fastestId
      return {
        id: risk.id,
        name: index === 0 ? (isFastest ? "Lowest Risk · Fastest" : "Lowest Reported Risk")
          : isFastest ? "Fastest Route" : "Alternative Route",
        distance: `${(path.distance / 1609.34).toFixed(1)} mi`,
        time: `${Math.round(path.time / 60000)} min`,
        safetyScore: risk.safetyScore,
        totalRisk: risk.totalRisk,
        crimeRisk: risk.crimeRisk,
        hazardRisk: risk.hazardRisk,
        assessedAt: assessment.assessedAt,
        dataFetchedAt: assessment.dataFetchedAt,
        sources: assessment.sources,
        coordinates: candidates[risk.id - 1].coordinates,
        waypoints: [],
        color: index === 0 ? "#10b981" : isFastest ? "#f59e0b" : "#3b82f6",
      }
    })

    return {
      routes,
      originCoords,
      destCoords,
    }
  } catch (error) {
    console.error("GraphHopper routing error:", error)
    throw error
  }
}

/**
 * Check if the backend routing endpoint is configured
 */
export function isGraphHopperConfigured(): boolean {
  return ROUTING_ENDPOINT.length > 0
}
