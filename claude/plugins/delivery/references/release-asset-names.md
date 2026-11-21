# Release asset names

Every project names its installers and release assets the same way. This is rule DL-96. The release check enforces it (LC-32).

## The name

`<Product>-<version>-<os>-<arch>.<ext>`

| Part | Rule |
|---|---|
| `Product` | One word in PascalCase. Letters and digits only, no spaces. |
| `version` | SemVer without a leading `v`. A pre-release or build suffix is allowed. |
| `os` | `win`, `linux` or `macos`. A target's `windows` becomes `win`. |
| `arch` | `x64` or `arm64`. |
| `ext` | The package: `msi`, `deb`, `rpm`, `pkg`, `tar.gz` or `zip`. |

Examples:

- `ExampleApp-2.5.0-win-x64.msi`
- `ExampleApp-2.5.0-linux-x64.deb`
- `ExampleApp-2.5.0-linux-arm64.rpm`
- `ExampleApp-2.5.0-macos-arm64.pkg`

The names written into `SHA256SUMS` are the same names. The version is the release tag without the leading `v`.

`lifecycle_release_check.py` requires one such name for each target in `lifecycle.json`, and fails on a package file with any other shape.

## The opt-out

A project that needs fixed names sets this in `.delivery/config.json`:

```json
{ "release_assets": { "versioned_names": false } }
```

The default is `true`. The templates read this key before they name a release asset. With `false` the name is `<Product>-<os>-<arch>.<ext>`, and the release check does not apply.

## The old names

The rule before this one was `<installer_name>_<version>.<ext>`. For one transition release an updater looks for the new name first and the older name second. After that release it looks for the new name only.

## What breaks, and how to cope

- **A self-updater that looks for a fixed or older asset name.** Machines on older versions stop finding the asset when the name changes. Make the updater look for the new name first and the older name as a fallback. Ship that updater one release before the rename if self-update must not break. Without that, expect one manual install.
- **Fixed `releases/latest/download/<name>` links in docs.** They stop working. Link the release page, or resolve the newest version first.

## CI build artifacts keep stable names

Only release assets change. The names given to `actions/upload-artifact` stay free of any version. `artifact-prune.yml` keeps the newest artifact of each name (DL-22), and a versioned name would make every artifact unique and defeat it.
