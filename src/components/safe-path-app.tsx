"use client"

import { useState } from "react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { MapPin, Navigation, Shield, ChevronRight, Settings, Loader2, AlertCircle } from "lucide-react"
import { Alert, AlertDescription } from "@/components/ui/alert"
import RouteMap from "@/components/route-map"
import LocationInput from "@/components/location-input"
import CrimeAnalytics from "@/components/crime-analytics"
import { Input } from "@/components/ui/input"
import { parseTableauView } from "@/services/tableau"
import { calculateRoutes, isGraphHopperConfigured } from "@/services/graphhopper"
import { saveLocation } from "@/services/savedLocations"

export interface Route {
  id: number
  name: string
  distance: string
  time: string
  safetyScore: number
  totalRisk: number
  crimeRisk: number
  hazardRisk: number
  assessedAt: string
  dataFetchedAt: string
  sources: { policeCalls: number; open311Reports: number }
  coordinates: Array<{ lat: number; lng: number }>
  waypoints: Array<{ name: string; type: string; safe: boolean }>
  color: string
}

export default function SafePathApp() {
  const [origin, setOrigin] = useState("")
  const [destination, setDestination] = useState("")
  const [routeCalculated, setRouteCalculated] = useState(false)
  const [routes, setRoutes] = useState<Route[]>([])
  const [selectedRouteId, setSelectedRouteId] = useState<number>(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [journey, setJourney] = useState<{ origin: string; destination: string } | null>(null)
  const [showDashboardSettings, setShowDashboardSettings] = useState(false)
  const [tableauUrl, setTableauUrl] = useState(() => {
    try { return localStorage.getItem("safepath_tableau_view") || process.env.REACT_APP_TABLEAU_VIEW_URL || "" }
    catch { return process.env.REACT_APP_TABLEAU_VIEW_URL || "" }
  })
  const [tableauDraft, setTableauDraft] = useState("")
  const [tableauError, setTableauError] = useState("")
  const connectTableau = () => {
    try {
      const value = tableauDraft.trim() ? parseTableauView(tableauDraft) : ""
      localStorage.setItem("safepath_tableau_view", value)
      setTableauUrl(value); setTableauError(""); setShowDashboardSettings(false)
    } catch (error) { setTableauError(error instanceof Error ? error.message : "Could not save the dashboard") }
  }

  const handleCalculateRoute = async () => {
    if (!origin || !destination) return

    // Check if the backend routing service is configured
    if (!isGraphHopperConfigured()) {
      setError("Routing service is not configured. Please try again later.")
      return
    }

    setLoading(true)
    setError(null)
    setRouteCalculated(false)

    try {
      const plannedJourney = { origin: origin.trim(), destination: destination.trim() }
      const result = await calculateRoutes(plannedJourney.origin, plannedJourney.destination)

      if (!result) {
        throw new Error("Could not calculate routes. Please check your addresses and try again.")
      }

      setJourney(plannedJourney)
      setRoutes(result.routes)
      setSelectedRouteId(result.routes[0].id)
      setRouteCalculated(true)

      // Save locations to localStorage for future use
      saveLocation(origin)
      saveLocation(destination)
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred while calculating routes")
      console.error("Route calculation error:", err)
    } finally {
      setLoading(false)
    }
  }

  const selectedRoute = routes.find((r) => r.id === selectedRouteId)

  return (
    <div className="min-h-screen gradient-bg">
      {/* Header */}
      <header className="border-b border-border/50 bg-white/80 backdrop-blur-lg shadow-sm">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl gradient-primary shadow-glow">
                <Shield className="h-7 w-7 text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-display font-bold text-gradient">SafePath</h1>
                <p className="text-xs text-muted-foreground font-medium">San Francisco, CA</p>
              </div>
            </div>
            <Button variant="ghost" size="icon" aria-label="Dashboard settings" onClick={() => { setTableauDraft(tableauUrl); setTableauError(""); setShowDashboardSettings(v => !v) }}>
              <Settings className="h-5 w-5 text-foreground/70" />
            </Button>
          </div>
        </div>
      </header>

      <div className="container mx-auto px-4 py-6">
        {showDashboardSettings && <Card className="p-5 mb-6 space-y-3">
          <h2 className="font-semibold">Tableau dashboard settings</h2>
          <p className="text-sm text-muted-foreground">Connect a published Tableau Public dashboard in this browser. Leaving the link empty keeps the built-in crime analytics available.</p>
          <label htmlFor="tableau-url" className="block text-sm font-medium">Published dashboard URL</label>
          <Input id="tableau-url" value={tableauDraft} onChange={e => setTableauDraft(e.target.value)} placeholder="https://public.tableau.com/views/YourWorkbook/YourDashboard" />
          {tableauError && <p role="alert" className="text-sm text-destructive">{tableauError}</p>}
          <Button onClick={connectTableau}>Save dashboard connection</Button>
          <a href={`${process.env.PUBLIC_URL || ""}/tableau/sf-crime-incidents.csv`} download className="block text-sm text-primary">Download crime data for Tableau</a>
        </Card>}
        {/* Top Section - Route Input/Options and Map */}
        <div className="grid gap-6 lg:grid-cols-3 mb-6">
          {/* Left Column - Route Input & Options */}
          <div className="space-y-6 lg:col-span-1">
            {/* Route Input Card */}
            <Card className="p-6 shadow-lg border-2 border-border/50 bg-white/90 backdrop-blur">
              <h2 className="mb-6 text-xl font-display font-bold text-foreground">Plan Your Route</h2>

              <div className="space-y-5">
                <div className="space-y-2">
                  <label className="text-sm font-semibold text-foreground">Starting Point</label>
                  <LocationInput
                    value={origin}
                    onChange={setOrigin}
                    placeholder="Enter your location"
                    icon={<MapPin className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-primary" />}
                    className="focus:border-primary focus:ring-2 focus:ring-primary/20"
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-sm font-semibold text-foreground">Destination</label>
                  <LocationInput
                    value={destination}
                    onChange={setDestination}
                    placeholder="Where are you going?"
                    icon={<Navigation className="absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-accent" />}
                    className="focus:border-accent focus:ring-2 focus:ring-accent/20"
                  />
                </div>

                <Button
                  onClick={handleCalculateRoute}
                  className="w-full h-11 text-base font-semibold gradient-primary shadow-glow-hover transition-all"
                  disabled={!origin || !destination || loading}
                >
                  {loading ? (
                    <>
                      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                      Calculating Routes...
                    </>
                  ) : (
                    <>
                      Compare Route Safety
                      <ChevronRight className="ml-2 h-5 w-5" />
                    </>
                  )}
                </Button>

                {/* Error Display */}
                {error && (
                  <Alert variant="destructive" className="mt-4">
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}
              </div>
            </Card>

            {routeCalculated && routes.length > 0 && (
              <Card className="p-6 shadow-lg border-2 border-border/50 bg-white/90 backdrop-blur">
                <h2 className="mb-5 text-xl font-display font-bold text-foreground">Route Options</h2>
                <p className="mb-4 text-sm text-muted-foreground">
                  Incident safety index: higher means less reported risk, not a guarantee of safety.
                  Based on police calls from the past 72 hours and open 311 safety reports.
                  Scored {new Date(routes[0].assessedAt).toLocaleTimeString()} using data fetched {new Date(routes[0].dataFetchedAt).toLocaleTimeString()}.
                </p>
                {routes[0].sources.policeCalls === 0 && routes[0].sources.open311Reports === 0 && (
                  <p className="mb-4 text-sm text-muted-foreground">
                    No matching reports were returned for this area. An empty result does not establish safety.
                  </p>
                )}
                <div className="space-y-3">
                  {routes.map((route) => (
                    <button
                      key={route.id}
                      onClick={() => setSelectedRouteId(route.id)}
                      className={`w-full rounded-xl border-2 p-4 text-left transition-all duration-200 ${
                        selectedRouteId === route.id
                          ? "border-primary bg-primary/10 shadow-md scale-[1.02]"
                          : "border-border/50 bg-white hover:border-primary/50 hover:shadow-md"
                      }`}
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                          <div className="h-4 w-4 rounded-full shadow-sm" style={{ backgroundColor: route.color }} />
                          <h3 className="font-display font-bold text-foreground">{route.name}</h3>
                        </div>
                        <span
                          className={`text-sm font-bold px-2.5 py-1 rounded-lg ${
                            route.safetyScore >= 90
                              ? "bg-accent/15 text-accent"
                              : route.safetyScore >= 80
                                ? "bg-primary/15 text-primary"
                                : "bg-yellow-500/15 text-yellow-600"
                          }`}
                        >
                          {route.safetyScore}/100
                        </span>
                      </div>
                      <div className="flex gap-4 text-sm text-muted-foreground font-medium">
                        <span>{route.distance}</span>
                        <span>•</span>
                        <span>{route.time}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </Card>
            )}
          </div>

          {/* Right Column - Map */}
          <div className="lg:col-span-2">
            <RouteMap
              routeCalculated={routeCalculated}
              origin={journey?.origin}
              destination={journey?.destination}
              routes={routes}
              selectedRouteId={selectedRouteId}
            />
          </div>
        </div>

        {routeCalculated && selectedRoute && (
          <CrimeAnalytics route={selectedRoute} tableauUrl={tableauUrl} />
        )}
      </div>
    </div>
  )
}
