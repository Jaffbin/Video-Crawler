import type { ButtonHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

type Variant = 'default' | 'primary' | 'ghost' | 'danger'

const styles: Record<Variant, string> = {
  default: 'bg-white/[.06] hover:bg-white/[.1] text-zinc-100',
  primary: 'bg-white text-zinc-950 hover:bg-zinc-200',
  ghost: 'bg-transparent hover:bg-white/[.06] text-zinc-300',
  danger: 'bg-red-500/10 text-red-300 hover:bg-red-500/15',
}

export function Button({
  className,
  variant = 'default',
  type = 'button',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-medium transition',
        'disabled:cursor-not-allowed disabled:opacity-40',
        styles[variant],
        className,
      )}
      {...props}
    />
  )
}
