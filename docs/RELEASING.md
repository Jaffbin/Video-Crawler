# Releasing

How a version of Video Grabber reaches users, and what is still missing.

## Publish a release

1. Set `version` in `pyproject.toml` (for example `0.2.0`) and commit it.
2. Make sure CI is green on `main`.
3. Tag and push the tag. The tag must be `v` plus the project version:

   ```powershell
   git tag v0.2.0
   git push origin v0.2.0
   ```

4. The **Release** workflow (`.github/workflows/release.yml`) builds the Windows Portable ZIP with
   `scripts/build_portable.ps1`, checks the generated `.sha256` file against the ZIP, and publishes a
   GitHub Release with:
   - `video-grabber-windows-x64-portable.zip`
   - `video-grabber-windows-x64-portable.zip.sha256`

   It fails, and publishes nothing, if the tag and `pyproject.toml` disagree or the checksum does not
   match.

You can also build the same files locally with `scripts\build_portable.ps1`; they appear in `artifacts/`.

## Verify a download

Users should compare the ZIP with the published checksum before opening it:

```powershell
(Get-FileHash .\video-grabber-windows-x64-portable.zip -Algorithm SHA256).Hash.ToLower()
Get-Content .\video-grabber-windows-x64-portable.zip.sha256
```

The two hashes must be identical. A checksum proves the file is the one that was published; it does not
replace code signing.

## Not done yet

- **The workflow has never run.** Cut a test tag such as `v0.1.1-test` on a branch you do not mind
  deleting, or run the build script locally, before relying on it.
- **Code signing.** The ZIP is unsigned, so Windows SmartScreen shows "Unknown publisher". Options are
  SignPath Foundation (free for open source, needs an application) or Azure Artifact Signing (paid, and
  limited to certain countries for individuals). Check current eligibility before choosing.
- **winget.** The Windows Package Manager needs an installer it can run: an `.exe`/`.msi`/`.msix`, or a
  ZIP whose nested file is one of those (or a `portable` executable). Our ZIP only contains
  `.cmd` launchers and an embedded Python, so a manifest would fail validation. To list the app, first
  produce one of:
  1. a small `VideoGrabber.exe` launcher inside the ZIP that starts the bundled Python (usable as a
     `portable` nested installer), or
  2. a per-user installer (for example Inno Setup) published next to the ZIP.

  Then submit a manifest to `microsoft/winget-pkgs` (`wingetcreate new <installer URL>` generates it, and
  the hash comes from the release). Re-check the current winget manifest rules before starting.
