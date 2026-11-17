export function compactNumber(value: number, locale: string): string {
  return new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }).format(
    value,
  )
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 365 * 24 * 3600],
  ['month', 30 * 24 * 3600],
  ['week', 7 * 24 * 3600],
  ['day', 24 * 3600],
  ['hour', 3600],
  ['minute', 60],
]

export function relativeTime(iso: string, locale: string, now = Date.now()): string {
  const seconds = (new Date(iso).getTime() - now) / 1000
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto', style: 'short' })
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.trunc(seconds / size), unit)
  }
  return rtf.format(0, 'minute')
}

/** Age as a bare amount, e.g. "10 мес." / "10 mths" — for figures labelled elsewhere. */
export function ageShort(iso: string, locale: string, now = Date.now()): string {
  const seconds = Math.max(0, (now - new Date(iso).getTime()) / 1000)
  const unitFmt = (unit: string, n: number) =>
    new Intl.NumberFormat(locale, { style: 'unit', unit, unitDisplay: 'short' }).format(n)
  for (const [unit, size] of UNITS) {
    if (seconds >= size) return unitFmt(unit, Math.floor(seconds / size))
  }
  return unitFmt('minute', 1)
}

/** Short month names for the pulse axis: [26 weeks ago, 13 weeks ago, now]. */
export function pulseAxis(locale: string, now = new Date()): string[] {
  const fmt = new Intl.DateTimeFormat(locale, { month: 'short' })
  return [26, 13, 0].map((w) => fmt.format(new Date(now.getTime() - w * 7 * 86_400_000)))
}

export function fullDate(iso: string, locale: string): string {
  return new Date(iso).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' })
}

export function initials(title: string): string {
  const words = title.split(/\s+/).filter((w) => /[\p{L}\p{N}]/u.test(w[0] ?? ''))
  return (
    words
      .slice(0, 2)
      .map((w) => w[0])
      .join('')
      .toUpperCase() || '?'
  )
}

const PALETTE = [
  '#e17076',
  '#7bc862',
  '#e5ca77',
  '#65aadd',
  '#a695e7',
  '#ee7aae',
  '#6ec9cb',
  '#faa774',
]

export function colorFor(id: number): string {
  return PALETTE[Math.abs(id) % PALETTE.length]!
}
