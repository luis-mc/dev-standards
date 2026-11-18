# Windows installer and update window (templates)

Starter files for UX-62 to UX-65. Copy them into the product's build folder.

- `make-installer-art.ts`: reads the token file and writes `banner.bmp` (493x58) and `dialog.bmp` (493x312). Run with Node 22 or later: `node --experimental-strip-types make-installer-art.ts <tokens-file> <out-dir> [variant]`. A second product passes its own variant.
- `installer-art.wxs`: wires both bitmaps into the stock WixUI dialogs.
- `update-window.ps1`: the one native update window. `-LayoutCheck` builds it off-screen at 100%, 150% and 200% and exits 1 when a control is clipped or a button is off-window. Run it in CI on Windows.
