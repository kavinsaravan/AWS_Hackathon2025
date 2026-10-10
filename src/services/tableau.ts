import type { AnalyticsBounds } from "./crimeAnalytics"

export interface TableauWorksheet {
  applyRangeFilterAsync(field: string, options: { min: number; max: number }): Promise<unknown>
  clearFilterAsync(field: string): Promise<unknown>
}
export interface TableauWorkbook {
  activeSheet: TableauWorksheet | { worksheets: TableauWorksheet[] }
}
export type TableauSyncState = "syncing" | "ready" | "error"

export function parseTableauView(value: string): string {
  const url = new URL(value.trim())
  if (url.protocol !== "https:" || url.hostname !== "public.tableau.com" || url.port || url.username || url.password) {
    throw new Error("Use a published view link from https://public.tableau.com.")
  }
  const match = url.pathname.match(/^\/views\/([^/]+)\/([^/]+)\/?$/) ||
    url.pathname.match(/^\/app\/profile\/[^/]+\/viz\/([^/]+)\/([^/]+)\/?$/)
  if (!match) throw new Error("Paste the published dashboard link, rather than your profile or editor link.")
  const names = match.slice(1).map(part => decodeURIComponent(part))
  if (names.some(part => !/^[\w. -]+$/.test(part) || part === "." || part === "..")) {
    throw new Error("This Tableau view link is invalid.")
  }
  return `https://public.tableau.com/views/${names.map(encodeURIComponent).join("/")}`
}

export async function applyTableauArea(workbook: TableauWorkbook, bounds?: AnalyticsBounds) {
  if (bounds && (!Object.values(bounds).every(Number.isFinite) || bounds.north < bounds.south || bounds.east < bounds.west)) {
    throw new Error("Invalid route area")
  }
  const active = workbook.activeSheet
  const worksheets = "worksheets" in active ? active.worksheets : [active]
  if (!worksheets.length) throw new Error("The Tableau view has no worksheets")
  // Range filters are worksheet operations; dashboards only support categorical filters.
  // Update every sheet, including charts that do not display the coordinates.
  for (const sheet of worksheets) {
    if (bounds) {
      await sheet.applyRangeFilterAsync("Latitude", { min: bounds.south, max: bounds.north })
      await sheet.applyRangeFilterAsync("Longitude", { min: bounds.west, max: bounds.east })
    } else {
      await sheet.clearFilterAsync("Latitude")
      await sheet.clearFilterAsync("Longitude")
    }
  }
}

export function createTableauAreaSync(workbook: TableauWorkbook, onState: (state: TableauSyncState) => void) {
  let running = false, disposed = false, revision = 0, pending = false
  let latest: AnalyticsBounds | undefined
  async function drain() {
    if (running || disposed) return
    running = true
    while (pending && !disposed) {
      pending = false
      const current = revision, bounds = latest
      onState("syncing")
      try {
        await applyTableauArea(workbook, bounds)
        if (!disposed && current === revision) onState("ready")
      } catch {
        if (!disposed && current === revision) onState("error")
      }
    }
    running = false
  }
  return {
    request(bounds?: AnalyticsBounds) {
      latest = bounds ? { ...bounds } : undefined
      revision += 1; pending = true
      void drain()
    },
    dispose() { disposed = true },
  }
}

let apiLoading: Promise<void> | undefined
export function loadTableauAPI(): Promise<void> {
  if (customElements.get("tableau-viz")) return Promise.resolve()
  if (!apiLoading) {
    apiLoading = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script")
      script.type = "module"
      script.src = "https://public.tableau.com/javascripts/api/tableau.embedding.3.latest.min.js"
      const timeout = window.setTimeout(() => fail(), 20000)
      function fail() { window.clearTimeout(timeout); script.remove(); reject(new Error("Tableau could not load")) }
      script.onerror = fail
      script.onload = () => {
        if (customElements.get("tableau-viz")) { window.clearTimeout(timeout); resolve() }
        else fail()
      }
      document.head.appendChild(script)
    }).catch(error => { apiLoading = undefined; throw error })
  }
  return apiLoading
}
