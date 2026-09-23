/**
 * Pull links out of arbitrary pasted or dropped text.
 *
 * The character class stops at whitespace, quotes, brackets and Chinese full-width punctuation, so
 * "看这个https://example.com/v?id=1，谢谢" yields exactly the link. Do not add "." or "," to the class:
 * that would cut every link at its first dot.
 */
const URL_PATTERN = /https?:\/\/[^\s"'<>\\)\]，。）】]+/gi

export function extractUrls(text: string): string[] {
  const found = (text.match(URL_PATTERN) ?? []).map((u) => u.replace(/[.,;、]+$/, ''))
  return [...new Set(found)]
}

/** One URL per line, ignoring blank lines and "# comments". */
export function readUrls(text: string): string[] {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith('#'))
}

/** Append links that are not already in the box. */
export function mergeUrls(existing: string, incoming: string[]): { text: string; added: number } {
  const have = new Set(readUrls(existing))
  const fresh = incoming.filter((u) => !have.has(u))
  if (!fresh.length) return { text: existing, added: 0 }
  const base = existing.trim() ? existing.replace(/\s*$/, '\n') : ''
  return { text: `${base}${fresh.join('\n')}\n`, added: fresh.length }
}

const TEXT_FILE = /\.(txt|csv|md|list|url|webloc|json|html?)$/i

export function looksLikeTextFile(file: Pick<File, 'name' | 'type'>): boolean {
  return file.type.startsWith('text/') || TEXT_FILE.test(file.name)
}
