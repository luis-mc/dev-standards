---
title: Windows packaging on the Linux pool
type: how-to
---
# Windows packaging on the Linux pool

Use this guide to build a Windows installer (MSI) on the Linux runner pool. The rules are in the [delivery spec](../features/delivery/spec.md), R13.68 to R13.71 and R13.76.

## What the layer installs

The `windows-packaging` layer adds these packages to the pool image: `dotnet-sdk-8.0`, `wine`, `wine64`, `xvfb`, `xauth` and `msitools`. It is about 1 GB and it is off by default.

## Turn it on

1. Add the layer to `.delivery/config.json`:

   ```json
   {"pool": {"layers": ["windows-packaging"]}}
   ```

2. Rebuild the pool image with `pool-refresh --yes`. It refuses while a pool runner is busy; wait for the job or use `--force`.
3. Run the doctor. `pool.<name>.layer-windows-packaging` checks that `wine`, `xvfb-run` and `dotnet` exist in the image.

`/delivery-ci-setup` offers this step when the repository has `*.wxs` files.

## Build an MSI on the pool

The template `scripts/delivery/windows-msi-linux.sh` downloads the pinned build tools listed in `scripts/delivery/windows-build-tools.json`, then runs the build command under Wine. Use `--dry-run` first to see each step.

This is a CI check only. The cabinet is compressed with `mszip`, and the file is never installed. The MSI you ship is built on Windows.

## Service permissions (WiX 5)

To set the access list (DACL) of a Windows service, put the core element `PermissionEx` inside `ServiceInstall`. WiX turns it into `MsiLockPermissionsEx`.

```xml
<ServiceInstall Id="App1Service" Name="App1" Type="ownProcess" Start="auto"
                ErrorControl="normal" Account="LocalSystem">
  <PermissionEx Sddl="D:(A;;GA;;;SY)(A;;GA;;;BA)" />
</ServiceInstall>
```

Do not use the util extension form `<util:PermissionEx Sddl="..." />`. It fails the build with `WIX0004` and `WIX0010`.

```xml
<!-- Fails with WIX0004 and WIX0010 -->
<ServiceInstall Id="App1Service" Name="App1">
  <util:PermissionEx Sddl="D:(A;;GA;;;SY)(A;;GA;;;BA)" />
</ServiceInstall>
```
