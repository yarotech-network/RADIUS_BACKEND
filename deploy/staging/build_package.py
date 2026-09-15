"""Package reviewed working files, including uncommitted implementation, without runtime data."""
import hashlib
import io
import json
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path

# deploy/staging/build_package.py -> repository root
backend = Path(__file__).resolve().parents[2]
frontend = backend.parent / 'yarotech-radius-frontend'
workspace = backend.parent
output = workspace / 'staging-artifacts'
output.mkdir(exist_ok=True)
release = 'yarotech-staging-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
archive = output / (release + '.tar.gz')
if not (frontend / 'dist/index.html').is_file():
    raise SystemExit('Build and validate the frontend first.')
blocked_dirs = {'.git','.venv','venv','node_modules','__pycache__','media','staticfiles','backups','production_backups','deployment-backups','test-results','playwright-report','.pytest_cache','logs'}
blocked_suffixes = {'.key','.pem','.p12','.pfx','.sqlite','.sqlite3','.db','.dump','.backup','.sql.gz','.tar','.tgz','.zip','.log','.pyc'}
manifest = {'release':release, 'kind':'staging-candidate', 'repositories':{}, 'files':{}}
files = []
for label, root in [('backend', backend), ('frontend', frontend)]:
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    status = subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True)
    manifest['repositories'][label] = {'head':head,'dirty':bool(status)}
    paths = subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=root).decode().split('\0')
    if label == 'frontend':
        paths += [str(path.relative_to(root)).replace('\\','/') for path in (root/'dist').rglob('*') if path.is_file()]
    for relative in sorted(set(paths)):
        if not relative:
            continue
        path = root / relative
        name = path.name.lower()
        if name in {'staging-tests.json', 'source.json', 'import-plan.json'}:
            continue
        if not path.is_file() or path.is_symlink() or blocked_dirs.intersection(path.relative_to(root).parts):
            continue
        if name.startswith('.env') or '.env.' in name or name.endswith('.env'):
            if not name.endswith('.example'):
                continue
        if any(name.endswith(suffix) for suffix in blocked_suffixes) or ('private' in name and 'key' in name):
            continue
        data = path.read_bytes()
        target = label+'/'+relative.replace('\\','/')
        manifest['files'][target] = hashlib.sha256(data).hexdigest()
        files.append((target,data))
with archive.open('xb') as output_file:
    with tarfile.open(fileobj=output_file,mode='w:gz') as tar:
        for target,data in files + [('manifest.json',json.dumps(manifest,indent=2,sort_keys=True).encode())]:
            info = tarfile.TarInfo(target)
            info.size = len(data)
            info.mode = 0o755 if target.endswith('.sh') else 0o644
            tar.addfile(info,io.BytesIO(data))
sha = hashlib.sha256(archive.read_bytes()).hexdigest()
archive.with_suffix(archive.suffix+'.sha256').write_text(sha+'  '+archive.name+'\n',encoding='utf-8')
print(str(archive))
print('SHA256 '+sha)
print('Candidate only: inspect the manifest and complete staging acceptance before promotion.')
