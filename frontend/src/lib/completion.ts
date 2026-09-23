export interface Batch {
  ok: number
  bad: number
  title: string
}

export const emptyBatch = (): Batch => ({ ok: 0, bad: 0, title: '' })

/** The sentence shown in the toast and in the desktop notification. Mirrors the backend's wording. */
export function completionMessage(batch: Batch): string {
  if (batch.bad) return `Completed ${batch.ok}, failed ${batch.bad}`
  if (batch.ok === 1) return `Download complete: ${batch.title}`
  return `${batch.ok} downloads completed`
}
