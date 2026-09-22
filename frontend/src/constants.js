export const API_BASE = 'http://localhost:8000'

export const GACHA_NAMES = {
  '100': 'Beginner',
  '200': 'Permanent',
  '301': 'Character Event',
  '302': 'Weapon Event',
  '500': 'Chronicled',
}

export const BANNER_FILTERS = [
  { value: 'all', label: 'All' },
  { value: '301', label: 'Character' },
  { value: '302', label: 'Weapon' },
  { value: '500', label: 'Chronicled' },
  { value: '200', label: 'Standard' },
]

export const RARITY_FILTERS = [
  { value: 'all', label: 'All' },
  { value: '5', label: '5★' },
  { value: '4', label: '4★' },
  { value: '3', label: '3★' },
]
