/** Channel accent colours, sampled from avatars. RGB triples as "r g b" strings for CSS. */

export type Rgb = [number, number, number]

const cache = new Map<string, Promise<Rgb | null>>()

function rgbToHsl([r, g, b]: Rgb): [number, number, number] {
  r /= 255
  g /= 255
  b /= 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return [0, 0, l]
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  const h =
    max === r
      ? ((g - b) / d + (g < b ? 6 : 0)) / 6
      : max === g
        ? ((b - r) / d + 2) / 6
        : ((r - g) / d + 4) / 6
  return [h, s, l]
}

function hslToRgb(h: number, s: number, l: number): Rgb {
  const hue = (p: number, q: number, t: number) => {
    if (t < 0) t += 1
    if (t > 1) t -= 1
    if (t < 1 / 6) return p + (q - p) * 6 * t
    if (t < 1 / 2) return q
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
    return p
  }
  if (s === 0) return [l * 255, l * 255, l * 255].map(Math.round) as Rgb
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s
  const p = 2 * l - q
  return [hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3)].map((v) =>
    Math.round(v * 255),
  ) as Rgb
}

/** Make any sampled colour usable as an accent on both themes. */
export function normalize(rgb: Rgb): Rgb {
  const [h, s, l] = rgbToHsl(rgb)
  if (s < 0.12) return hslToRgb(h, 0.08, 0.58) // greyscale logos stay neutral
  return hslToRgb(h, Math.max(0.5, Math.min(s, 0.85)), Math.max(0.48, Math.min(l, 0.62)))
}

function luminance(rgb: Rgb): number {
  const [r, g, b] = rgb.map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }) as Rgb
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

export function contrast(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * The channel colour adjusted to be readable as text on `surface` (WCAG 4.5:1): lighter on
 * dark surfaces, darker on light ones. Hue and saturation are kept.
 */
export function ink(rgb: Rgb, surface: Rgb): Rgb {
  const [h, s, l0] = rgbToHsl(rgb)
  const step = luminance(surface) > 0.5 ? -0.02 : 0.02
  let l = l0
  let out = rgb
  while (contrast(out, surface) < 4.5 && l > 0.05 && l < 0.95) {
    l += step
    out = hslToRgb(h, s, l)
  }
  return out
}

/** A darker, slightly hue-shifted partner for gradients. */
export function companion(rgb: Rgb): Rgb {
  const [h, s, l] = rgbToHsl(rgb)
  return hslToRgb((h + 0.07) % 1, s, Math.max(0.28, l - 0.18))
}

export function hexToRgb(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

/** Dominant "vivid" colour of an image: pixels weighted by saturation, so logos beat backgrounds. */
export function sampleImage(url: string): Promise<Rgb | null> {
  const hit = cache.get(url)
  if (hit) return hit
  const job = new Promise<Rgb | null>((resolve) => {
    const img = new Image()
    img.decoding = 'async'
    img.onload = () => {
      try {
        const size = 24
        const canvas = document.createElement('canvas')
        canvas.width = canvas.height = size
        const ctx = canvas.getContext('2d', { willReadFrequently: true })
        if (!ctx) return resolve(null)
        ctx.drawImage(img, 0, 0, size, size)
        const data = ctx.getImageData(0, 0, size, size).data
        let r = 0
        let g = 0
        let b = 0
        let weight = 0
        for (let i = 0; i < data.length; i += 4) {
          const px: Rgb = [data[i]!, data[i + 1]!, data[i + 2]!]
          const [, s, l] = rgbToHsl(px)
          const w = (data[i + 3]! / 255) * (0.05 + s * s) * (1 - Math.abs(l - 0.5) * 1.2)
          r += px[0] * w
          g += px[1] * w
          b += px[2] * w
          weight += w
        }
        resolve(weight > 0 ? ([r / weight, g / weight, b / weight].map(Math.round) as Rgb) : null)
      } catch {
        resolve(null) // tainted canvas or decode error
      }
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
  cache.set(url, job)
  return job
}

export const css = (rgb: Rgb) => rgb.join(' ')
