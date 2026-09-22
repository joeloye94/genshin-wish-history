import { GACHA_NAMES } from '../constants'

function PullsTable({ pulls }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Time</th>
          <th>Banner</th>
          <th>Name</th>
          <th>Rarity</th>
          <th>Pity</th>
        </tr>
      </thead>
      <tbody>
        {pulls.map((p) => {
          const rankClass = p.rank_type === '5' ? 'rank-5' : p.rank_type === '4' ? 'rank-4' : ''
          const fiftyFiftyClass =
            p.won_fiftyfifty === true ? 'won-fiftyfifty' : p.won_fiftyfifty === false ? 'lost-fiftyfifty' : ''
          return (
            <tr key={p.id} className={[rankClass, fiftyFiftyClass].filter(Boolean).join(' ')}>
              <td>{p.time}</td>
              <td>{GACHA_NAMES[p.gacha_type] || p.gacha_type}</td>
              <td className="name-cell">
                {p.icon_url && <img src={p.icon_url} alt="" className="item-icon" />}
                {p.name}
              </td>
              <td>{p.rank_type}★</td>
              <td>{p.pity}</td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

export default PullsTable
