"""Build-time installation of the hash-pinned desktop engine; never used at runtime."""
from pathlib import Path
import hashlib
import io
import json
import platform
import sysconfig
import tarfile
import urllib.request


def prepare() -> Path | None:
    root = Path(__file__).resolve().parents[1] / 'reverie' / 'computer_use'
    if platform.system() != 'Windows':
        return None
    if sysconfig.get_platform() != 'win-amd64':
        raise RuntimeError('The bundled Computer Use engine currently supports Windows x64.')
    manifest = json.loads((root / 'native_manifest.json').read_text(encoding='utf-8'))
    target = root / 'native' / manifest['platform']
    binary = target / 'agent-desktop.exe'
    receipt = target / 'receipt.json'
    if binary.is_file() and receipt.is_file():
        existing = json.loads(receipt.read_text(encoding='utf-8'))
        if (existing.get('archive_sha256') == manifest['archive_sha256']
                and hashlib.sha256(binary.read_bytes()).hexdigest() == manifest['binary_sha256']
                and (target / 'LICENSE').is_file()):
            return binary
    url = f"{manifest['repository']}/releases/download/v{manifest['version']}/{manifest['archive']}"
    with urllib.request.urlopen(url, timeout=60) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != manifest['archive_sha256']:
        raise RuntimeError('Computer Use archive SHA-256 mismatch; no binary was installed.')
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as bundle:
        entry = bundle.getmember('agent-desktop.exe')
        if not entry.isfile():
            raise RuntimeError('Native engine archive has no regular executable.')
        payload = bundle.extractfile(entry).read()
    if hashlib.sha256(payload).hexdigest() != manifest['binary_sha256']:
        raise RuntimeError('Computer Use executable SHA-256 mismatch; no binary was installed.')
    license_url = f"https://raw.githubusercontent.com/vercel-labs/agent-desktop/{manifest['commit']}/LICENSE"
    with urllib.request.urlopen(license_url, timeout=30) as response:
        license_text = response.read()
    target.mkdir(parents=True, exist_ok=True)
    staged = target / 'agent-desktop.exe.pending'
    staged.write_bytes(payload)
    staged.replace(binary)
    (target / 'LICENSE').write_bytes(license_text)
    receipt.write_text(json.dumps({**manifest, 'binary_sha256': hashlib.sha256(payload).hexdigest()}, indent=2), encoding='utf-8')
    return binary


if __name__ == '__main__':
    print(prepare() or 'Computer Use native payload is not required on this platform.')
