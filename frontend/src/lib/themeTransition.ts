import type { Theme } from '../hooks/useTheme'

interface Point {
  x: number
  y: number
}

let revealId = 0

export function themeReveal(theme: Theme, origin: Point, width: number, height: number) {
  if (theme === 'light') {
    const radius = Math.hypot(Math.max(origin.x, width - origin.x), Math.max(origin.y, height - origin.y))
    return {
      duration: 550,
      keyframes: [
        { clipPath: `circle(0px at ${origin.x}px ${origin.y}px)` },
        { clipPath: `circle(${Math.ceil(radius) + 2}px at ${origin.x}px ${origin.y}px)` },
      ],
      easing: 'cubic-bezier(0.2, 0.65, 0.3, 1)',
    }
  }

  // A fixed spread avoids random clusters and keeps both narrow and wide windows covered.
  const drops = [
    [0.2, 0.12],
    [0.76, 0.28],
    [0.43, 0.46],
    [0.86, 0.7],
    [0.18, 0.85],
  ]
  const radius = Math.hypot(width, height) * 0.42 + 2
  const duration = 760
  const keyframes = Array.from({ length: 39 }, (_, frame) => {
    const time = (frame / 38) * duration
    const circles = drops.map(([x, y], index) => {
      const progress = Math.max(0, Math.min(1, (time - index * 65) / 500))
      const eased = progress * progress * (3 - 2 * progress)
      // Identical SVG commands let the browser interpolate the union of all five circles.
      const r = Math.max(0.01, radius * eased)
      const n = (value: number) => value.toFixed(2)
      return `M ${n(x * width - r)} ${n(y * height)} a ${n(r)} ${n(r)} 0 1 0 ${n(2 * r)} 0 a ${n(r)} ${n(r)} 0 1 0 ${n(-2 * r)} 0 Z`
    })
    return { clipPath: `path("${circles.join(' ')}")`, offset: frame / 38 }
  })
  return { duration, keyframes, easing: 'linear' }
}

/** Reveal the real themed page, leaving media elements and React state mounted. */
export function transitionTheme(theme: Theme, update: () => void, button?: HTMLElement): () => void {
  const root = document.documentElement
  const motion = window.matchMedia?.('(prefers-reduced-motion: reduce)')
  if (
    root.dataset.theme === theme ||
    document.hidden ||
    motion?.matches ||
    typeof document.startViewTransition !== 'function' ||
    typeof root.animate !== 'function' ||
    typeof KeyframeEffect === 'undefined' ||
    !('pseudoElement' in KeyframeEffect.prototype) ||
    !CSS.supports('clip-path', 'path("M 0 0 H 1 V 1 Z")')
  ) {
    update()
    return () => {}
  }

  const bounds = button?.getBoundingClientRect()
  const origin = {
    x: bounds ? bounds.left + bounds.width / 2 : innerWidth / 2,
    y: bounds ? bounds.top + bounds.height / 2 : innerHeight / 2,
  }
  const reveal = themeReveal(theme, origin, innerWidth, innerHeight)
  const token = String(++revealId)
  root.dataset.themeReveal = token
  let canceled = false
  let committed = false
  let animation: Animation | undefined
  let transition: ViewTransition | undefined

  const commit = () => {
    if (canceled || committed) return
    committed = true
    update()
  }
  const cleanup = () => {
    animation?.cancel()
    // A skipped transition can finish after its replacement has already started.
    if (root.dataset.themeReveal === token) delete root.dataset.themeReveal
    window.removeEventListener('resize', interrupt)
    document.removeEventListener('visibilitychange', interrupt)
    motion?.removeEventListener('change', interrupt)
  }
  const cancel = () => {
    canceled = true
    transition?.skipTransition()
    cleanup()
  }
  const interrupt = () => {
    // Resizing or changing motion preferences must still apply the requested theme.
    commit()
    cancel()
  }

  try {
    transition = document.startViewTransition(commit)
  } catch {
    commit()
    cleanup()
    return cancel
  }
  window.addEventListener('resize', interrupt)
  document.addEventListener('visibilitychange', interrupt)
  motion?.addEventListener('change', interrupt)
  void transition.ready.then(
    () => {
      if (canceled) return
      try {
        animation = root.animate(reveal.keyframes, {
          duration: reveal.duration,
          easing: reveal.easing,
          fill: 'both',
          pseudoElement: '::view-transition-new(root)',
        })
        void animation.finished.catch(() => {}) // Cancellation is expected on a second click.
      } catch {
        transition?.skipTransition()
      }
    },
    () => {
      commit() // Hidden windows or unavailable capture must not prevent theme switching.
      cleanup()
    },
  )
  void transition.finished.then(cleanup, cleanup)
  return cancel
}
