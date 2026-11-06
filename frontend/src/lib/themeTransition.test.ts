import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { themeReveal, transitionTheme } from './themeTransition'

function deferred() {
  let resolve!: () => void
  let reject!: (error: Error) => void
  const promise = new Promise<void>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

function fixture() {
  const ready = deferred()
  const finished = deferred()
  const animationDone = deferred()
  const cancelAnimation = vi.fn(() => animationDone.reject(new Error('Canceled')))
  const animate = vi.fn(() => ({ finished: animationDone.promise, cancel: cancelAnimation }))
  const skipTransition = vi.fn(() => finished.resolve())
  let commit!: () => void
  const start = vi.fn((update: () => void) => {
    commit = update
    return { ready: ready.promise, finished: finished.promise, skipTransition }
  })
  Object.defineProperty(document, 'startViewTransition', { configurable: true, value: start })
  Object.defineProperty(document.documentElement, 'animate', { configurable: true, value: animate })
  vi.stubGlobal('CSS', { supports: () => true })
  class Effect {
    get pseudoElement() {
      return null
    }
  }
  vi.stubGlobal('KeyframeEffect', Effect)
  const motion = new EventTarget()
  vi.stubGlobal('matchMedia', () => Object.assign(motion, { matches: false }))
  return {
    ready,
    finished,
    animationDone,
    cancelAnimation,
    animate,
    skipTransition,
    start,
    motion,
    commit: () => commit(),
  }
}

beforeEach(() => {
  document.documentElement.dataset.theme = 'dark'
})
afterEach(() => {
  Reflect.deleteProperty(document, 'startViewTransition')
  Reflect.deleteProperty(document.documentElement, 'animate')
  delete document.documentElement.dataset.theme
  delete document.documentElement.dataset.themeReveal
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

it('starts the light reveal at the button center and reaches every viewport corner', () => {
  const reveal = themeReveal('light', { x: 900, y: 35 }, 1000, 700)
  expect(reveal.keyframes[0].clipPath).toBe('circle(0px at 900px 35px)')
  const radius = Number(reveal.keyframes.at(-1)!.clipPath.match(/circle\(([\d.]+)px/)![1])
  for (const x of [0, 1000]) {
    for (const y of [0, 700]) expect(Math.hypot(x - 900, y - 35)).toBeLessThan(radius)
  }
  expect(reveal.duration).toBeLessThanOrEqual(600)
})

it.each([
  [320, 600],
  [1180, 860],
  [2560, 400],
  [320, 2000],
])('covers the whole %s × %s viewport with staggered rain circles', (width, height) => {
  const reveal = themeReveal('dark', { x: 0, y: 0 }, width, height)
  const circles = (frame: number) =>
    Array.from(
      reveal.keyframes[frame].clipPath.matchAll(/M ([-\d.]+) ([-\d.]+) a ([\d.]+)/g),
      ([, left, y, r]) => ({ x: Number(left) + Number(r), y: Number(y), r: Number(r) }),
    )
  const first = circles(0)
  const early = circles(4)
  expect(first).toHaveLength(5)
  expect(first.every(({ r }) => r < 1)).toBe(true)
  expect(early[0].r).toBeGreaterThan(early[1].r)
  expect(early[2].r).toBeLessThan(1)
  const last = circles(reveal.keyframes.length - 1)
  for (let column = 0; column <= 20; column++) {
    for (let row = 0; row <= 20; row++) {
      expect(
        last.some(({ x, y, r }) => Math.hypot((width * column) / 20 - x, (height * row) / 20 - y) < r),
      ).toBe(true)
    }
  }
  expect(reveal.duration).toBeLessThanOrEqual(850)
})

it('commits after capture, animates the new snapshot and releases the finished effect', async () => {
  const f = fixture()
  const update = vi.fn()
  const button = document.createElement('button')
  vi.spyOn(button, 'getBoundingClientRect').mockReturnValue({
    left: 100,
    top: 20,
    width: 104,
    height: 44,
  } as DOMRect)
  transitionTheme('light', update, button)
  expect(update).not.toHaveBeenCalled()
  f.commit()
  expect(update).toHaveBeenCalledOnce()
  f.ready.resolve()
  await Promise.resolve()
  expect(f.animate).toHaveBeenCalledWith(
    expect.arrayContaining([{ clipPath: 'circle(0px at 152px 42px)' }]),
    expect.objectContaining({ pseudoElement: '::view-transition-new(root)', duration: 550 }),
  )
  f.animationDone.resolve()
  f.finished.resolve()
  await Promise.resolve()
  expect(f.cancelAnimation).toHaveBeenCalledOnce()
  window.dispatchEvent(new Event('resize'))
  expect(f.skipTransition).not.toHaveBeenCalled()
})

it('cancels a superseded transition without applying its stale theme callback', async () => {
  const f = fixture()
  const update = vi.fn()
  const cancel = transitionTheme('light', update)
  cancel()
  f.commit()
  f.ready.reject(new Error('Skipped'))
  await Promise.resolve()
  expect(update).not.toHaveBeenCalled()
  expect(f.animate).not.toHaveBeenCalled()
  expect(f.skipTransition).toHaveBeenCalledOnce()
})

it.each(['resize', 'visibilitychange', 'change'])('finishes the requested theme on %s', async (event) => {
  const f = fixture()
  const update = vi.fn()
  transitionTheme('light', update)
  const target = event === 'resize' ? window : event === 'visibilitychange' ? document : f.motion
  target.dispatchEvent(new Event(event))
  expect(update).toHaveBeenCalledOnce()
  expect(f.skipTransition).toHaveBeenCalledOnce()
  f.commit()
  f.ready.resolve()
  await Promise.resolve()
  expect(f.animate).not.toHaveBeenCalled()
})

it('applies the choice when capture fails and falls back if animation creation fails', async () => {
  let f = fixture()
  const update = vi.fn()
  transitionTheme('light', update)
  f.ready.reject(new Error('Capture unavailable'))
  f.finished.resolve()
  await Promise.resolve()
  f.commit()
  expect(update).toHaveBeenCalledOnce()

  f = fixture()
  f.animate.mockImplementation(() => {
    throw new Error('Animation unavailable')
  })
  transitionTheme('light', update)
  f.commit()
  f.ready.resolve()
  await Promise.resolve()
  expect(update).toHaveBeenCalledTimes(2)
  expect(f.skipTransition).toHaveBeenCalledOnce()
})

it('switches directly when reduced motion is requested or the API is unavailable', () => {
  const f = fixture()
  const update = vi.fn()
  vi.stubGlobal('matchMedia', () => ({ matches: true }))
  transitionTheme('light', update)
  expect(update).toHaveBeenCalledOnce()
  expect(f.start).not.toHaveBeenCalled()
  Reflect.deleteProperty(document, 'startViewTransition')
  vi.stubGlobal('matchMedia', () => ({ matches: false }))
  transitionTheme('light', update)
  expect(update).toHaveBeenCalledTimes(2)
})

it('releases capture styling if starting a transition throws', () => {
  const f = fixture()
  f.start.mockImplementation(() => {
    throw new Error('Capture unavailable')
  })
  const update = vi.fn()
  transitionTheme('light', update)
  expect(update).toHaveBeenCalledOnce()
  expect(document.documentElement).not.toHaveAttribute('data-theme-reveal')
})

it('does not let an old completion remove a replacement transition’s capture styling', async () => {
  const old = fixture()
  const cancel = transitionTheme('light', vi.fn())
  cancel()
  const next = fixture()
  const stop = transitionTheme('light', vi.fn())
  const token = document.documentElement.dataset.themeReveal
  old.ready.reject(new Error('Skipped'))
  await Promise.resolve()
  expect(document.documentElement.dataset.themeReveal).toBe(token)
  next.ready.resolve()
  stop()
  await Promise.resolve()
  expect(document.documentElement).not.toHaveAttribute('data-theme-reveal')
})
