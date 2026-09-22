function SyncControls({ status, fiveStars, syncing, error, syncNow, exportJson }) {
  return (
    <>
      <button type="button" onClick={syncNow} disabled={syncing} className="sync-button">
        {syncing ? 'Syncing...' : 'Sync now'}
      </button>
      <button type="button" onClick={exportJson} className="sync-button">
        Export JSON
      </button>
      <p className="sync-note">
        Requires the game to have been launched and Wish → History opened in-game this session.
      </p>
      {error && <p className="error">{error}</p>}

      {status && (
        <div className="status">
          <span>Total pulls: {status.total_pulls}</span>
          <span>5-star pulls: {fiveStars}</span>
          <span>Last fetch: {status.last_fetch_at || 'never'}</span>
          <span>
            Status:{' '}
            {status.last_status === 'authkey_expired'
              ? 'authkey expired, reopen Wish History in-game and Sync now'
              : status.last_status || 'no authkey yet'}
          </span>
        </div>
      )}
    </>
  )
}

export default SyncControls
