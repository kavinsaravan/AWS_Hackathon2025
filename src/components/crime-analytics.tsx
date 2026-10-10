import { useEffect, useMemo, useState } from "react"
import { BarChart3, Loader2 } from "lucide-react"
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, LineChart, Line } from "recharts"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { routeArea, summarizeCrimeArea, type CrimeSnapshot } from "@/services/crimeAnalytics"
import TableauDashboard from "./tableau-dashboard"
import type { Route } from "./safe-path-app"

export default function CrimeAnalytics({ route, tableauUrl }: { route: Route; tableauUrl: string }) {
  const [snapshot, setSnapshot] = useState<CrimeSnapshot | null>(null)
  const [error, setError] = useState(false)
  const [citywide, setCitywide] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch(`${process.env.PUBLIC_URL || ""}/safety-analytics.json`, { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error("Analytics unavailable"); return r.json() })
      .then(data => {
        if (data.version !== 1 || !Array.isArray(data.cells) || !Array.isArray(data.dates) || !Number.isFinite(Date.parse(data.refreshedUTC))) throw new Error("Invalid analytics")
        setSnapshot(data)
      }).catch(err => { if (err.name !== "AbortError") setError(true) })
    return () => controller.abort()
  }, [])
  const bounds = useMemo(() => citywide ? undefined : routeArea(route.coordinates), [citywide, route.coordinates])
  const summary = useMemo(() => snapshot ? summarizeCrimeArea(snapshot, bounds) : null, [snapshot, bounds])

  return (
    <section className="space-y-6" aria-label="Crime analytics">
      <Card className="p-5 md:p-7 shadow-lg bg-white/90">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
          <div>
            <h2 className="flex items-center gap-2 text-xl font-display font-bold"><BarChart3 className="h-5 w-5 text-primary" />Crime analytics</h2>
            <p className="text-sm text-muted-foreground mt-1">{citywide ? "San Francisco" : "Approximate area around the selected route"}</p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant={citywide ? "outline" : "default"} onClick={() => setCitywide(false)}>Route area</Button>
            <Button size="sm" variant={citywide ? "default" : "outline"} onClick={() => setCitywide(true)}>All SF</Button>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-3 mb-6">
          <div className="rounded-xl bg-primary/5 p-4"><p className="text-xs font-semibold text-muted-foreground">Mapped police records · 90 days</p><p className="text-2xl font-bold mt-2">{summary ? summary.count.toLocaleString() : "—"}</p></div>
          <div className="rounded-xl bg-primary/5 p-4"><p className="text-xs font-semibold text-muted-foreground">Selected route incident index</p><p className="text-2xl font-bold mt-2">{route.safetyScore}<span className="text-sm text-muted-foreground"> / 100</span></p></div>
          <div className="rounded-xl bg-primary/5 p-4"><p className="text-xs font-semibold text-muted-foreground">Route risk breakdown</p><p className="text-sm font-medium mt-2">Police calls: {route.crimeRisk.toFixed(2)}<br />Open 311 reports: {route.hazardRisk.toFixed(2)}</p></div>
        </div>
        {error ? <p className="text-sm text-muted-foreground">Historical analytics are temporarily unavailable. Route safety results are shown above.</p> : !summary ?
          <p className="flex gap-2 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" />Loading area analytics…</p> :
          <div className="grid gap-7 lg:grid-cols-2">
            <div><h3 className="font-semibold mb-4">Most reported categories</h3><div className="h-64">
              <ResponsiveContainer width="100%" height="100%"><BarChart data={summary.categories} layout="vertical" margin={{ left: 10, right: 20 }}>
                <XAxis type="number" allowDecimals={false} /><YAxis dataKey="name" type="category" width={135} tick={{ fontSize: 11 }} /><Tooltip /><Bar dataKey="count" name="Police records" fill="#8b5cf6" radius={[0, 5, 5, 0]} />
              </BarChart></ResponsiveContainer>
            </div></div>
            <div><h3 className="font-semibold mb-4">Reports over time</h3><div className="h-64">
              <ResponsiveContainer width="100%" height="100%"><LineChart data={summary.days} margin={{ left: 0, right: 20 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={v => new Date(v + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })} minTickGap={35} /><YAxis allowDecimals={false} /><Tooltip /><Line type="monotone" dataKey="count" name="Police records" stroke="#06b6d4" strokeWidth={2} dot={false} />
              </LineChart></ResponsiveContainer>
            </div></div>
          </div>}
        <p className="text-xs text-muted-foreground mt-5">{snapshot ? `Historical snapshot updated ${new Date(snapshot.refreshedUTC).toLocaleString()}. ` : ""}Includes records with usable SF coordinates. Area boundaries are approximate. Recent days may be incomplete due to reporting delays. Reported records and the route's incident index describe different measures; neither guarantees personal safety.</p>
      </Card>
      <TableauDashboard viewUrl={tableauUrl} bounds={bounds} />
    </section>
  )
}
