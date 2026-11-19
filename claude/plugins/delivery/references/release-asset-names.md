# Release asset names

Release assets carry the version in the file name. This is rule DL-96.

## The default

A file uploaded to a release is named `<installer_name>_<version>.<ext>`. For example `example-app-windows-amd64_1.4.2.msi`. The same holds for `.pkg`, `.deb`, `.rpm`, `.tar.gz` and `.zip`. The names written into `SHA256SUMS` are the same versioned names.

The version is the release tag without the leading `v`.

## The opt-out

A project that needs fixed names sets this in `.delivery/config.json`:

```json
{ "release_assets": { "versioned_names": false } }
```

The default is `true`. The templates read this key before they name a release asset.

## What breaks, and how to cope

- **A self-updater that looks for a fixed asset name.** Machines on older versions stop finding the asset when the name gains a version. Make the updater look for the versioned name first and the plain name as a fallback. Ship that updater one release before the rename if self-update must not break. Without that, expect one manual install.
- **Fixed `releases/latest/download/<name>` links in docs.** They stop working. Link the release page, or resolve the newest version first.

## CI build artifacts keep stable names

Only release assets change. The names given to `actions/upload-artifact` stay free of any version. `artifact-prune.yml` keeps the newest artifact of each name (DL-22), and a versioned name would make every artifact unique and defeat it.
