"""The check every change to the list of packages (packages.json) must pass
before it's merged, run by Ectonomic on each pull request and by anyone by
hand: each entry's shape, a license compatible with the GPLv3
(gpl-compatible.json), and each version's release, which must carry the
manifest the list shows and a package matching the checksum the list pins.

  check.py [LIST] [--releases DIR]   checks LIST (packages.json beside this
      file); the release files are read from GitHub
      (github.com/<repository>/releases/download/<version>/<file>), or from
      DIR/<id>/<version>/<file> (as tools/release-package.py writes them).
      Prints what's wrong, a line each, and exits 1 when anything is.

Reads nothing but the list, the release files and gpl-compatible.json.
"""
import hashlib
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KINDS = ('core', 'plugin')
NEEDS = ('id', 'kind', 'name', 'version', 'protocol', 'module', 'license', 'description')
NAMED = re.compile(r'^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')
ID = re.compile(r'^[a-z0-9][a-z0-9-]*$')


def jsonc(text):
    """JSON with // and /* */ comments, as manifests are written."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == '\\' else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith('//', i):
            i = text.find('\n', i)
            i = n if i < 0 else i
        elif text.startswith('/*', i):
            i = text.find('*/', i) + 2
        else:
            out.append(c)
            i += 1
    return json.loads(''.join(out))


def alternatives(expr):
    """An SPDX expression as its choices, each the licenses that all apply."""
    t = re.findall(r'\(|\)|[A-Za-z0-9.+:-]+', expr.replace('/', ' OR '))
    at = 0

    def either():
        nonlocal at
        out = both()
        while at < len(t) and t[at] == 'OR':
            at += 1
            out = out + both()
        return out

    def both():
        nonlocal at
        out = one()
        while at < len(t) and t[at] == 'AND':
            at += 1
            more = one()
            out = [a + b for a in out for b in more]
        return out

    def one():
        nonlocal at
        if at < len(t) and t[at] == '(':
            at += 1
            out = either()
            at += 1
            return out
        term = t[at] if at < len(t) else ''
        at += 1
        if at < len(t) and t[at] == 'WITH':
            at += 2
        return [[term]]

    return either() if t else [[]]


def compatible(expr, allowed):
    return any(alt and all(x in allowed for x in alt) for alt in alternatives(expr))


def release_file(repo, pid, version, name, releases):
    if releases:
        f = Path(releases) / pid / version / name
        return f.read_bytes() if f.is_file() else None
    url = f'https://github.com/{repo}/releases/download/{version}/{name}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'ectomatter-packages-check'}), timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def check_version(repo, v, releases, said, where):
    m = v.get('manifest')
    if not isinstance(m, dict):
        said.append(f'{where}: no manifest')
        return
    missing = [k for k in NEEDS if k not in m]
    if missing:
        said.append(f'{where}: its manifest has no {", ".join(missing)}')
        return
    pid, version = m['id'], m['version']
    if m.get('repository', repo) != repo:
        said.append(f'{where}: its manifest names {m["repository"]}, not {repo}')
    sha = str(v.get('sha256', ''))
    if not re.fullmatch(r'[0-9a-f]{64}', sha):
        said.append(f'{where}: no SHA-256 pinned')
        return
    released = release_file(repo, pid, version, 'core.json', releases)
    if released is None:
        said.append(f'{where}: the release {version} of {repo} has no core.json')
    elif jsonc(released.decode()) != m:
        said.append(f'{where}: the release\'s core.json isn\'t the manifest listed')
    package = release_file(repo, pid, version, f'{pid}.ectocore', releases)
    if package is None:
        said.append(f'{where}: the release {version} of {repo} has no {pid}.ectocore')
        return
    if hashlib.sha256(package).hexdigest() != sha:
        said.append(f'{where}: {pid}.ectocore doesn\'t match the SHA-256 pinned')
        return
    try:
        z = zipfile.ZipFile(io.BytesIO(package))
        names = z.namelist()
        root = '' if 'core.json' in names else f'{pid}/'
        inside = jsonc(z.read(f'{root}core.json').decode())
        if inside != m:
            said.append(f'{where}: the package\'s core.json isn\'t the manifest listed')
        if f'{root}{m["module"]}' not in names:
            said.append(f'{where}: the package has no {m["module"]}')
    except (zipfile.BadZipFile, KeyError, ValueError) as e:
        said.append(f'{where}: the package can\'t be read ({e})')


def check(listing, releases=None):
    said = []
    allowed = set(json.loads((HERE / 'gpl-compatible.json').read_text())['licenses'])
    if listing.get('format') != 1:
        said.append('the list says no format 1')
    ids = {}
    for n, e in enumerate(listing.get('packages', [])):
        repo = e.get('repository', '')
        versions = e.get('versions') or []
        first = (versions[0].get('manifest') or {}) if versions else {}
        pid = first.get('id', f'#{n}')
        where = f'{pid}'
        if not NAMED.match(repo):
            said.append(f'{where}: no repository (owner/name)')
        if not str(e.get('publisher', '')).strip():
            said.append(f'{where}: no publisher')
        if not versions:
            said.append(f'{where}: no version')
            continue
        if not ID.match(str(pid)):
            said.append(f'{where}: an id Ectomatter can\'t use')
        if pid in ids:
            said.append(f'{where}: listed twice')
        ids[pid] = True
        seen = set()
        for v in versions:
            m = v.get('manifest') or {}
            at = f'{pid} {m.get("version", "?")}'
            if m.get('id') != pid or m.get('kind') != first.get('kind'):
                said.append(f'{at}: another package than the entry\'s first version')
            if m.get('kind') not in KINDS:
                said.append(f'{at}: kind isn\'t core or plugin')
            if m.get('version') in seen:
                said.append(f'{at}: listed twice')
            seen.add(m.get('version'))
            if not compatible(str(m.get('license', '')), allowed):
                said.append(f'{at}: license {m.get("license")!r} isn\'t compatible with the GPLv3 (gpl-compatible.json)')
            check_version(repo, v, releases, said, at)
    return said


def main(argv):
    releases = argv[argv.index('--releases') + 1] if '--releases' in argv else None
    rest = [a for i, a in enumerate(argv) if a != '--releases' and (i == 0 or argv[i - 1] != '--releases')]
    path = Path(rest[0]) if rest else HERE / 'packages.json'
    said = check(json.loads(path.read_text()), releases)
    print('\n'.join(said))
    return 1 if said else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
