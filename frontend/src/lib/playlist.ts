/** Resolve supported ranges against displayed indices without expanding unbounded ranges. */
export function previewSelection(indices: number[], range: string): number[] | null | undefined {
  if (!range.trim()) return null
  const parts = range.split(',').map((part) => /^(\d+)(?:-(\d*))?$/.exec(part.trim()))
  if (parts.some((part) => !part || Number(part[1]) < 1 || (part[2] && Number(part[2]) < Number(part[1]))))
    return undefined
  return indices.filter((index) =>
    parts.some((part) => {
      const first = Number(part![1])
      const last = part![2] === undefined ? first : part![2] === '' ? Infinity : Number(part![2])
      return index >= first && index <= last
    }),
  )
}
