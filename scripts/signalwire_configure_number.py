#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / '.env'


def load_env(path: Path) -> dict[str, str]:
    vals: dict[str, str] = {}
    if path.exists():
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            vals[k] = v
    vals.update(os.environ)
    return vals


def auth_header(project: str, token: str) -> str:
    b = base64.b64encode(f'{project}:{token}'.encode()).decode()
    return f'Basic {b}'


def request_json_python(url: str, *, method: str = 'GET', headers: dict[str, str] | None = None, data: dict[str, str] | None = None) -> dict:
    body = None
    req_headers = {'Accept': 'application/json'}
    if headers:
        req_headers.update(headers)
    if data is not None:
        body = urlencode(data).encode()
        req_headers['Content-Type'] = 'application/x-www-form-urlencoded'
    req = Request(url, data=body, headers=req_headers, method=method)
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def request_json_curl(url: str, *, method: str = 'GET', headers: dict[str, str] | None = None, data: dict[str, str] | None = None, insecure: bool = False) -> dict:
    curl = shutil.which('curl') or '/usr/bin/curl'
    cmd = [curl, '-sS', '-X', method, '-H', 'Accept: application/json']
    if insecure:
        cmd.append('-k')
    if headers:
        for k, v in headers.items():
            cmd += ['-H', f'{k}: {v}']
    if data is not None:
        for k, v in data.items():
            cmd += ['--data-urlencode', f'{k}={v}']
    cmd.append(url)
    out = subprocess.check_output(cmd, text=True)
    return json.loads(out)


def request_json(url: str, *, method: str = 'GET', headers: dict[str, str] | None = None, data: dict[str, str] | None = None, curl_fallback: bool = True, insecure: bool = False) -> dict:
    try:
        return request_json_python(url, method=method, headers=headers, data=data)
    except URLError:
        if curl_fallback:
            return request_json_curl(url, method=method, headers=headers, data=data, insecure=insecure)
        raise


def mask(s: str) -> str:
    return s if len(s) <= 8 else s[:4] + '...' + s[-4:]


def build_base(space: str, project: str) -> str:
    return f'https://{space}/api/laml/2010-04-01/Accounts/{project}'


def list_numbers(space: str, project: str, token: str, *, insecure: bool = False) -> dict:
    url = build_base(space, project) + '/IncomingPhoneNumbers.json'
    return request_json(url, headers={'Authorization': auth_header(project, token)}, insecure=insecure)


def update_number(space: str, project: str, token: str, sid: str, voice_url: str, voice_method: str = 'POST', *, insecure: bool = False) -> dict:
    url = build_base(space, project) + f'/IncomingPhoneNumbers/{sid}.json'
    payload = {'VoiceUrl': voice_url, 'VoiceMethod': voice_method}
    return request_json(url, method='POST', headers={'Authorization': auth_header(project, token)}, data=payload, insecure=insecure)


def pick_number(data: dict, needle: str) -> dict | None:
    items = data.get('incoming_phone_numbers') or data.get('incomingPhoneNumbers') or []
    for item in items:
        phone = str(item.get('phone_number', ''))
        friendly = str(item.get('friendly_name', ''))
        sid = str(item.get('sid', ''))
        if needle in {phone, friendly, sid}:
            return item
    return None


def main() -> int:
    p = argparse.ArgumentParser(description='List/update SignalWire incoming phone numbers for inbound voice URL.')
    p.add_argument('--insecure', action='store_true', help='Allow insecure TLS for curl fallback if local CA trust is broken')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list', help='List incoming phone numbers')
    upd = sub.add_parser('update', help='Update one incoming phone number VoiceUrl')
    upd.add_argument('--sid', help='Incoming phone number SID')
    upd.add_argument('--match', help='Match by exact phone number, friendly name, or SID')
    upd.add_argument('--voice-url', required=True, help='Public inbound URL, e.g. https://example.ngrok-free.app/')
    upd.add_argument('--voice-method', default='POST', choices=['GET', 'POST'])
    upd.add_argument('--dry-run', action='store_true')
    args = p.parse_args()

    env = load_env(ENV_PATH)
    space = env.get('SIGNALWIRE_SPACE', '')
    project = env.get('SIGNALWIRE_PROJECT', '')
    token = env.get('SIGNALWIRE_TOKEN', '')
    missing = [k for k, v in [('SIGNALWIRE_SPACE', space), ('SIGNALWIRE_PROJECT', project), ('SIGNALWIRE_TOKEN', token)] if not v]
    if missing:
        print(f'Missing required env vars: {", ".join(missing)}', file=sys.stderr)
        return 2

    try:
        if args.cmd == 'list':
            data = list_numbers(space, project, token, insecure=args.insecure)
            items = data.get('incoming_phone_numbers') or data.get('incomingPhoneNumbers') or []
            print(f'Space: {space}')
            print(f'Project: {mask(project)}')
            print(f'Found {len(items)} incoming phone number(s)')
            for item in items:
                print(json.dumps({
                    'sid': item.get('sid'),
                    'phone_number': item.get('phone_number'),
                    'friendly_name': item.get('friendly_name'),
                    'voice_url': item.get('voice_url'),
                    'voice_method': item.get('voice_method'),
                }, ensure_ascii=False))
            return 0

        if args.cmd == 'update':
            sid = args.sid
            if not sid:
                if not args.match:
                    print('Provide --sid or --match', file=sys.stderr)
                    return 2
                data = list_numbers(space, project, token, insecure=args.insecure)
                match = pick_number(data, args.match)
                if not match:
                    print(f'No incoming phone number matched: {args.match}', file=sys.stderr)
                    return 3
                sid = match['sid']
                print(f'Matched SID: {sid} ({match.get("phone_number")})')
            if args.dry_run:
                print(json.dumps({'sid': sid, 'voice_url': args.voice_url, 'voice_method': args.voice_method, 'dry_run': True}, ensure_ascii=False))
                return 0
            resp = update_number(space, project, token, sid, args.voice_url, args.voice_method, insecure=args.insecure)
            print(json.dumps(resp, indent=2, ensure_ascii=False))
            return 0
    except HTTPError as e:
        body = e.read().decode(errors='ignore')
        print(f'HTTP {e.code} calling SignalWire API', file=sys.stderr)
        print(body, file=sys.stderr)
        return 10
    except subprocess.CalledProcessError as e:
        print(f'curl failed: {e}', file=sys.stderr)
        return 11
    except URLError as e:
        print(f'Network error calling SignalWire API: {e}', file=sys.stderr)
        return 12
    except Exception as e:
        print(f'Unexpected error: {e}', file=sys.stderr)
        return 13


if __name__ == '__main__':
    raise SystemExit(main())
