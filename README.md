# Ectomatter's packages

The list of cores and plugins Ectonomic reviewed, `packages.json`. Ectomatter
reads it for Add a device core and Add a plugin in Settings, and for each listed
package's updates. Each entry names the repository the package is released
from, who publishes it, and each version: the manifest that was reviewed and
the SHA-256 its package must have. Ectomatter takes a package only if it
matches that checksum, so a release changed after it was reviewed is refused.

## Sending in a package

1. Release it (`docs/making-a-package.md` in Ectomatter's repository):
   `tools/release-package.py` makes the release's three files and prints the
   package's entry.
2. Open a pull request that adds the entry to `packages` in `packages.json`.
   For a new version of a package already listed, add the version to its
   entry's `versions`, newest last. Keep older versions; people may be on
   them.
3. Ectonomic runs the check on the pull request (`check.py`). It fails when:
   - the license isn't one in `gpl-compatible.json`
   - the release's `core.json`, or the one inside the package, isn't the
     manifest in the entry
   - the package doesn't match the checksum in the entry
   - the id is taken, or the entry has no repository or publisher
4. Someone at Ectonomic reads the manifest, mostly what it reaches: the USB
   devices in `matches` and everything in `uses`. A package can reach nothing
   else, so a manifest that asks only for what the package needs is quick to
   approve. A plugin that reaches the web says why in its `description`.

Run the check yourself before sending it:

```sh
python3 check.py --releases path/to/target/releases
```

## A package that isn't listed

Anyone can still add a package from its GitHub address or its file, in Add a
device core or Add a plugin, From an address or a file. Ectomatter says nobody at Ectonomic reviewed
it, and shows what it can reach before it's added.
