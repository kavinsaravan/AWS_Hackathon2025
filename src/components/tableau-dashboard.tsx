import { useEffect, useRef, useState } from "react"
import { ExternalLink, Loader2 } from "lucide-react"
import { Card } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import type { AnalyticsBounds } from "@/services/crimeAnalytics"
import { createTableauAreaSync, loadTableauAPI, parseTableauView, type TableauWorkbook } from "@/services/tableau"

type TableauElement = HTMLElement & { workbook: TableauWorkbook }

export default function TableauDashboard({ viewUrl, bounds }: { viewUrl: string; bounds?: AnalyticsBounds }) {
  const host = useRef<HTMLDivElement>(null)
  const latestBounds = useRef(bounds)
  latestBounds.current = bounds
  const sync = useRef<ReturnType<typeof createTableauAreaSync> | null>(null)
  const [status, setStatus] = useState<"loading" | "syncing" | "ready" | "error">("loading")
  const [attempt, setAttempt] = useState(0)
  const [appliedScope, setAppliedScope] = useState("Route area")
  let source = ""
  try { source = viewUrl ? parseTableauView(viewUrl) : "" } catch { /* Invalid configuration is not embedded. */ }

  useEffect(() => {
    if (!source) return
    let active = true, viz: TableauElement | undefined
    setStatus("loading")
    const timeout = window.setTimeout(() => { if (active) setStatus("error") }, 45000)
    const synchronize = () => {
      if (active) sync.current?.request(latestBounds.current)
    }
    const ready = () => {
      if (!active || !viz) return
      window.clearTimeout(timeout)
      sync.current?.dispose()
      sync.current = createTableauAreaSync(viz.workbook, state => {
        if (!active) return
        if (state === "ready") setAppliedScope(latestBounds.current ? "Route area" : "All SF")
        setStatus(state)
      })
      synchronize()
    }
    const failed = () => { if (active) { window.clearTimeout(timeout); sync.current?.dispose(); sync.current = null; setStatus("error") } }
    void loadTableauAPI().then(() => {
      if (!active || !host.current) return
      viz = document.createElement("tableau-viz") as TableauElement
      viz.setAttribute("toolbar", "hidden")
      viz.setAttribute("hide-tabs", "")
      viz.setAttribute("width", "100%")
      viz.setAttribute("height", "740")
      viz.addEventListener("firstinteractive", ready)
      viz.addEventListener("tabswitched", synchronize)
      viz.addEventListener("vizloaderror", failed)
      viz.setAttribute("src", source)
      host.current.replaceChildren(viz)
    }).catch(failed)
    return () => {
      active = false; window.clearTimeout(timeout)
      sync.current?.dispose(); sync.current = null
      if (viz) {
        viz.removeEventListener("firstinteractive", ready)
        viz.removeEventListener("tabswitched", synchronize)
        viz.removeEventListener("vizloaderror", failed)
        viz.remove()
      }
    }
  }, [source, attempt])

  useEffect(() => { sync.current?.request(bounds) }, [bounds])
  if (!viewUrl) return null
  if (!source) return <Card className="p-6"><p>The Tableau dashboard link is invalid. Update it in dashboard settings.</p></Card>

  return <Card className="p-5 md:p-7 shadow-lg bg-white/90" aria-label="Tableau crime dashboard">
    <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
      <div><h2 className="text-xl font-display font-bold">Tableau crime dashboard</h2>
        <p className="text-sm text-muted-foreground mt-1">{status === "ready" ? `${appliedScope} · Historical police incident data` : "Historical police incident data"}</p></div>
      <a href={source} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-primary">Open SF overview in Tableau<ExternalLink className="h-4 w-4" /></a>
    </div>
    <div className="relative min-h-[740px] overflow-hidden rounded-xl border">
      <div ref={host} className={status === "ready" ? "" : "invisible"} />
      {status !== "ready" && <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-slate-50 px-6 text-center" role="status" aria-live="polite">
        {status === "error" ? <><p>The Tableau dashboard could not load or match the selected area.</p><Button variant="outline" onClick={() => setAttempt(n => n + 1)}>Try again</Button></> :
          <><Loader2 className="h-5 w-5 animate-spin text-primary" /><p>{status === "syncing" ? "Updating the dashboard for your selected area…" : "Loading Tableau dashboard…"}</p></>}
      </div>}
    </div>
    <p className="text-xs text-muted-foreground mt-4">This dashboard uses a published data snapshot. Changing routes changes its area filters; it does not fetch new incident records. Route safety scores are calculated separately above. Area boundaries are approximate.</p>
  </Card>
}
