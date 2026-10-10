import { Card } from "@/components/ui/card"
import type { Route } from "./safe-path-app"

export default function SafetyFactors({ route }: { route: Route }) {
  return (
    <Card className="p-6 space-y-3">
      <h2 className="text-xl font-bold">Reported Incident Risk</h2>
      <p>Police call risk: {route.crimeRisk.toFixed(2)}</p>
      <p>Open 311 report risk: {route.hazardRisk.toFixed(2)}</p>
      <p>Combined risk: {route.totalRisk.toFixed(2)} (lower is better)</p>
      <p className="text-sm text-muted-foreground">
        {route.sources.policeCalls} police calls and {route.sources.open311Reports} open 311 reports
        retrieved for the area. Reports are weighted by severity, age, and distance from the route.
      </p>
    </Card>
  )
}
