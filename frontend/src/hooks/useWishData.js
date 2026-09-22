import { useEffect, useState } from 'react'
import { API_BASE } from '../constants'

export function useWishData() {
  const [status, setStatus] = useState(null)
  const [pulls, setPulls] = useState([])
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState(null)

  const refresh = async () => {
    const [s, p] = await Promise.all([
      fetch(`${API_BASE}/status`).then((r) => r.json()),
      fetch(`${API_BASE}/pulls`).then((r) => r.json()),
    ])
    setStatus(s)
    setPulls(p)
  }

  useEffect(() => {
    refresh()
    const source = new EventSource(`${API_BASE}/events`)
    source.onmessage = () => refresh()
    source.onerror = () => console.log('SSE connection error, retrying...')
    return () => source.close()
  }, [])

  const syncNow = async () => {
    setSyncing(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/sync-now`, { method: 'POST' })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || 'Sync failed')
      await refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setSyncing(false)
    }
  }

  const exportJson = async () => {
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/export`)
      if (!res.ok) throw new Error('Export failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'wish-history-export.json'
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err.message)
    }
  }

  return { status, pulls, syncing, error, syncNow, exportJson }
}
