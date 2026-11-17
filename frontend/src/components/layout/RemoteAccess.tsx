import { Smartphone, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import {
  changeRemoteAccess,
  getRemoteAccess,
  type RemoteAccessChange,
  type RemoteAccessStatus,
} from '../../api/client'
import { useI18n } from '../../i18n'
import { Button } from '../ui/Button'
import { HelpButton, HelpNote, useHelpTip } from '../ui/HelpTip'

const LOOPBACK = 'loopback'

/**
 * Lets paired phones add downloads, follow the queue and play Library media through a separate,
 * opt-in listener. Hidden in clients that may not manage it (such as the Chrome extension).
 */
export function RemoteAccess({ onError }: { onError?: (message: string) => void }) {
  const { t, locale } = useI18n()
  const tip = useHelpTip()
  const [status, setStatus] = useState<RemoteAccessStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [bind, setBind] = useState(LOOPBACK)
  const [port, setPort] = useState('')
  const [hosts, setHosts] = useState('')
  const [message, setMessage] = useState('')

  function show(result: RemoteAccessStatus) {
    setStatus(result)
    setBind(result.bind)
    setPort(String(result.port))
    setHosts(result.trusted_hosts.join(' '))
  }

  useEffect(() => {
    let stop = false
    getRemoteAccess()
      .then((result) => {
        if (!stop) show(result)
      })
      .catch(() => {
        /* Stays hidden when the app does not answer or this client may not manage remote access. */
      })
    return () => {
      stop = true
    }
  }, [])

  // While a pairing code is shown, watch for the phone that uses it.
  const waiting = Boolean(status?.pairing)
  useEffect(() => {
    if (!waiting) return
    const timer = window.setInterval(() => {
      getRemoteAccess()
        .then((result) => {
          setStatus(result)
        })
        .catch(() => {})
    }, 3000)
    return () => window.clearInterval(timer)
  }, [waiting])

  if (status === null) return null

  async function change(request: RemoteAccessChange) {
    setBusy(true)
    setMessage('')
    try {
      show(await changeRemoteAccess(request))
      if (request.action === 'configure') setMessage(t('Saved.'))
    } catch (error) {
      const text = error instanceof Error ? error.message : t('That did not work')
      setMessage(text)
      onError?.(text)
    } finally {
      setBusy(false)
    }
  }

  const dirty =
    bind !== status.bind || port !== String(status.port) || hosts.trim() !== status.trusted_hosts.join(' ')
  const date = (seconds: number) =>
    new Date(seconds * 1000).toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' })

  return (
    <section className="grid gap-2" aria-label={t('Remote access')}>
      <div className="flex items-center gap-2">
        <h3 className="min-w-0 flex-1 text-sm font-medium text-zinc-100">{t('Remote access')}</h3>
        <HelpButton tip={tip} about={t('Remote access')} />
      </div>
      <HelpNote tip={tip}>
        {t(
          'Lets phones you pair add downloads, follow the queue and play your Library. Paired phones cannot change settings, delete files or see your cookies. Use Tailscale to reach this computer securely from anywhere, or your home Wi-Fi.',
        )}
      </HelpNote>
      <p className="text-sm text-zinc-300">
        {!status.enabled
          ? t('Off. Phones cannot connect.')
          : status.error === 'port_busy'
            ? t('Could not start: port {port} is in use. Choose another port.', { port: status.port })
            : status.error === 'address_missing'
              ? t('Could not start: this computer no longer has the address {address}. Choose another.', {
                  address: status.bind,
                })
              : status.urls.length
                ? t('On. Open on your phone: {urls}', { urls: status.urls.join(', ') })
                : t(
                    'On, for this computer only (port {port}). Point Tailscale Serve or another reverse proxy at it, then add its host name below.',
                    { port: status.port },
                  )}
      </p>
      {status.enabled && status.bind !== LOOPBACK && (
        <p className="rounded-xl bg-amber-500/[.08] p-3 text-sm text-amber-100" role="note">
          {t(
            'Home network connections are not encrypted: anyone on the same Wi-Fi could read what a phone sends and watches. Use this only on a network you trust, or use Tailscale.',
          )}
        </p>
      )}
      <Button disabled={busy} onClick={() => void change({ action: status.enabled ? 'disable' : 'enable' })}>
        {t(status.enabled ? 'Turn off remote access' : 'Turn on remote access')}
      </Button>

      {status.enabled && (
        <>
          <form
            className="grid gap-2 rounded-xl bg-white/5 p-3"
            onSubmit={(event) => {
              event.preventDefault()
              void change({
                action: 'configure',
                bind,
                port: Number(port),
                trusted_hosts: hosts.split(/[\s,]+/).filter(Boolean),
              })
            }}
          >
            <label className="grid gap-1 text-sm">
              {t('Where phones connect')}
              <select className="field" value={bind} onChange={(event) => setBind(event.target.value)}>
                <option value={LOOPBACK}>{t('This computer only (for Tailscale or a reverse proxy)')}</option>
                {[...new Set([...status.addresses, ...(status.bind === LOOPBACK ? [] : [status.bind])])].map(
                  (address) => (
                    <option key={address} value={address}>
                      {t('Home network: {address}', { address })}
                    </option>
                  ),
                )}
              </select>
            </label>
            <label className="grid gap-1 text-sm">
              {t('Port')}
              <input
                className="field"
                inputMode="numeric"
                value={port}
                onChange={(event) => setPort(event.target.value.replace(/\D/g, '').slice(0, 5))}
              />
            </label>
            <label className="grid gap-1 text-sm">
              {t('Host names that may connect (optional)')}
              <input
                className="field"
                placeholder="mypc.tailnet.ts.net"
                value={hosts}
                spellCheck={false}
                autoCapitalize="off"
                onChange={(event) => setHosts(event.target.value)}
              />
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" disabled={busy || !dirty}>
                {t('Save')}
              </Button>
              {message && (
                <span className="text-sm text-zinc-300" role="status">
                  {message}
                </span>
              )}
            </div>
          </form>

          {status.running &&
            (status.pairing ? (
              <div className="grid gap-2 rounded-xl bg-white/5 p-3" role="status">
                <p className="text-sm">
                  {t('Open the address on your phone and enter this code. It works once, for 5 minutes.')}
                </p>
                <p className="text-center text-2xl font-semibold tracking-[0.2em] text-zinc-100 tabular-nums">
                  {status.pairing.code}
                </p>
                <Button disabled={busy} onClick={() => void change({ action: 'cancel_code' })}>
                  {t('Cancel')}
                </Button>
              </div>
            ) : (
              <Button
                variant="primary"
                disabled={busy || status.devices.length >= 10}
                onClick={() => void change({ action: 'new_code' })}
              >
                <Smartphone aria-hidden size={14} />
                {t('Pair a phone')}
              </Button>
            ))}

          {status.devices.length > 0 && (
            <ul className="grid gap-1" aria-label={t('Paired phones')}>
              {status.devices.map((device) => (
                <li key={device.id} className="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-2">
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-zinc-100">{device.name}</span>
                    <span className="block text-xs text-zinc-400">
                      {t('Last used {date}', { date: date(device.last_seen) })}
                    </span>
                  </span>
                  <Button
                    disabled={busy}
                    aria-label={t('Remove {name}', { name: device.name })}
                    onClick={() => void change({ action: 'revoke', device: device.id })}
                  >
                    <X aria-hidden size={14} />
                    {t('Remove')}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  )
}
