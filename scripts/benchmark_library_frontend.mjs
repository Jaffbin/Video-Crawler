/** Run with Node 24+: synthetic library data, no browser or user media access. */
import { performance } from 'node:perf_hooks'
import { writeFileSync } from 'node:fs'
import { filterLibrary } from '../frontend/src/lib/library.ts'

const median = values => values.sort((a, b) => a - b)[Math.floor(values.length / 2)]
function measure(run) {
  const values = []
  for (let index = 0; index < 9; index++) {
    const started = performance.now()
    run()
    values.push(performance.now() - started)
  }
  return Math.round(median(values) * 100) / 100
}
const result = [1000, 10000].map(size => {
  const files = Array.from({ length: size }, (_, index) => ({ name: `video-${index}.mp4`, path: `group/video-${index}.mp4`,
    title: `中文 Video ${index}`, source: 'example.com', kind: 'video', size: index + 1, mtime: index,
    tags: ['sample', `tag-${index % 5}`], note: 'Synthetic library entry' }))
  const selected = files.map(file => file.path)
  return { media: size, query_ms: measure(() => filterLibrary(files, '中文 video 9', '', '', '', '', 'newest')),
    name_sort_ms: measure(() => filterLibrary(files, '', '', '', '', '', 'name')),
    selected_array_ms: measure(() => files.filter(file => selected.includes(file.path))),
    selected_set_ms: measure(() => { const keys = new Set(selected); return files.filter(file => keys.has(file.path)) }) }
})
console.log(JSON.stringify(result, null, 2))
if (process.argv[2]) writeFileSync(process.argv[2], JSON.stringify(result, null, 2))
