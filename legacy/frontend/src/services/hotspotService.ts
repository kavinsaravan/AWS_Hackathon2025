/**
 * Hotspot Service
 * Fetches crime hotspot data from AWS Lambda API
 */

export interface Hotspot {
  id: number
  center: {
    lat: number
    lng: number
  }
  radius_km: number
  incident_count: number
  severity_score: number
  risk_level: 'High' | 'Medium' | 'Low'
  color: string
  top_crimes: Array<{
    type: string
    count: number
  }>
  crime_breakdown: Record<string, number>
}

export interface HotspotGeoJSON {
  type: 'FeatureCollection'
  features: Array<{
    type: 'Feature'
    geometry: {
      type: 'Point'
      coordinates: [number, number] // [lng, lat]
    }
    properties: {
      id: number
      radius_km: number
      incident_count: number
      severity_score: number
      risk_level: string
      color: string
      top_crimes: Array<{ type: string; count: number }>
      description: string
    }
  }>
}

export interface HotspotParams {
  eps?: number           // DBSCAN epsilon (km)
  minSamples?: number   // Minimum incidents
  algorithm?: 'dbscan' | 'kmeans'
  format?: 'json' | 'geojson'
}

/**
 * Fetch crime hotspots from AWS Lambda API
 */
export async function fetchHotspots(
  params: HotspotParams = {}
): Promise<HotspotGeoJSON> {
  const {
    eps = 0.3,
    minSamples = 5,
    algorithm = 'dbscan',
    format = 'geojson'
  } = params

  const apiEndpoint = process.env.REACT_APP_API_ENDPOINT || ''

  if (!apiEndpoint) {
    throw new Error('Hotspot service is not configured')
  }

  const queryParams = new URLSearchParams({
    eps: eps.toString(),
    min_samples: minSamples.toString(),
    algorithm,
    format
  })

  const url = `${apiEndpoint}/hotspots?${queryParams}`

  const response = await fetch(url)
  if (!response.ok) {
    throw new Error(`Hotspot service returned HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * Filter hotspots by risk level
 */
export function filterHotspotsByRisk(
  geojson: HotspotGeoJSON,
  riskLevels: Set<string>
): HotspotGeoJSON {
  return {
    ...geojson,
    features: geojson.features.filter(feature =>
      riskLevels.has(feature.properties.risk_level)
    )
  }
}

/**
 * Get hotspot statistics
 */
export function getHotspotStats(geojson: HotspotGeoJSON) {
  const features = geojson.features

  if (features.length === 0) {
    return {
      total: 0,
      high: 0,
      medium: 0,
      low: 0,
      totalIncidents: 0,
      avgSeverity: 0
    }
  }

  const stats = features.reduce(
    (acc, feature) => {
      const { risk_level, incident_count, severity_score } = feature.properties

      acc.total++
      acc.totalIncidents += incident_count
      acc.totalSeverity += severity_score

      if (risk_level === 'High') acc.high++
      else if (risk_level === 'Medium') acc.medium++
      else if (risk_level === 'Low') acc.low++

      return acc
    },
    { total: 0, high: 0, medium: 0, low: 0, totalIncidents: 0, totalSeverity: 0 }
  )

  return {
    total: stats.total,
    high: stats.high,
    medium: stats.medium,
    low: stats.low,
    totalIncidents: stats.totalIncidents,
    avgSeverity: stats.totalSeverity / stats.total
  }
}
