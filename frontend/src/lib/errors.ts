const COPY: Record<string, [string, string]> = {
  ffmpeg: ['Video and audio processing needs attention.', 'Prepare the download features, then retry.'],
  javascript: [
    'This site needs an additional download feature.',
    'Prepare the download features, then retry.',
  ],
  impersonation_missing: [
    'This site needs an additional download feature.',
    'Prepare the download features, then retry.',
  ],
  app_control: ['Windows blocked a download feature.', 'Technical details show which file was blocked.'],
  login: [
    'This site needs you to sign in.',
    'Sign in on the original page, then choose that browser to retry.',
  ],
  cookies_expired: [
    'Your saved sign-in session has expired.',
    'Sign in on the original page, then choose that browser to retry.',
  ],
  cookies_locked: [
    'The browser’s sign-in session could not be read.',
    'Close the browser completely, then retry. You can also choose another browser.',
  ],
  disk_full: [
    'The download drive is out of space.',
    'Open the download folder, free some space, then retry.',
  ],
  file_locked: ['A player or another app is using this file.', 'Close the player, then retry.'],
  file_permission: [
    'The app cannot save to this folder.',
    'Check that you can save files in the download folder, then retry.',
  ],
  not_found: ['This link is no longer available.', 'Open the original page and copy a new link.'],
  unsupported: [
    'No downloadable media was found on this page.',
    'Open the original page and check the link.',
  ],
  forbidden: [
    'The site did not allow this download.',
    'Check the original page. If sign-in is required, choose your browser to retry.',
  ],
  network: ['The site could not be reached.', 'Check your connection, then retry.'],
  timeout: ['The site took too long to respond.', 'Check your connection, then retry.'],
  dns: ['The site could not be reached.', 'Check your connection and the link, then retry.'],
  certificate: [
    'A secure connection to the site could not be established.',
    'Check your computer’s date and time, then retry.',
  ],
  partial: [
    'Some items could not be finished.',
    'Retry the failed items, or repair the files already downloaded.',
  ],
}

export function errorCopy(kind?: string): [string, string] {
  return (
    COPY[kind || ''] || [
      'This download could not finish.',
      'Retry, or view technical details if it still fails.',
    ]
  )
}
