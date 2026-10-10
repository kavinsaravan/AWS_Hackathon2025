import type { Route } from "@/components/safe-path-app"
import { assessRouteSafety } from "./routeSafety"

const GRAPHHOPPER_API_KEY = process.env.REACT_APP_GRAPHHOPPER_API_KEY || ""
const GEOCODING_URL = "https://graphhopper.com/api/1/geocode"
const ROUTING_URL = "https://graphhopper.com/api/1/route"

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
    // Add San Francisco location bias if address doesn't already specify a city
    let searchQuery = address
    const lowerAddress = address.toLowerCase()
    const hasCityContext = lowerAddress.includes("san francisco") ||
                          lowerAddress.includes("sf") ||
                          lowerAddress.includes(", ca") ||
                          lowerAddress.includes("california")

    if (!hasCityContext) {
      searchQuery = `${address}, San Francisco, CA`
    }

    // San Francisco coordinates for location bias
    const SF_LAT = 37.7749
    const SF_LNG = -122.4194

    const params = new URLSearchParams({
      q: searchQuery,
      point: `${SF_LAT},${SF_LNG}`, // Bias results toward San Francisco
      locale: "en-US",
      key: GRAPHHOPPER_API_KEY,
    })

    const response = await fetch(`${GEOCODING_URL}?${params.toString()}`)

    if (!response.ok) {
      throw new Error(`Geocoding failed: ${response.statusText}`)
    }

    const data: GeocodingResult = await response.json()

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

    // Step 2: Get multiple route alternatives
    // Build URL with multiple 'point' parameters
    const params = new URLSearchParams({
      vehicle: "foot", // walking routes
      locale: "en",
      points_encoded: "false",
      algorithm: "alternative_route",
      "alternative_route.max_paths": "3",
      key: GRAPHHOPPER_API_KEY,
    })

    // Add points manually (URLSearchParams doesn't support duplicate keys in object literal)
    params.append("point", `${originCoords.lat},${originCoords.lng}`)
    params.append("point", `${destCoords.lat},${destCoords.lng}`)

    const response = await fetch(`${ROUTING_URL}?${params.toString()}`)

    if (!response.ok) {
      throw new Error(`Routing failed: ${response.statusText}`)
    }

    const data: RoutingResult = await response.json()

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
 * Check if GraphHopper API key is configured
 */
export function isGraphHopperConfigured(): boolean {
  return GRAPHHOPPER_API_KEY.length > 0
}
