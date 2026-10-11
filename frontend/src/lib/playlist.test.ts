import { expect, it } from 'vitest'
import { previewSelection } from './playlist'

it('handles explicit, bounded and open ranges using original indices', () => {
  expect(previewSelection([1, 2, 4, 8, 10, 100], '1-4,8,10-')).toEqual([1, 2, 4, 8, 10, 100])
  expect(previewSelection([1, 2], '101-')).toEqual([])
  expect(previewSelection([1, 2], '')).toBeNull()
  expect(previewSelection([1, 2], '2-1')).toBeUndefined()
  expect(previewSelection([1, 2], '1:5:2')).toBeUndefined()
})
