import { useState } from 'react'
import './App.css'
import { useWishData } from './hooks/useWishData'
import FilterBar from './components/FilterBar'
import PullsTable from './components/PullsTable'
import SyncControls from './components/SyncControls'

function App() {
  const { status, pulls, syncing, error, syncNow, exportJson } = useWishData()
  const [bannerFilter, setBannerFilter] = useState('all')
  const [rarityFilter, setRarityFilter] = useState('all')

  const fiveStars = pulls.filter((p) => p.rank_type === '5').length
  const filteredPulls = pulls.filter(
    (p) =>
      (bannerFilter === 'all' || p.gacha_type === bannerFilter) &&
      (rarityFilter === 'all' || p.rank_type === rarityFilter),
  )

  return (
    <div className="container">
      <h1>Genshin Wish History</h1>

      <SyncControls
        status={status}
        fiveStars={fiveStars}
        syncing={syncing}
        error={error}
        syncNow={syncNow}
        exportJson={exportJson}
      />

      <FilterBar
        bannerFilter={bannerFilter}
        setBannerFilter={setBannerFilter}
        rarityFilter={rarityFilter}
        setRarityFilter={setRarityFilter}
      />

      <PullsTable pulls={filteredPulls} />
    </div>
  )
}

export default App
