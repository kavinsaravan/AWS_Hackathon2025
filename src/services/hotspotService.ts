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
    console.error('REACT_APP_API_ENDPOINT not configured')
    // Return empty GeoJSON for development
    return {
      type: 'FeatureCollection',
      features: []
    }
  }

  const queryParams = new URLSearchParams({
    eps: eps.toString(),
    min_samples: minSamples.toString(),
    algorithm,
    format
  })

  const url = `${apiEndpoint}/hotspots?${queryParams}`

  try {
    const response = await fetch(url)

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    const data = await response.json()
    return data

  } catch (error) {
    console.error('Error fetching hotspots:', error)

    // Return mock data for development
    return getMockHotspots()
  }
}

/**
 * Mock hotspot data for development/testing
 */
function getMockHotspots(): HotspotGeoJSON {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [-122.4194, 37.7749] // Downtown SF
        },
        properties: {
          id: 1,
          radius_km: 0.35,
          incident_count: 45,
          severity_score: 2.8,
          risk_level: 'High',
          color: '#ef4444',
          top_crimes: [
            { type: 'ROBBERY', count: 15 },
            { type: 'ASSAULT', count: 12 },
            { type: 'THEFT', count: 18 }
          ],
          description: 'High risk area with 45 incidents. Most common: ROBBERY.'
        }
      },
      {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [-122.4080, 37.7853] // Tenderloin
        },
        properties: {
          id: 2,
          radius_km: 0.28,
          incident_count: 38,
          severity_score: 2.5,
          risk_level: 'High',
          color: '#ef4444',
          top_crimes: [
            { type: 'FIGHT NO WEAPON', count: 20 },
            { type: 'SUSPICIOUS PERSON', count: 10 },
            { type: 'ASSAULT', count: 8 }
          ],
          description: 'High risk area with 38 incidents. Most common: FIGHT NO WEAPON.'
        }
      },
      {
        type: 'Feature',
        geometry: {
          type: 'Point',
          coordinates: [-122.4376, 37.7599] // Castro
        },
        properties: {
          id: 3,
          radius_km: 0.22,
          incident_count: 15,
          severity_score: 1.7,
          risk_level: 'Medium',
          color: '#f59e0b',
          top_crimes: [
            { type: 'THEFT', count: 8 },
            { type: 'VANDALISM', count: 4 },
            { type: 'SUSPICIOUS PERSON', count: 3 }
          ],
          description: 'Medium risk area with 15 incidents. Most common: THEFT.'
        }
      }
    ]
  }
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
