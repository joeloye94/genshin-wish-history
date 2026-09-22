import { BANNER_FILTERS, RARITY_FILTERS } from '../constants'

function FilterBar({ bannerFilter, setBannerFilter, rarityFilter, setRarityFilter }) {
  return (
    <>
      <div className="filter-group">
        <span className="filter-label">Banner:</span>
        <div className="banner-filter">
          {BANNER_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              className={bannerFilter === f.value ? 'active' : ''}
              onClick={() => setBannerFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="filter-group">
        <span className="filter-label">Rarity:</span>
        <div className="banner-filter">
          {RARITY_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              className={rarityFilter === f.value ? 'active' : ''}
              onClick={() => setRarityFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
    </>
  )
}

export default FilterBar
