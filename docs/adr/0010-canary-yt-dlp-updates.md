# 0010. Try a new yt-dlp on a few sites before switching to it

Status: Accepted (2026-11-23), implemented in `grab_canary.py`. The open questions were decided as
recommended; see "Decisions" at the end.

## Context

Sites change often, so Video Grabber nudges users to update yt-dlp and installs updates with one
click (`pip install -U` into the app's own Python or the portable `site-packages`). A new release
occasionally breaks a site that worked before. Today that is found only when a real download fails,
and the user then has to open **Updates → Go back to <version>** (commit `960fda2`). The app keeps the old version in memory until restart,
because `yt_dlp` is imported once when the app starts.

Constraints:

- **Privacy:** no project server, no telemetry. Checks may contact only the sites being checked and
  PyPI, and must never send the user's cookies.
- **Portable build:** an embedded Python whose packages live in its own `Lib/site-packages`; updates
  use `pip --target`.
- **Network noise:** a single failed request says little. Sites rate-limit, links rot and some need
  sign-in, so "the new version failed once" is not proof of a regression.

## Decision

### 1. Stage, then probe, then install

```
check PyPI ──► stage new version ──► probe old and new ──► verdict ──► install (or keep current)
               (separate folder)      (child processes)
```

1. **Stage.** `pip install "yt-dlp[...]==<new>" --target <settings>/managed/ytdlp-staging/<new>`.
   Nothing the app uses is touched; a failed or cancelled stage is deleted.
2. **Probe.** For each probe link, run the *current* and the *staged* yt-dlp in child processes
   (started from an empty folder without `PYTHONPATH`, with the staging folder put first on
   `sys.path` for the new one; `python -I` is not used because it would hide a yt-dlp installed in the
   user's site-packages) asking for
   metadata only: no download, no playlist expansion, no cookies, a 45-second limit per link, at
   most two links in parallel. A probe succeeds when yt-dlp exits normally and returns at least one
   playable format.
3. **Verdict**, per link:

   | Current version | New version | Meaning |
   | --- | --- | --- |
   | works | works | fine |
   | fails | works | fine (the update fixes it) |
   | fails | fails | inconclusive (link, network or sign-in), ignored |
   | works | fails | **regression** |

   The update **passes** when no link regresses and at least one link was conclusive. A run where
   every link is inconclusive (offline, all links dead) is reported as "could not test" and the user
   chooses.
4. **Install.** On a pass, install the same version the normal way (pip reuses its cache) and
   remember the replaced version for **Go back**. On a regression, keep the current version, show
   which sites regressed and the new version's error for each, and offer **Install anyway**. The
   skipped version is remembered so the "update available" dot stays quiet until a newer release
   appears.

Comparing the two versions on the same link, at the same time and on the same network, is the core
choice: it turns flaky single requests into a signal, without a server.

### 2. Which links are probed

- **Built-in set (always):** three or four stable, public, permissively licensed videos on the most
  used sites (YouTube first; others chosen during implementation), kept in `grab_canary.py` with the
  reason each was chosen. Links are checked for licence and availability when added, and an
  inconclusive built-in link is reported in Diagnostics so it can be replaced.
- **Your recent sites (opt-in, off by default):** for up to three sites from the last successful
  downloads, re-probe one recent link per site. This tests what the user actually uses, but repeats a
  request to a link from their history, which may be private or tied to a session, so it is a
  choice in Settings rather than a default.

### 3. When it runs

Only when the user starts an update, as part of that update (about 50 seconds of extra work in the measurement below,
shown as **Downloading → Testing on N sites → Installing**). No background or scheduled updates are
added by this decision. The existing rules still apply: no update while tasks are queued or running.

### 4. What does not change

- **Go back** stays, for regressions the probes cannot see (a site not in the set, a download that
  fails after metadata succeeds).
- **Update without testing** stays available as an explicit choice, for offline machines or when a
  site is blocked on the user's network.
- Probes honour proxy environment variables like any yt-dlp run, and never use uploaded cookies,
  cookies from browsers or sign-in data.

## Consequences

- A regression on a probed site is caught before the user's downloads use the new version.
- Updates take longer (about 50 seconds in the measurement above) and use some bandwidth: metadata
  only, but sites such as YouTube still send a web page and a player script per link.
- Staging temporarily holds a second copy of yt-dlp and its dependencies (45 MB measured, with
  curl-cffi), removed afterwards.
- Built-in links need occasional maintenance; inconclusive links are surfaced rather than silently
  weakening the check.
- Metadata success does not prove the download step works. **Go back** covers that gap.
- A site with no probe link gets no protection beyond **Go back**.

## Alternatives considered

- **Test only the new version:** cheaper, but every dead link or rate limit looks like a regression.
- **Install first, test after, roll back automatically:** simpler pipeline, but leaves a broken
  version in place if the rollback itself fails (offline), and needs a restart in between.
- **Run yt-dlp's own extractor test suite:** written for yt-dlp's developers, slow, needs network for
  hundreds of sites and fails for reasons unrelated to the user.
- **A project server that tests releases once for everyone:** contradicts "no project server".

## Open questions (decided)

1. **On a regression, the default:** keep the current version and ask (recommended), or install
   anyway and only warn?
2. **"Your recent sites" probes:** offer them as opt-in (recommended), leave them out, or turn them on
   by default?
3. **Built-in sites besides YouTube:** which two or three matter most to users of this app
   (for example Bilibili, Vimeo, SoundCloud)?

## Decisions

1. On a regression the current version is kept and the user is asked; **Install anyway** stays one
   click away.
2. Probing recent sites is opt-in, off by default (**Also test on up to three sites you downloaded
   from recently** in the Updates window).
3. Built-in probes: YouTube, Internet Archive and Wikimedia Commons, all Blender Foundation's Big Buck
   Bunny, because each site's metadata states a Creative Commons licence that yt-dlp reads
   (`license`). Vimeo was dropped because yt-dlp now needs a signed-in session there; Bilibili and
   SoundCloud have no link whose licence could be verified the same way. Recent-site probes cover
   sites like Bilibili for users who opt in.

Measured on the development machine on 2026-11-24, updating 2026.8.19 to 2026.11.23 with the real
pipeline (final install replaced by a recorder): checking PyPI 7-19 s, staging 25 s (9 s with pip's
cache), probing the three links with both versions 18-20 s, about 50 s in total. The staging folder
peaked at 45 MB and was removed. The child processes reported running 2026.08.19 and 2026.11.23
respectively, and a probe that loads any other version than the one being tested now counts as
inconclusive, so a staging problem cannot turn into a silent pass.

## Implementation outline

- `grab_canary.py` (pure logic, testable without network): probe list, verdict table, staging paths.
- `webui.py`: an update pipeline with phases (`staging`, `probing`, `installing`) reusing `_do_update`,
  and a skipped-version record next to the existing previous-version record.
- Updates window: phases, per-site results, **Install anyway**, **Update without testing**.
- Tests: verdict table, child-process probe with a local HTTP fixture and a fake extractor, staging
  clean-up after cancel or failure, and that probes never receive cookies.
