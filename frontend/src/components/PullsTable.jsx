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
        </tr>
      </thead>
      <tbody>
        {pulls.map((p) => (
          <tr key={p.id} className={p.rank_type === '5' ? 'rank-5' : p.rank_type === '4' ? 'rank-4' : ''}>
            <td>{p.time}</td>
            <td>{GACHA_NAMES[p.gacha_type] || p.gacha_type}</td>
            <td className="name-cell">
              {p.icon_url && <img src={p.icon_url} alt="" className="item-icon" />}
              {p.name}
            </td>
            <td>{p.rank_type}★</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default PullsTable
