/**
 * Hotspot Toggle Component
 * UI controls for showing/hiding crime hotspots on the map
 */

import { useState, useEffect } from 'react'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { AlertCircle, MapPin, Eye, EyeOff } from 'lucide-react'
import { fetchHotspots, getHotspotStats, type HotspotGeoJSON } from '@/services/hotspotService'

interface HotspotToggleProps {
  onHotspotsChange: (hotspots: HotspotGeoJSON | null) => void
  onVisibilityChange: (visible: boolean) => void
}

export function HotspotToggle({ onHotspotsChange, onVisibilityChange }: HotspotToggleProps) {
  const [loading, setLoading] = useState(false)
  const [hotspots, setHotspots] = useState<HotspotGeoJSON | null>(null)
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch hotspots on component mount
  useEffect(() => {
    loadHotspots()
  }, [])

  const loadHotspots = async () => {
    setLoading(true)
    setError(null)

    try {
      const data = await fetchHotspots({
        eps: 0.3,
        minSamples: 5,
        algorithm: 'dbscan'
      })

      setHotspots(data)
      onHotspotsChange(data)
    } catch (err) {
      console.error('Error loading hotspots:', err)
      setError('Failed to load crime hotspots')
    } finally {
      setLoading(false)
    }
  }

  const toggleVisibility = () => {
    const newVisibility = !visible
    setVisible(newVisibility)
    onVisibilityChange(newVisibility)
  }

  const stats = hotspots ? getHotspotStats(hotspots) : null

  return (
    <Card className="p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertCircle className="h-5 w-5 text-red-500" />
          <h3 className="font-semibold">Crime Hotspots</h3>
        </div>

        <Button
          variant={visible ? "default" : "outline"}
          size="sm"
          onClick={toggleVisibility}
          disabled={loading || !hotspots}
        >
          {visible ? (
            <>
              <Eye className="h-4 w-4 mr-1" />
              Hide
            </>
          ) : (
            <>
              <EyeOff className="h-4 w-4 mr-1" />
              Show
            </>
          )}
        </Button>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="text-sm text-gray-500 flex items-center gap-2">
          <div className="animate-spin h-4 w-4 border-2 border-gray-300 border-t-blue-500 rounded-full" />
          Detecting hotspots...
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="text-sm text-red-600 bg-red-50 p-2 rounded">
          {error}
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="space-y-2">
          <div className="text-sm text-gray-600">
            <div className="flex justify-between mb-1">
              <span>Total Hotspots:</span>
              <span className="font-semibold">{stats.total}</span>
            </div>
            <div className="flex justify-between mb-1">
              <span>Total Incidents:</span>
              <span className="font-semibold">{stats.totalIncidents}</span>
            </div>
          </div>

          {/* Risk Level Breakdown */}
          <div className="flex gap-2">
            {stats.high > 0 && (
              <Badge variant="destructive" className="text-xs">
                <AlertCircle className="h-3 w-3 mr-1" />
                {stats.high} High
              </Badge>
            )}
            {stats.medium > 0 && (
              <Badge className="text-xs bg-orange-500 hover:bg-orange-600">
                <AlertCircle className="h-3 w-3 mr-1" />
                {stats.medium} Medium
              </Badge>
            )}
            {stats.low > 0 && (
              <Badge className="text-xs bg-yellow-500 hover:bg-yellow-600">
                <AlertCircle className="h-3 w-3 mr-1" />
                {stats.low} Low
              </Badge>
            )}
          </div>

          {/* Description */}
          <div className="text-xs text-gray-500 pt-2 border-t">
            Hotspots identified using DBSCAN clustering algorithm.
            Click circles on map for details.
          </div>
        </div>
      )}

      {/* Refresh Button */}
      {hotspots && (
        <Button
          variant="outline"
          size="sm"
          onClick={loadHotspots}
          disabled={loading}
          className="w-full text-xs"
        >
          <MapPin className="h-3 w-3 mr-1" />
          Refresh Hotspots
        </Button>
      )}
    </Card>
  )
}
