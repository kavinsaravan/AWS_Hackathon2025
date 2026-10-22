/**
 * Hotspot Layer Component
 * Displays crime hotspots as circles on the Leaflet map
 */

import { Circle, Popup, Tooltip } from 'react-leaflet'
import type { HotspotGeoJSON } from '@/services/hotspotService'

interface HotspotLayerProps {
  hotspots: HotspotGeoJSON
  visible: boolean
}

export function HotspotLayer({ hotspots, visible }: HotspotLayerProps) {
  if (!visible || !hotspots.features.length) {
    return null
  }

  return (
    <>
      {hotspots.features.map((feature) => {
        const [lng, lat] = feature.geometry.coordinates
        const props = feature.properties

        // Convert radius from km to meters for Leaflet
        const radiusMeters = props.radius_km * 1000

        // Opacity based on risk level
        const opacity = props.risk_level === 'High' ? 0.4 :
                       props.risk_level === 'Medium' ? 0.3 : 0.2

        const fillOpacity = props.risk_level === 'High' ? 0.2 :
                           props.risk_level === 'Medium' ? 0.15 : 0.1

        return (
          <Circle
            key={feature.properties.id}
            center={[lat, lng]}
            radius={radiusMeters}
            pathOptions={{
              color: props.color,
              fillColor: props.color,
              weight: 2,
              opacity: opacity,
              fillOpacity: fillOpacity
            }}
          >
            {/* Tooltip on hover */}
            <Tooltip>
              <div className="text-sm">
                <strong className={`font-bold ${
                  props.risk_level === 'High' ? 'text-red-600' :
                  props.risk_level === 'Medium' ? 'text-orange-600' :
                  'text-yellow-600'
                }`}>
                  {props.risk_level} Risk Area
                </strong>
                <div className="mt-1">
                  <div>{props.incident_count} incidents</div>
                  <div>Severity: {props.severity_score.toFixed(1)}/3.0</div>
                </div>
              </div>
            </Tooltip>

            {/* Popup on click */}
            <Popup>
              <div className="min-w-[250px]">
                {/* Header */}
                <div className="border-b pb-2 mb-2">
                  <h3 className="font-bold text-lg flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: props.color }}
                    />
                    Crime Hotspot #{props.id}
                  </h3>
                  <div className={`text-sm font-semibold ${
                    props.risk_level === 'High' ? 'text-red-600' :
                    props.risk_level === 'Medium' ? 'text-orange-600' :
                    'text-yellow-600'
                  }`}>
                    {props.risk_level} Risk Level
                  </div>
                </div>

                {/* Statistics */}
                <div className="space-y-2 text-sm mb-3">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Total Incidents:</span>
                    <span className="font-semibold">{props.incident_count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Severity Score:</span>
                    <span className="font-semibold">{props.severity_score.toFixed(2)} / 3.0</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Coverage Area:</span>
                    <span className="font-semibold">{props.radius_km.toFixed(2)} km radius</span>
                  </div>
                </div>

                {/* Top Crimes */}
                <div>
                  <div className="text-xs font-semibold text-gray-700 mb-1">
                    Most Common Incidents:
                  </div>
                  <div className="space-y-1">
                    {props.top_crimes.slice(0, 3).map((crime, idx) => (
                      <div
                        key={idx}
                        className="flex justify-between text-xs bg-gray-50 px-2 py-1 rounded"
                      >
                        <span className="truncate">{crime.type}</span>
                        <span className="font-semibold ml-2">{crime.count}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Description */}
                <div className="mt-3 text-xs text-gray-600 border-t pt-2">
                  {props.description}
                </div>
              </div>
            </Popup>
          </Circle>
        )
      })}
    </>
  )
}
