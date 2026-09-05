import uasyncio as asyncio
import ure as re
import ujson as json
import ubinascii
import utime as time
import os
import sys
import uhashlib
import json
from modules import interfaces as interfaces_mod
from modules import vlan as vlan_mod
from modules import lan as lan_mod
from modules import wan as wan_mod
from modules import dmz as dmz_mod
from modules import ip_tools as ipt_mod
from modules import license as license_mod 
from modules import setting as setting_mod
from modules import wireless as wifi_mod
from modules import health as health_mod
STATE_FILE     = '/mnt/ser/lic/license.state'
BACKUP_FILE    = '/mnt/ser/lic/backup_license.state.old'
TMP_STATE_FILE = '/mnt/ser/lic/license.state.tmp'
LIC_MODE_FILE  = '/sbin/ubsd'
SYS_ID_FILE    = '/mnt/ser/lic/sys_id'
REM_TIME_FILE  = '/mnt/ser/lic/rem_time'
MAX_RUN_SECONDS = 72 * 3600                  
SLEEP_INTERVAL  = 300

FIREWALL_FILE   = '/etc/config/firewall'

def _ensure_dir(path):
    try:
        d = path.rsplit('/', 1)[0]
        if d and not os.path.isdir(d):
            os.makedirs(d)
    except Exception:
        pass
for p in (STATE_FILE, BACKUP_FILE, TMP_STATE_FILE, SYS_ID_FILE, REM_TIME_FILE):
    _ensure_dir(p)
def license_initialize_state():
    epoch = time.time()                                
    return {'elapsed': 0.0, 'last_epoch': epoch}
def _rename_file(src, dst):
    try:
        os.replace(src, dst)                         
    except AttributeError:
        os.rename(src, dst)                                  
def license_atomic_write(path, data_str):
    try:
        with open(TMP_STATE_FILE, 'w') as fh:
            fh.write(data_str)
        _rename_file(TMP_STATE_FILE, path)
    except Exception:
        pass
def license_save_state(state):
    if os.path.exists(STATE_FILE):
        try:
            _rename_file(STATE_FILE, BACKUP_FILE)
        except Exception:
            pass
    license_atomic_write(STATE_FILE, json.dumps(state))
def _load_json_safe(path):
    with open(path, 'r') as fh:
        return json.loads(fh.read())
def license_load_state():
    try:
        st = _load_json_safe(STATE_FILE)
        if 'elapsed' in st and 'last_epoch' in st:
            return st
    except Exception:
        pass
    st = license_initialize_state()
    license_save_state(st)
    return st
def license_update_elapsed(state):
    now_epoch = time.time()
    delta = now_epoch - state.get('last_epoch', now_epoch)
    if delta < 0 or delta > 3600:                                         
        delta = 0
    state['elapsed'] += delta
    state['last_epoch'] = now_epoch
    license_save_state(state)
def license_is_valid(state):
    return state['elapsed'] < MAX_RUN_SECONDS
def license_format_hms(seconds):
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return h, m, s
def license_get_system_id():
    path = '/sys/bus/spi/devices/spi0.0/unique_id'
    try:
        with open(path, 'r') as f:
            return f.read().strip().upper() or 'UNKNOWN'
    except Exception:
        return 'UNKNOWN'
def license_write_file(path, content):
    try:
        with open(path, 'w') as f:
            f.write(str(content))
    except Exception:
        pass
def license_clear_file(path):
    try:
        with open(path, 'w'):
            pass
    except Exception:
        pass
def license_read_file(path):
    try:
        return open(path).read().strip()
    except Exception:
        return ''
def license_is_active():
    try:
        enc = license_read_file(LIC_MODE_FILE)
        if not enc:
            return False
        try:
            dec = ubinascii.a2b_base64(enc)
        except Exception:
            return False
        try:
            dec_txt = dec.decode()
        except Exception:
            return False
        return dec_txt == 'ok!'
    except Exception:
        return False
def license_patch_firewall():
    try:
        with open(FIREWALL_FILE, 'r') as f:
            src_lines = f.readlines()
    except Exception as e:
        print('[LIC] cannot read firewall:', e)
        return
    dst_lines, in_lan, in_wan = [], False, False
    for line in src_lines:
        stripped = line.strip()
        if stripped.startswith('config zone'):
            in_lan = in_wan = False
        if "option name 'lan'" in stripped or 'option name "lan"' in stripped:
            in_lan, in_wan = True, False
        elif "option name 'wan'" in stripped or 'option name "wan"' in stripped:
            in_wan, in_lan = True, False
        if in_lan:
            if "option forward" in stripped and 'ACCEPT' in stripped:
                line = line.replace('ACCEPT', 'REJECT')
            elif "option device 'ppp+ pptp+'" in stripped and not stripped.startswith('#'):
                line = '# ' + line
        elif in_wan:
            if "option output" in stripped and 'ACCEPT' in stripped:
                line = line.replace('ACCEPT', 'REJECT')
            elif stripped.startswith('list network') and not stripped.startswith('#'):
                line = '# ' + line
        dst_lines.append(line)
    if not dst_lines:
        print('[LIC] WARNING: produced empty firewall — aborted')
        return
    tmp = FIREWALL_FILE + '.tmp'
    bak = FIREWALL_FILE + '.bak'
    try:
        with open(tmp, 'w') as f:
            for l in dst_lines:                                
                f.write(l)
    except Exception as e:
        print('[LIC] write tmp failed:', e)
        try: os.remove(tmp)
        except: pass
        return
    try:
        if os.path.exists(bak):
            os.remove(bak)
        os.rename(FIREWALL_FILE, bak)
    except Exception:
        pass
    try:
        os.rename(tmp, FIREWALL_FILE)
    except Exception as e:
        print('[LIC] rename tmp->file failed:', e)
        return
    os.system('/etc/init.d/firewall reload')
    print('[LIC] firewall patched & reloaded')
async def license_loop():
    stored_sys_id = license_read_file(SYS_ID_FILE)
    if not stored_sys_id:
        current_id = license_get_system_id()
        if current_id and current_id != 'UNKNOWN':
            license_write_file(SYS_ID_FILE, current_id)
            stored_sys_id = current_id
        else:
            license_clear_file(LIC_MODE_FILE)
    if license_get_system_id() != stored_sys_id:
        for p in (LIC_MODE_FILE, SYS_ID_FILE, STATE_FILE, BACKUP_FILE):
            license_clear_file(p)
        os.system('reboot')
        return
    state = license_load_state()
    while True:
        if not license_is_active():
            license_update_elapsed(state)
            if not license_is_valid(state):
                license_patch_firewall()
            remaining = MAX_RUN_SECONDS - state['elapsed']
            h, m, s = license_format_hms(max(0, remaining))
            license_write_file(REM_TIME_FILE, '%02d:%02d:%02d' % (h, m, s))
        await asyncio.sleep(SLEEP_INTERVAL)
HOST = '0.0.0.0'
HTTP_PORT_FILE = '/mnt/ser/http_port'
def _read_http_port_file():
    try:
        s = read_file(HTTP_PORT_FILE, 'r') or ''
    except:
        s = ''
    port = 8080
    for line in s.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if 'port=' in line:
            k, v = line.split('=', 1)
            if k.strip().lower() == 'port':
                try:
                    p = int(v.strip())
                    if 1 <= p <= 65535:
                        port = p
                except:
                    pass
            break
    return port
PORT = _read_http_port_file()
REQUESTED_PORT = PORT
WEB_ROOT = '.'
TEMPLATES_DIR = WEB_ROOT + '/templates'
STATIC_DIR = WEB_ROOT + '/static'
PASS_FILE = '/mnt/ser/admin_password'
AUTH_USER = 'admin'
def _urldecode(s):
    if not s:
        return ""
    out = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == '%':
            if i + 2 < len(s):
                try:
                    out.append(chr(int(s[i+1:i+3], 16)))
                    i += 3
                    continue
                except:
                    pass
        elif ch == '+':
            out.append(' ')
            i += 1
            continue
        out.append(ch)
        i += 1
    return ''.join(out)
def _coerce_query_to_dict(q):
    if isinstance(q, dict):
        return q
    if not q:
        return {}
    if isinstance(q, bytes):
        try:
            q = q.decode()
        except:
            q = str(q)
    if isinstance(q, str):
        res = {}
        parts = q.split('&')
        for p in parts:
            if not p:
                continue
            if '=' in p:
                k, v = p.split('=', 1)
                res[_urldecode(k)] = _urldecode(v)
            else:
                res[_urldecode(p)] = ''
        return res
    return {}
def read_file(path, mode='r'):
    try:
        with open(path, mode) as f:
            return f.read()
    except:
        return None
def sha256_hex(s):
    h = uhashlib.sha256(s.encode('utf-8'))
    return ubinascii.hexlify(h.digest()).decode()
def _load_password_store():
    try:
        v = read_file(PASS_FILE, 'r')
        if v:
            v = v.strip()
            print('Loaded admin password from', PASS_FILE)
            return v
    except Exception as e:
        print('Warning: could not read password file:', e)
    print('Using default fallback password (plain:admin123)')
    return 'plain:admin123'
def verify_password(plain, stored):
    if stored.startswith('sha256:'):
        return sha256_hex(plain) == stored.split(':', 1)[1]
    if stored.startswith('plain:'):
        return plain == stored[6:]
    return plain == stored
def now():
    return int(time.time())
def gen_session_id():
    return ubinascii.hexlify(os.urandom(32)).decode()
SESSIONS = {}
SESSION_TTL = 60 * 60 * 8           
CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.css':  'text/css; charset=utf-8',
    '.js':   'application/javascript; charset=utf-8',
    '.png':  'image/png',
    '.jpg':  'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif':  'image/gif',
    '.svg':  'image/svg+xml',
    '.ico':  'image/x-icon',
    '.json': 'application/json; charset=utf-8',
    '.txt':  'text/plain; charset=utf-8',
}
def guess_content_type(path):
    for ext, ctype in CONTENT_TYPES.items():
        if path.endswith(ext):
            return ctype
    return 'application/octet-stream'
def get_cookie(headers, name):
    ck = headers.get('cookie') or headers.get('Cookie')
    if not ck:
        return None
    parts = [p.strip() for p in ck.split(';')]
    for p in parts:
        if '=' in p:
            k, v = p.split('=', 1)
            if k.strip() == name:
                return v.strip()
    return None
def get_session(headers):
    sid = get_cookie(headers, 'ARABSESSID')
    if not sid:
        return None
    s = SESSIONS.get(sid)
    if not s:
        return None
    if s['exp'] < now():
        try:
            del SESSIONS[sid]
        except:
            pass
        return None
    s['exp'] = now() + SESSION_TTL
    return sid, s
def set_session(user):
    sid = gen_session_id()
    SESSIONS[sid] = {'user': user, 'iat': now(), 'exp': now() + SESSION_TTL}
    return sid
def clear_session(headers):
    sid = get_cookie(headers, 'ARABSESSID')
    if sid and sid in SESSIONS:
        try:
            del SESSIONS[sid]
        except:
            pass
def url_decode(s):
    out = []
    i = 0
    s = s.replace('+', ' ')
    while i < len(s):
        if s[i] == '%' and i + 2 < len(s):
            try:
                out.append(chr(int(s[i+1:i+3], 16)))
                i += 3
                continue
            except:
                pass
        out.append(s[i])
        i += 1
    return ''.join(out)
def parse_body_to_dict(req):
    ctype = (req['headers'].get('content-type') or req['headers'].get('Content-Type') or '').lower()
    raw = req['body'] or b''
    try:
        s = raw.decode()
    except:
        s = ''
    if 'application/json' in ctype:
        try:
            return json.loads(s)
        except Exception as e:
            print('[WAN-DBG] JSON parse error:', repr(e), 'payload=', repr(s))
            return {}
    form = {}
    for part in s.split('&'):
        if '=' in part:
            k, v = part.split('=', 1)
            form[url_decode(k)] = url_decode(v)
    return form
def parse_multipart(req):
    headers = req.get('headers') or {}
    ct = (headers.get('content-type') or headers.get('Content-Type') or '')
    if 'multipart/form-data' not in ct:
        return {}
    import ure as _re
    m = _re.search(r'boundary=([^;]+)', ct)
    if not m:
        return {}
    boundary = m.group(1).strip()
    if boundary.startswith('"') and boundary.endswith('"'):
        boundary = boundary[1:-1]
    b_boundary = ("--" + boundary).encode()
    body = req.get('body') or b''
    parts = body.split(b_boundary)
    out = {}
    for part in parts:
        part = part.strip()
        if not part or part == b'--':
            continue
        if part.endswith(b'--'):
            part = part[:-2]
        sep = b"\r\n\r\n"
        idx = part.find(sep)
        if idx < 0:
            continue
        raw_headers = part[:idx].decode('utf-8', 'ignore')
        content = part[idx+4:]
        if content.endswith(b"\r\n"):
            content = content[:-2]
        cd_line = None
        for line in raw_headers.split("\r\n"):
            if line.lower().startswith('content-disposition:'):
                cd_line = line
                break
        if not cd_line:
            continue
        name = None
        fname = None
        m_name = _re.search(r'name="([^"]+)"', cd_line)
        if m_name:
            name = m_name.group(1)
        m_fn = _re.search(r'filename="([^"]*)"', cd_line)
        if m_fn:
            fname = m_fn.group(1)
        if not name:
            continue
        out[name] = {'filename': fname, 'content': content}
    return out
def render_template(layout_name, *, title='WanBlendr', content='', extra_css='', extra_js=''):
    layout_path = TEMPLATES_DIR + '/' + layout_name
    tpl = read_file(layout_path)
    if tpl is None:
        return b'<!DOCTYPE html><html><body><h1>Template not found</h1></body></html>'
    page = tpl
    page = page.replace('{{ title }}', str(title))
    page = page.replace('{% block extra_css %}{% endblock %}', extra_css or '')
    page = page.replace('{% block extra_js %}{% endblock %}', extra_js or '')
    if '{% block content %}{% endblock %}' in page:
        page = page.replace('{% block content %}{% endblock %}', content or '')
    else:
        page = page.replace('{{ content }}', content or '')
    return page.encode('utf-8')
def page_login(error_msg=None):
    extra_css = '<link rel="stylesheet" href="/static/css/login.css">'
    content = read_file(TEMPLATES_DIR + '/login.html') or ''
    if error_msg:
        content = content.replace('<!--LOGIN_ERROR-->', '<div class="error">%s</div>' % error_msg)
    else:
        content = content.replace('<!--LOGIN_ERROR-->', '')
    return render_template('layout_public.html', title='Login', content=content, extra_css=extra_css)
def page_interfaces():
    base = read_file(TEMPLATES_DIR + '/interfaces.html') or '<h2>Interfaces</h2>'
    return render_template('layout_private.html', title='Interfaces', content=base)
def page_vlan():
    base = read_file(TEMPLATES_DIR + '/vlan.html') or '<h2>VLAN</h2>'
    return render_template('layout_private.html', title='VLAN', content=base)
def page_lan():
    base = read_file(TEMPLATES_DIR + '/lan.html') or '<h2>LAN</h2>'
    return render_template('layout_private.html', title='LAN', content=base)
def page_wan():
    base = read_file(TEMPLATES_DIR + '/wan.html') or '<h2>WAN</h2>'
    return render_template('layout_private.html', title='WAN Interfaces', content=base)
def page_dmz():
    base = read_file(TEMPLATES_DIR + '/dmz.html') or '<h2>DMZ</h2>'
    return render_template('layout_private.html', title='DMZ', content=base)
def page_ip_tools():
    base = read_file(TEMPLATES_DIR + '/ip_tools.html') or '<h2>IP Tools</h2>'
    return render_template('layout_private.html', title='IP Tools', content=base)
def page_license():
    lic_status = license_mod.get_license_status() or ''
    ctx = {
        '%%HW_MODEL%%'      : license_mod.get_hw_model(),
        '%%MACHINE_KEY%%'   : license_mod.generate_machine_key(license_mod.get_system_id() or '') if license_mod.get_system_id() else 'N/A',
        '%%DISK_SERIAL%%'   : license_mod.get_disk_serial() or 'N/A',
        '%%SYSTEM_ID%%'     : license_mod.get_system_id() or 'N/A',
        '%%REMAINING_TIME%%': license_mod.get_remaining_time(lic_status),
        '%%LICENSE_STATUS%%': 'Done' if lic_status == 'Done' else 'Not licensed',
        '%%STATUS_CLASS%%'  : 'status-ok' if lic_status == 'Done' else 'status-not',
    }
    ctx['%%INPUT_BLOCK%%'] = '' if lic_status == 'Done' else (
        '<div class="license-input">'
        '<label for="licenseKey">License Key:</label>'
        '<input type="text" id="licenseKey" placeholder="Enter license key">'
        '<button id="checkLicenseBtn">Check</button></div>'
    )
    ctx['%%EXPORT_BLOCK%%'] = '' if lic_status == 'Done' else (
        '<div class="info-row" id="exportRow">'
        '<span class="info-label">&nbsp;</span>'
        '<button id="exportBtn" class="license-export" style="margin-left:auto">Export</button>'
        '</div>'
    )
    base = read_file(TEMPLATES_DIR + '/license.html') or '<h2>License</h2>'
    for k, v in ctx.items():
        base = base.replace(k, str(v))
    return render_template('layout_private.html', title='License', content=base)
def page_setting():
    base = read_file(TEMPLATES_DIR + '/setting.html') or '<h2>Setting</h2>'
    return render_template('layout_private.html', title='Setting', content=base)
def page_wireless():
    base = read_file(TEMPLATES_DIR + '/wireless.html') or '<h2>Wireless</h2>'
    return render_template('layout_private.html', title='Wireless', content=base)
def page_dashboard(title='Dashboard', body_html=''):
    base = read_file(TEMPLATES_DIR + '/dashboard.html') or ''
    if body_html:
        base = base.replace('<!--DASH_CONTENT-->', body_html)
    return render_template('layout_private.html', title=title, content=base)
def page_about():
    base = read_file(TEMPLATES_DIR + '/about.html') or '<h2>About</h2>'
    return render_template('layout_private.html', title='About', content=base)
DASH_PAGES = {
    'interfaces': 'Interfaces',
    'vlan': 'VLAN',
    'lan': 'LAN',
    'bridge': 'Bridge',
    'wan': 'WAN',
    'dmz': 'DMZ',
    'ip_tools': 'IP Tools',
    'license': 'License',
    'setting': 'Setting',
    'Wireless': 'Wireless'
}
async def read_request(reader):
    try:
        line = await reader.readline()
    except Exception:
        return None
    if not line:
        return None
    try:
        req_line = line.decode().strip()
    except:
        req_line = ''
    m = re.match(r'([A-Z]+)\s+(\S+)\s+HTTP/1\.[01]', req_line)
    if not m:
        return None
    method, path = m.group(1), m.group(2)
    headers = {}
    while True:
        try:
            h = await reader.readline()
        except Exception:
            return None
        if not h:
            break
        h = h.decode().strip()
        if h == '':
            break
        if ':' in h:
            k, v = h.split(':', 1)
            headers[k.strip().lower()] = v.strip()
    path_only, query = path, ''
    if '?' in path:
        path_only, query = path.split('?', 1)
    body = b''
    stream_mode = False
    if method in ('POST', 'PUT', 'PATCH'):
        cl = headers.get('content-length')
        n = 0
        try:
            n = int(cl or '0')
        except:
            n = 0
        ctype = (headers.get('content-type') or '').lower()
        if path_only == '/dashboard/setting/upload':
            stream_mode = True
        else:
            if n > 0:
                try:
                    body = await reader.readexactly(n)
                except:
                    body = await reader.read(-1)
    req = {'method': method, 'path': path_only, 'query': query,
           'headers': headers, 'body': body}
    if stream_mode:
        req['stream'] = reader
        req['content_length'] = n
    return req
async def send_response(writer, status=200, reason='OK', headers=None, body=b''):
    if headers is None:
        headers = {}
    base = {
        'Server': 'WanBlendr-uPy',
        'Connection': 'close',
        'Content-Length': str(len(body)),
    }
    for k, v in base.items():
        if k.lower() not in headers:
            headers[k] = v
    start = 'HTTP/1.1 %d %s\r\n' % (status, reason)
    try:
        writer.write(start.encode('utf-8'))
        for k, v in headers.items():
            writer.write(('%s: %s\r\n' % (k, v)).encode('utf-8'))
        writer.write(b'\r\n')
        if body:
            writer.write(body)
        await writer.drain()
    except:
        pass
async def redirect(writer, location, set_cookie=None):
    headers = {'Location': location}
    if set_cookie:
        headers['Set-Cookie'] = set_cookie
    await send_response(writer, 302, 'Found', headers=headers, body=b'')
async def handle_static(req, writer):
    rel = req['path'][len('/static/'):]
    if '..' in rel or rel.startswith('/'):
        await send_response(writer, 403, 'Forbidden', body=b'Forbidden')
        return
    path = STATIC_DIR + '/' + rel
    data = read_file(path, 'rb')
    if data is None:
        await send_response(writer, 404, 'Not Found', body=b'Not Found')
        return
    if isinstance(data, str):
        data = data.encode('utf-8')
    ctype = guess_content_type(path)
    try:
        etag = '"' + ubinascii.hexlify(uhashlib.sha1(data).digest()).decode() + '"'
    except Exception:
        etag = None
    inm = req['headers'].get('if-none-match')
    if etag and inm == etag:
        await send_response(writer, 304, 'Not Modified', headers={
            'Content-Type': ctype,
            'ETag': etag,
            'Cache-Control': 'public, max-age=0, must-revalidate'
        }, body=b'')
        return
    headers = {
        'Content-Type': ctype,
        'Cache-Control': 'public, max-age=0, must-revalidate'
    }
    if etag:
        headers['ETag'] = etag
    await send_response(writer, 200, 'OK', headers=headers, body=data)
async def handle_root(req, writer):
    sid = get_session(req['headers'])
    if sid:
        await redirect(writer, '/dashboard/interfaces')
    else:
        await redirect(writer, '/login')
async def handle_login(req, writer):
    if req['method'] == 'GET':
        body = page_login()
        await send_response(writer, 200, 'OK', headers={
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }, body=body)
        return
    if req['method'] == 'POST':
        form = {}
        body = req['body'].decode() if req['body'] else ''
        for part in body.split('&'):
            if '=' in part:
                k, v = part.split('=', 1)
                form[url_decode(k)] = url_decode(v)
        user = form.get('username', '')
        pw = form.get('password', '')
        current_store = _load_password_store()
        if user == AUTH_USER and verify_password(pw, current_store):
            sid = set_session(user)
            cookie = 'ARABSESSID=%s; HttpOnly; Path=/' % sid
            await redirect(writer, '/dashboard/interfaces', set_cookie=cookie)
        else:
            body = page_login('Invalid username or password.')
            await send_response(writer, 401, 'Unauthorized', headers={
                'Content-Type': 'text/html; charset=utf-8',
                'Cache-Control': 'no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }, body=body)
        return
    await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
async def handle_logout(req, writer):
    clear_session(req['headers'])
    await send_response(writer, 200, 'OK', headers={
        'Content-Type': 'text/html; charset=utf-8',
        'Set-Cookie': 'ARABSESSID=; Path=/; Max-Age=0',
        'Cache-Control': 'no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0'
    }, body=b'<html><body><script>location.href="/login"</script></body></html>')
async def handle_dashboard(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer, '/login')
        return
    parts = req['path'].split('/')
    sub = parts[2] if len(parts) > 2 and parts[2] else ''
    if sub == '':
        await redirect(writer, '/dashboard/interfaces')
        return
    if sub == 'vlan':
        body = page_vlan()
        await send_response(writer, 200, 'OK', headers={'Content-Type': 'text/html; charset=utf-8'}, body=body)
        return
    if sub == 'lan':
        body = page_lan()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'text/html; charset=utf-8'},
                            body=body)
        return
    if sub == 'interfaces':
        body = page_interfaces()
        await send_response(writer, 200, 'OK', headers={
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'private, no-cache, max-age=0, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }, body=body)
        return
    if sub in DASH_PAGES:
        title = DASH_PAGES[sub]
        body = page_dashboard(title, '<div class="card"><h2>%s</h2><p>Placeholder.</p></div>' % title)
        await send_response(writer, 200, 'OK', headers={
            'Content-Type': 'text/html; charset=utf-8',
            'Cache-Control': 'private, no-cache, max-age=0, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0'
        }, body=body)
        return
    await send_response(writer, 404, 'Not Found', body=b'Not Found')
async def handle_api_interfaces(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized')
        return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
        return
    try:
        data = interfaces_mod.compute_interfaces_data()
        body = json.dumps({'interfaces': data}).encode()
        await send_response(writer, 200, 'OK', headers={
            'Content-Type': 'application/json; charset=utf-8'
        }, body=body)
    except Exception as e:
        try:
            sys.print_exception(e)
        except:
            print('EXC:', e)
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=msg)
async def handle_wan_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer, '/login')
        return
    body = page_wan()
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type': 'text/html; charset=utf-8'},
                        body=body)
async def handle_wan_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized')
        return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
        return
    rows = wan_mod.build_wan_table_rows()
    body = json.dumps(rows).encode()
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type': 'application/json; charset=utf-8'},
                        body=body)
async def handle_wan_interfaces(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized')
        return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
        return
    try:
        print("[WAN-DBG] handle_wan_interfaces: collecting lists ...")
        phys_raw = wan_mod.get_physical_interfaces()
        vlan_raw = wan_mod.get_vlan_interfaces()
        print("[WAN-DBG] physical interfaces ->", phys_raw)
        print("[WAN-DBG] vlan interfaces     ->", vlan_raw)
        phys = [{'value': p, 'label': wan_mod.display_interface_name(p)} for p in phys_raw]
        vl   = [{'value': v, 'label': wan_mod.display_interface_name(v)} for v in vlan_raw]
        print("[WAN-DBG] payload physical ->", phys)
        print("[WAN-DBG] payload vlans    ->", vl)
        body = json.dumps({'physical': phys, 'vlans': vl}).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
    except Exception as e:
        try:
            import sys
            sys.print_exception(e)
        except:
            print("[WAN-DBG] EXC in handle_wan_interfaces:", e)
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=msg)
async def handle_wan_add(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized')
        return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
        return
    try:
        data = parse_body_to_dict(req)                                 
        ifname   = (data.get('ifname') or data.get('interface') or '').strip()
        proto    = (data.get('proto')  or data.get('type')      or '').strip().lower()
        comment  = (data.get('comment') or '').strip()
        username = (data.get('username') or '').strip()
        password = (data.get('password') or '').strip()
        ipaddr   = (data.get('ip_address') or '').strip()
        netmask  = (data.get('net_mask')   or '').strip()
        gateway  = (data.get('gateway')    or '').strip()
        dns      = (data.get('dns')        or '').strip()
        if not ifname or not proto:
            payload = {'ok': False, 'error': 'Missing required fields: interface/ifname and type/proto'}
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type': 'application/json; charset=utf-8'},
                                body=json.dumps(payload).encode())
            return
        payload = {
            'ifname': ifname,
            'proto': proto,
            'comment': comment,
        }
        if proto == 'pppoe':
            payload['username'] = username
            payload['password'] = password
        elif proto == 'static':
            payload['ip_address'] = ipaddr
            payload['net_mask']   = netmask
            if gateway: payload['gateway'] = gateway
            if dns:     payload['dns']     = dns
        ok, msg = wan_mod.add_wan_interface(payload)
        if ok:
            body = json.dumps({'ok': True, 'message': msg or 'saved'}).encode()
            await send_response(writer, 200, 'OK',
                                headers={'Content-Type': 'application/json; charset=utf-8'},
                                body=body)
        else:
            body = json.dumps({'ok': False, 'error': msg or 'failed'}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type': 'application/json; charset=utf-8'},
                                body=body)
    except Exception as e:
        try:
            import sys
            sys.print_exception(e)
        except:
            print('[WAN-DBG] EXC in handle_wan_add:', e)
        body = json.dumps({'ok': False, 'error': 'Unexpected server error: %s' % (str(e) or e.__class__.__name__)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
async def handle_wan_delete(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        payload = req['body'].decode() if req['body'] else ''
        d = json.loads(payload) if payload else {}
    except:
        d = {}
    nm = (d.get('name') or '').lower()
    if not nm:
        await send_response(writer, 400, 'Bad Request',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error':'Missing name'}).encode()); return
    if wan_mod.is_interface_in_mwan3(nm):
        await send_response(writer, 400, 'Bad Request',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error':'Interface in Load-balancer'}).encode()); return
    ok = wan_mod.delete_wan_interface(nm)
    if ok:
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    else:
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error':'Reload failed'}).encode())
async def handle_wan_dns_list(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b''); return
    try:
        items = wan_mod.list_dhcp_interfaces_for_dns()
        await send_response(writer, 200, 'OK',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'items': items}).encode())
    except Exception as e:
        await send_response(writer,500,'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error':str(e)}).encode())
async def handle_wan_dns_save(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b''); return
    try:
        payload = parse_body_to_dict(req) or {}
        items = payload.get('items') or []
        ok = wan_mod.save_dns_settings(items)
        await send_response(writer, 200 if ok else 500, 'OK' if ok else 'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'ok': bool(ok)}).encode())
    except Exception as e:
        await send_response(writer,500,'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error':str(e)}).encode())
async def handle_wan_get_mac_list(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    out = wan_mod.get_mac_list_for_ui()
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type':'application/json; charset=utf-8'},
                        body=json.dumps(out).encode())
async def handle_wan_edit_mac(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        payload = req['body'].decode() if req['body'] else ''
        items = json.loads(payload) if payload else []
    except:
        items = []
    if not isinstance(items, list):
        await send_response(writer, 400, 'Bad Request',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error':'Bad format'}).encode()); return
    errs = []
    for it in items:
        iface = (it.get('interface') or '')
        newmc = (it.get('new_mac') or '').upper()
        if not iface or not newmc:
            errs.append("Missing fields"); continue
        if not wan_mod.is_valid_mac(newmc):
            errs.append("Invalid MAC %s" % newmc); continue
        ok, msg = wan_mod.update_macaddr_in_network_custom(iface, newmc)
        if not ok:
            errs.append("%s: %s" % (iface, msg))
    if errs:
        await send_response(writer, 400, 'Bad Request',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': errs}).encode()); return
    ok, _ = wan_mod.commit_and_restart_network()
    if not ok:
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': 'Reload failed'}).encode()); return
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type':'application/json; charset=utf-8'},
                        body=json.dumps({'success': True}).encode())
async def handle_wan_auto(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        payload = req['body'].decode() if req['body'] else ''
        d = json.loads(payload) if payload else {}
    except:
        d = {}
    nm = (d.get('name') or '').strip()
    val = (d.get('auto') or '').strip()
    if not nm or val not in ('0','1'):
        await send_response(writer, 400, 'Bad Request',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error':'Missing/invalid fields'}).encode()); return
    ok, msg = wan_mod.set_wan_auto(nm, val)
    if ok:
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    else:
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': msg or 'Failed'}).encode())
async def handle_wan_pppoe_list(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    lst = wan_mod.get_pppoe_list_for_ui()
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type':'application/json; charset=utf-8'},
                        body=json.dumps(lst).encode())
async def handle_wan_save_yemen(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        payload = req['body'].decode() if req['body'] else ''
        selected = json.loads(payload) if payload else []
    except:
        selected = []
    ok = wan_mod.save_pppoe_selection(selected)
    if ok:
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    else:
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error':'Save failed'}).encode())
async def handle_lb_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer, '/login'); return
    body = page_load_balancer()
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type': 'text/html; charset=utf-8'},
                        body=body)
async def handle_lb_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        rows = []
        body = json.dumps({'interfaces': rows}).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=msg)
async def handle_lb_interfaces(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        lst = []
        body = json.dumps({'interfaces': lst}).encode()
        await send_response(writer, 200, 'OK',
                            headers={
                                'Content-Type':'application/json; charset=utf-8',
                                'Cache-Control':'no-store, must-revalidate',
                                'Pragma':'no-cache',
                                'Expires':'0'
                            },
                            body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=msg)
async def handle_lb_add_backup(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        data = parse_body_to_dict(req)                
        iface = (data.get('interface') or '').strip()
        ip    = (data.get('check_ip') or '').strip()
        dist  = data.get('distance_dist', 0)
        try: dist = int(dist)
        except: dist = 0
        if not (iface and ip and dist > 0):
            body = json.dumps({'error':'Missing/invalid fields'}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body); return
        ok, msg = False, 'removed'
        if not ok:
            body = json.dumps({'error': msg}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_lb_add_failover(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        data = parse_body_to_dict(req)
        iface = (data.get('interface') or '').strip()
        ip    = (data.get('check_ip') or '').strip()
        if not (iface and ip):
            body = json.dumps({'error':'Missing fields'}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body); return
        ok, msg = False, 'removed'
        if not ok:
            body = json.dumps({'error': msg}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_lb_delete(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        data = parse_body_to_dict(req)
        iface = (data.get('interface') or '').strip()
        if not iface:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error':'Missing interface'}).encode()); return
        ok, msg = False, 'removed'
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_lb_edit(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        data = parse_body_to_dict(req)
        iface = (data.get('interface') or '').strip()
        ip    = (data.get('check_ip') or '').strip()
        if not (iface and ip):
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error':'Missing fields'}).encode()); return
        ok, msg = False, 'removed'
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_sr_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer, '/login'); return
    body = page_source_routing()
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type': 'text/html; charset=utf-8'},
                        body=body)
async def handle_sr_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        rows = []
        body = json.dumps({'routes': rows}).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=msg)
async def handle_sr_interfaces(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        qraw = req.get('query', {})
        q = _coerce_query_to_dict(qraw)
        mode = (q.get('mode') or 'add').lower()
        policy_name = (q.get('policy_name') or '')
        lst = []
        body = json.dumps({'available_interfaces': lst}).encode()
        await send_response(writer, 200, 'OK',
                            headers={
                                'Content-Type':'application/json; charset=utf-8',
                                'Cache-Control':'no-store, must-revalidate',
                                'Pragma':'no-cache',
                                'Expires':'0'
                            },
                            body=body)
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except:
            pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=msg)
async def handle_sr_add(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        data = parse_body_to_dict(req)
        selected = data.get('selected_interfaces') or data.get('interfaces') or []
        if isinstance(selected, str):
            selected = [selected]
        src = (data.get('source_address') or '').strip()
        ok, msg = False, 'removed'
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True, 'rule_name': msg}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_sr_edit(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        data = parse_body_to_dict(req)
        rule_name = (data.get('rule_name') or '').strip()
        src       = (data.get('source_address') or '').strip()
        selected  = data.get('selected_interfaces') or []
        if isinstance(selected, str):
            selected = [selected]
        ok, msg = False, 'removed'
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_sr_delete(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        data = parse_body_to_dict(req)
        policy_name = (data.get('policy_name') or '').strip()
        rule_name   = (data.get('rule_name') or '').strip()
        ok, msg = False, 'removed'
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_sr_selected(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        qraw = req.get('query', {})
        q = _coerce_query_to_dict(qraw)                                  
        policy_name = (q.get('policy_name') or '').strip()
        data = []
        body = json.dumps(data).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8',
                                     'Cache-Control':'no-store, must-revalidate',
                                     'Pragma':'no-cache',
                                     'Expires':'0'},
                            body=body)
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except:
            pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_hr_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer, '/login'); return
    body = page_host_redirecting()
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type':'text/html; charset=utf-8'},
                        body=body)
async def handle_hr_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        rows = []
        body = json.dumps({'routes': rows}).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_hr_interfaces(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        q = _coerce_query_to_dict(req.get('query', {}))
        mode = (q.get('mode') or 'add').lower()
        policy_name = (q.get('policy_name') or '')
        lst = []
        body = json.dumps({'available_interfaces': lst}).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8',
                                     'Cache-Control':'no-store, must-revalidate',
                                     'Pragma':'no-cache',
                                     'Expires':'0'},
                            body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_hr_selected(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        q = _coerce_query_to_dict(req.get('query', {}))
        policy_name = (q.get('policy_name') or '').strip()
        data = []
        body = json.dumps(data).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8',
                                     'Cache-Control':'no-store, must-revalidate',
                                     'Pragma':'no-cache',
                                     'Expires':'0'},
                            body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_hr_resolve(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        q = _coerce_query_to_dict(req.get('query', {}))
        dom = (q.get('domain') or '').strip()
        if not dom:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': 'Missing domain'}).encode()); return
        addrs = []
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'addresses': addrs}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_hr_add(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)
        mode = (d.get('mode') or 'domain').lower()
        dom  = (d.get('domain') or '').strip()
        ips  = d.get('ip_list') or []
        if isinstance(ips, str):
            ips = [x for x in ips.split() if x]
        ifs  = d.get('selected_interfaces') or d.get('interfaces') or []
        if isinstance(ifs, str):
            ifs = [ifs]
        ok, msg = False, 'removed'
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True, 'policy_name': msg}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_hr_edit(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)
        policy = (d.get('policy_name') or '').strip()
        mode   = (d.get('mode') or 'domain').lower()
        dom    = (d.get('domain') or '').strip()
        ips    = d.get('ip_list') or []
        if isinstance(ips, str):
            ips = [x for x in ips.split() if x]
        ifs    = d.get('selected_interfaces') or []
        if isinstance(ifs, str):
            ifs = [ifs]
        ok, msg = False, 'removed'
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True, 'policy_name': msg}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_hr_delete(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)
        policy = (d.get('policy_name') or '').strip()
        ok, msg = False, 'removed'
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_vlan_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized')
        return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
        return
    try:
        rows = vlan_mod.list_vlan_devices_display()
        body = json.dumps(rows).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
    except Exception as e:
        try:
            import sys
            sys.print_exception(e)
        except:
            pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=msg)
async def handle_vlan_eths(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized')
        return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
        return
    try:
        eths = vlan_mod.list_virtual_eths()
        body = json.dumps(eths).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
    except Exception as e:
        try:
            import sys
            sys.print_exception(e)
        except:
            pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=msg)
async def handle_vlan_add_batch(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized')
        return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
        return
    try:
        payload = {}
        if req['body']:
            try:
                payload = json.loads(req['body'].decode())
            except:
                pass
        nic  = payload.get('nic')
        svid = payload.get('start_vlan')
        evid = payload.get('end_vlan')
        ok, added, skipped, err = vlan_mod.add_vlan_batch_from_virtual(nic, svid, evid)
        if not ok:
            msg = json.dumps({'error': err or 'Failed to add batch'}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type': 'application/json; charset=utf-8'},
                                body=msg)
            return
        msg = "Added VLANs: %s. Skipped: %s" % (added, skipped)
        body = json.dumps({'success': True, 'added': added, 'skipped': skipped, 'message': msg}).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
    except Exception as e:
        try:
            import sys
            sys.print_exception(e)
        except:
            pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=msg)
async def handle_wan_source_list_lans(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        lst = wan_mod.list_lan_network_cidrs()
        body = json.dumps({'cidrs': lst}).encode()
        await send_response(writer, 200, 'OK', headers={'Content-Type':'application/json; charset=utf-8'}, body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error', headers={'Content-Type':'application/json; charset=utf-8'}, body=json.dumps({'error': str(e)}).encode())
async def handle_wan_source_list_wans(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        lst = wan_mod.list_wan_interface_names()
        body = json.dumps({'wans': lst}).encode()
        await send_response(writer, 200, 'OK', headers={'Content-Type':'application/json; charset=utf-8'}, body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error', headers={'Content-Type':'application/json; charset=utf-8'}, body=json.dumps({'error': str(e)}).encode())
async def handle_wan_source_policies(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        rows = wan_mod.list_source_policies()
        body = json.dumps({'policies': rows}).encode()
        await send_response(writer, 200, 'OK', headers={'Content-Type':'application/json; charset=utf-8'}, body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error', headers={'Content-Type':'application/json; charset=utf-8'}, body=json.dumps({'error': str(e)}).encode())
async def handle_wan_source_add(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)
        src = (d.get('src') or '').strip()
        wan = d.get('wan')
        ok, msg = wan_mod.add_source_policy(src, wan)
        if not ok:
            await send_response(writer, 400, 'Bad Request', headers={'Content-Type':'application/json; charset=utf-8'}, body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK', headers={'Content-Type':'application/json; charset=utf-8'}, body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error', headers={'Content-Type':'application/json; charset=utf-8'}, body=json.dumps({'error': str(e)}).encode())
async def handle_wan_source_delete(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)
        idx = d.get('id')
        ok, msg = wan_mod.delete_source_policy(idx)
        if not ok:
            await send_response(writer, 400, 'Bad Request', headers={'Content-Type':'application/json; charset=utf-8'}, body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK', headers={'Content-Type':'application/json; charset=utf-8'}, body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error', headers={'Content-Type':'application/json; charset=utf-8'}, body=json.dumps({'error': str(e)}).encode())
async def handle_vlan_delete(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized')
        return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
        return
    try:
        payload = {}
        if req['body']:
            try:
                payload = json.loads(req['body'].decode())
            except:
                pass
        nic_virtual = payload.get('nic')
        vlan_id     = payload.get('vlan_id')
        if not nic_virtual or not vlan_id:
            msg = json.dumps({'error': 'Missing nic or vlan_id'}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type': 'application/json; charset=utf-8'},
                                body=msg)
            return
        nic_phys = vlan_mod.virtual_to_physical(nic_virtual)
        ok, err = vlan_mod.delete_vlan_device(nic_phys, str(vlan_id))
        if not ok:
            msg = json.dumps({'error': err or 'Delete failed'}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type': 'application/json; charset=utf-8'},
                                body=msg)
            return
        body = json.dumps({'success': True}).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
    except Exception as e:
        try:
            import sys
            sys.print_exception(e)
        except:
            pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=msg)
async def handle_lan_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        rows = lan_mod.list_lan_table()
        body = json.dumps(rows).encode()
        await send_response(writer, 200, 'OK',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=body)
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except: pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=msg)
async def handle_lan_interfaces_list(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        lst = lan_mod.interfaces_list()
        body = json.dumps(lst).encode()
        await send_response(writer, 200, 'OK',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=body)
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except: pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=msg)
async def handle_lan_add(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        payload = {}
        if req['body']:
            try: payload = json.loads(req['body'].decode())
            except: payload = {}
        ok, msg = lan_mod.add_entry(payload.get('device',''), payload.get('ip_cidr',''))
        if not ok:
            body = json.dumps({'error': msg}).encode()
            await send_response(writer, 400, 'Bad Request',
                headers={'Content-Type': 'application/json; charset=utf-8'}, body=body); return
        body = json.dumps({'success': True}).encode()
        await send_response(writer, 200, 'OK',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=body)
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except: pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=msg)
async def handle_lan_edit(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        payload = {}
        if req['body']:
            try: payload = json.loads(req['body'].decode())
            except: payload = {}
        ok, msg = lan_mod.edit_entry(payload.get('name',''), payload.get('device',''), payload.get('ip_cidr',''))
        if not ok:
            body = json.dumps({'error': msg}).encode()
            await send_response(writer, 400, 'Bad Request',
                headers={'Content-Type': 'application/json; charset=utf-8'}, body=body); return
        body = json.dumps({'success': True}).encode()
        await send_response(writer, 200, 'OK',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=body)
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except: pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=msg)
async def handle_lan_delete(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        payload = {}
        if req['body']:
            try: payload = json.loads(req['body'].decode())
            except: payload = {}
        ok, msg = lan_mod.delete_entry(payload.get('name',''))
        if not ok:
            body = json.dumps({'error': msg}).encode()
            await send_response(writer, 400, 'Bad Request',
                headers={'Content-Type': 'application/json; charset=utf-8'}, body=body); return
        body = json.dumps({'success': True}).encode()
        await send_response(writer, 200, 'OK',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=body)
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except: pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=msg)
async def handle_dmz_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer, '/login'); return
    body = page_dmz()                             
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type': 'text/html; charset=utf-8'},
                        body=body)
async def handle_dmz_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        rows = dmz_mod.list_for_ui()                                                       
        body = json.dumps({'rules': rows}).encode()
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        msg = json.dumps({'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=msg)
async def handle_dmz_add(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)                                
        dest_ip   = (d.get('dest_ip')   or '').strip()
        proto     = (d.get('proto')     or 'tcp udp').strip()
        src_dport = (d.get('src_dport') or '').strip()            
        dest_port = (d.get('dest_port') or '').strip()
        if not (dest_ip and dest_port):
            body = json.dumps({'error': 'Missing required fields (dest_ip/dest_port)'}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type': 'application/json; charset=utf-8'},
                                body=body)
            return
        print("[DMZ-ADD] dest_ip=%r proto=%r src_dport=%r dest_port=%r" %
      (dest_ip, proto, src_dport, dest_port))
        ok, dmz_id = dmz_mod.add_dmz(dest_ip, proto, src_dport, dest_port, 'wan', 'lan')
        if not ok:
            body = json.dumps({'error': dmz_id or 'Add failed'}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type': 'application/json; charset=utf-8'},
                                body=body)
            return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type': 'application/json; charset=utf-8'},
                            body=json.dumps({'success': True, 'id': dmz_id}).encode())
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except:
            pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_dmz_edit(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)                                
        dmz_id    = (d.get('id')        or '').strip()
        dest_ip   = (d.get('dest_ip')   or '').strip()
        proto     = (d.get('proto')     or 'tcp udp').strip()
        src_dport = (d.get('src_dport') or '').strip()             
        dest_port = (d.get('dest_port') or '').strip()
        if not dmz_id:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error':'Missing rule id'}).encode())
            return
        ok, msg = dmz_mod.edit_dmz(dmz_id, dest_ip, proto, src_dport, dest_port, 'wan', 'lan')
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode())
            return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except:
            pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_dmz_delete(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)
        dmz_id = (d.get('id') or '').strip()                                     
        if not dmz_id:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error':'Missing rule id'}).encode()); return
        ok, msg = dmz_mod.delete_dmz(dmz_id)
        if not ok:
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=json.dumps({'error': msg}).encode()); return
        await send_response(writer, 200, 'OK',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'success': True}).encode())
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=json.dumps({'error': str(e)}).encode())
async def handle_iptools_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer, '/login'); return
    body = page_ip_tools()
    await send_response(writer, 200, 'OK',
                        headers={'Content-Type': 'text/html; charset=utf-8'},
                        body=body)
async def handle_iptools_ping(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)                
        host  = (d.get('host')  or '').strip()
        count = d.get('count', 4)
        size  = d.get('size', 0)
        try: count = int(count)
        except: count = 4
        try: size = int(size)
        except: size = 0
        ok, out = ipt_mod.ping(host, count=count, size=size, ipv6=False)
        if ok:
            body = json.dumps({'ok': True, 'output': out}).encode()
            await send_response(writer, 200, 'OK',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body)
        else:
            body = json.dumps({'ok': False, 'error': out, 'output': out}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        body = json.dumps({'ok': False, 'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=body)
async def handle_iptools_dns(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)
        host = (d.get('host') or '').strip()
        ok, out = ipt_mod.dns_lookup(host)
        if ok:
            body = json.dumps({'ok': True, 'output': out}).encode()
            await send_response(writer, 200, 'OK',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body)
        else:
            body = json.dumps({'ok': False, 'error': out, 'output': out}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        body = json.dumps({'ok': False, 'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=body)
async def handle_iptools_traceroute(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)
        host = (d.get('host') or '').strip()
        hops = d.get('max_hops', 30)
        try: hops = int(hops)
        except: hops = 30
        ok, out = ipt_mod.traceroute(host, max_hops=hops)
        if ok:
            body = json.dumps({'ok': True, 'output': out}).encode()
            await send_response(writer, 200, 'OK',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body)
        else:
            body = json.dumps({'ok': False, 'error': out, 'output': out}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        body = json.dumps({'ok': False, 'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=body)
async def handle_iptools_tcp(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req)
        host = (d.get('host') or '').strip()
        port = d.get('port', 0)
        try: port = int(port)
        except: port = 0
        ok, out = ipt_mod.tcp_check(host, port, timeout=3)
        if ok:
            body = json.dumps({'ok': True, 'output': out}).encode()
            await send_response(writer, 200, 'OK',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body)
        else:
            body = json.dumps({'ok': False, 'error': out, 'output': out}).encode()
            await send_response(writer, 400, 'Bad Request',
                                headers={'Content-Type':'application/json; charset=utf-8'},
                                body=body)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        body = json.dumps({'ok': False, 'error': str(e)}).encode()
        await send_response(writer, 500, 'Internal Server Error',
                            headers={'Content-Type':'application/json; charset=utf-8'},
                            body=body)
async def handle_license_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer, '/login'); return
    body = page_license()
    await send_response(writer, 200, 'OK',
        headers={'Content-Type':'text/html; charset=utf-8'}, body=body)
async def handle_license_check(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    data = parse_body_to_dict(req)
    lic_key = (data.get('license_key') or '').strip()
    ok, msg = license_mod.activate_license(lic_key)
    body = {'success': ok, 'message': msg}
    status = 200 if ok else 400
    await send_response(writer, status, 'OK' if ok else 'Bad Request',
        headers={'Content-Type':'application/json; charset=utf-8'},
        body=json.dumps(body).encode())
async def handle_license_export(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        ok, payload = license_mod.export_license_package()
        data = payload.get('bytes', b'')
        mime = payload.get('mime', 'text/plain; charset=utf-8')
        filename = payload.get('filename', 'license_export.txt')
        status_code = 200 if ok and data else 500
        status_text = 'OK' if status_code == 200 else 'Internal Server Error'
        await send_response(writer, status_code, status_text,
            headers={
                'Content-Type': mime,
                'Content-Disposition': 'attachment; filename="%s"' % filename
            },
            body=data)
    except Exception as e:
        try: import sys; sys.print_exception(e)
        except: pass
        await send_response(writer, 500, 'Internal Server Error', body=b'Internal Error')
async def handle_setting_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer,'/login'); return
    body = page_setting()
    await send_response(writer,200,'OK',
        headers={'Content-Type':'text/html; charset=utf-8'}, body=body)
async def handle_about_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer,'/login'); return
    body = page_about()
    await send_response(writer,200,'OK',
        headers={'Content-Type':'text/html; charset=utf-8'}, body=body)
async def _setting_resp(writer, ok, msg):
    status = 200 if ok else 400
    body = json.dumps({'ok':ok,'message':msg} if ok else {'error':msg}).encode()
    await send_response(writer,status,'OK' if ok else 'Bad Request',
        headers={'Content-Type':'application/json; charset=utf-8'}, body=body)
async def handle_setting_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        cur = (setting_mod.read_http_port() or '')
        payload = {'current_port': cur}
        await send_response(writer, 200, 'OK',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps(payload).encode())
    except Exception as e:
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error': str(e)}).encode())
async def handle_setting_change_password(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    d = parse_body_to_dict(req)
    ok, msg = setting_mod.change_password(
        d.get('old_password') or '',
        d.get('new_password') or '',
        d.get('confirm_password') or ''
    )
    await _setting_resp(writer, ok, msg)
async def handle_setting_save_port(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    d = parse_body_to_dict(req)
    ok, msg = setting_mod.save_http_port(d.get('http_port') or '')
    await _setting_resp(writer, ok, msg)
async def handle_setting_upload(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        if req.get('stream'):
            q = req.get('query') or ''
            filename = ''
            try:
                if '_coerce_query_to_dict' in globals():
                    filename = (_coerce_query_to_dict(q).get('filename') or '').strip()
                else:
                    for part in q.split('&'):
                        if part.startswith('filename='):
                            filename = part.split('=',1)[1]
                            filename = filename.strip()
                            break
            except:
                filename = ''
            if filename not in ('5009.zip','hap-dk.zip','750g-mt.zip'):
                await _setting_resp(writer, False, "The uploaded file is not valid"); return
            target = '/tmp/' + filename
            try:
                remaining = int(req.get('content_length') or 0)
            except:
                remaining = 0
            print("[UP-DBG] upload start:", filename, "len=", remaining)
            try:
                os.remove(target)
            except:
                pass
            written = 0
            rd = req['stream']
            try:
                with open(target, 'wb') as f:
                    if remaining > 0:
                        while remaining > 0:
                            to_read = 4096 if remaining > 4096 else remaining
                            chunk = await rd.read(to_read)
                            if not chunk:
                                print("[UP-DBG] empty chunk (CL mode) -> break")
                                break
                            f.write(chunk)
                            written += len(chunk)
                            remaining -= len(chunk)
                            if written <= 16384 or remaining == 0:
                                print("[UP-DBG] wrote", written, "remaining", remaining)
                    else:
                        while True:
                            chunk = await rd.read(4096)
                            if not chunk:
                                print("[UP-DBG] EOF (unknown length)")
                                break
                            f.write(chunk)
                            written += len(chunk)
                            if written <= 16384 or (written % (256*1024) == 0):
                                print("[UP-DBG] wrote", written)
            except Exception as e:
                print("[UP-DBG] exception while streaming upload:", e)
                try: os.remove(target)
                except: pass
                await _setting_resp(writer, False, "The uploaded file is not valid")
                return
            try:
                st = os.stat(target)
                size_on_disk = st[6] if len(st) > 6 else 0
            except:
                size_on_disk = 0
            print("[UP-DBG] final size:", size_on_disk)
            if size_on_disk <= 0:
                try: os.remove(target)
                except: pass
                await _setting_resp(writer, False, "The uploaded file is not valid"); return
            await send_response(
                writer, 200, 'OK',
                headers={'Content-Type':'application/json; charset=utf-8'},
                body=json.dumps({'ok': True, 'message': 'Uploaded to /tmp', 'filename': filename}).encode()
            )
            return
        parts = parse_multipart(req)
        fw = parts.get('fw_zip') or parts.get('file')
        if not fw or not fw.get('filename'):
            await _setting_resp(writer, False, "The uploaded file is not valid"); return
        filename = fw['filename']
        if filename not in ('5009.zip','hap-dk.zip','750g-mt.zip'):
            await _setting_resp(writer, False, "The uploaded file is not valid"); return
        ok, res = setting_mod.fw_save_zip(filename, fw.get('content') or b'')
        if not ok:
            await _setting_resp(writer, False, res); return
        await send_response(
            writer, 200, 'OK',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'ok': True, 'message': 'Uploaded to /tmp', 'filename': filename}).encode()
        )
    except Exception as e:
        try:
            import sys; sys.print_exception(e)
        except:
            pass
        await _setting_resp(writer, False, "The uploaded file is not valid")
async def handle_setting_update(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    d = parse_body_to_dict(req)
    filename = (d.get('filename') or d.get('zip') or '').strip()
    status, info = setting_mod.fw_prepare_and_validate(filename)
    if status == 'invalid':
        await _setting_resp(writer, False, info)                                        
        return
    if status == 'mismatch':
        await send_response(writer, 400, 'Bad Request',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error': info}).encode())
        return
    lic_ok = False
    try:
        lic_ok = setting_mod.license_allowed()
    except:
        lic_ok = False
    if not lic_ok:
        try:
            print('Update not allowed: system is not licensed.')
        except:
            pass
        await send_response(writer, 403, 'Forbidden',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error': 'Update not allowed: system is not licensed.'}).encode())
        return
    img = info.get('image')
    await send_response(writer, 200, 'OK',
        headers={'Content-Type':'application/json; charset=utf-8'},
        body=json.dumps({'ok': True, 'message': 'يتم الان التحديث'}).encode())
    try:
        import uasyncio as asyncio
        async def _do():
            try:
                try:
                    await asyncio.sleep_ms(200)
                except:
                    await asyncio.sleep(0.2)
            except:
                pass
            try:
                setting_mod.fw_start_sysupgrade(img)
            except:
                pass
        try:
            asyncio.create_task(_do())
        except AttributeError:
            loop = asyncio.get_event_loop()
            loop.create_task(_do())
    except:
        setting_mod.fw_start_sysupgrade(img)
async def handle_setting_update_online_start(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        d = parse_body_to_dict(req) or {}
        # Always use backend default GitHub manifest URL; ignore any client-provided URL
        manifest = getattr(setting_mod, 'DEFAULT_MANIFEST_URL', '').strip()
        ok, msg = setting_mod.start_online_update(manifest)
        await send_response(writer, 200 if ok else 400, 'OK' if ok else 'Bad Request',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'ok': bool(ok), 'message': msg}).encode())
    except Exception as e:
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error': str(e)}).encode())
async def handle_setting_update_online_status(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'GET':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        st = setting_mod.online_update_status()
        await send_response(writer, 200, 'OK',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps(st).encode())
    except Exception as e:
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error': str(e)}).encode())
async def handle_setting_update_online_confirm(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized'); return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed'); return
    try:
        ok, msg = setting_mod.online_update_confirm()
        await send_response(writer, 200 if ok else 400, 'OK' if ok else 'Bad Request',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'ok': bool(ok), 'message': msg}).encode())
    except Exception as e:
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error': str(e)}).encode())
async def handle_wireless_page(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await redirect(writer,'/login'); return
    body = page_wireless()
    await send_response(writer,200,'OK',
        headers={'Content-Type':'text/html; charset=utf-8'}, body=body)
async def handle_wireless_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer,401,'Unauthorized',body=b'Unauthorized'); return
    if req['method']!='GET':
        await send_response(writer,405,'Method Not Allowed',body=b''); return
    out = {'radio0': wifi_mod.read_radio('radio0'),
           'radio1': wifi_mod.read_radio('radio1')}
    await send_response(writer,200,'OK',
        headers={'Content-Type':'application/json; charset=utf-8'},
        body=json.dumps(out).encode())
async def handle_wireless_save(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer,401,'Unauthorized',body=b'Unauthorized'); return
    data = parse_body_to_dict(req)
    radio    = data.get('radio','radio0')
    ssid     = data.get('ssid')
    key      = data.get('key')
    disabled = data.get('disabled')
    if disabled not in ('0','1',0,1,None): disabled=None
    if isinstance(disabled,str): disabled = (disabled=='1')
    ok,msg = wifi_mod.save_radio(radio, ssid=ssid, key=key, disabled=disabled)
    status = 200 if ok else 400
    await send_response(writer,status,'OK' if ok else 'Bad Request',
        headers={'Content-Type':'application/json; charset=utf-8'},
        body=json.dumps({'ok':ok,'message':msg} if ok else {'error':msg}).encode())
async def handle_reboot(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer, 401, 'Unauthorized', body=b'Unauthorized')
        return
    if req['method'] != 'POST':
        await send_response(writer, 405, 'Method Not Allowed', body=b'Method Not Allowed')
        return
    try:
        os.system('reboot')
        await send_response(writer, 200, 'OK',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=json.dumps({'status': 'rebooting'}).encode()
        )
    except Exception as e:
        await send_response(writer, 500, 'Internal Server Error',
            headers={'Content-Type': 'application/json; charset=utf-8'},
            body=json.dumps({'error': str(e)}).encode()
        )
async def handle_health_data(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer,401,'Unauthorized',body=b'Unauthorized'); return
    if req['method']!='GET':
        await send_response(writer,405,'Method Not Allowed',body=b''); return
    try:
        data = health_mod.snapshot()
        await send_response(writer,200,'OK',
            headers={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'},
            body=json.dumps(data).encode())
    except Exception as e:
        await send_response(writer,500,'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error':str(e)}).encode())
async def handle_version(req, writer):
    if req['method']!='GET':
        await send_response(writer,405,'Method Not Allowed',body=b''); return
    try:
        ver = ''
        try:
            # Prefer existing helper in setting module
            ver = setting_mod._read_local_version()
        except Exception:
            ver = ''
        await send_response(writer,200,'OK',
            headers={'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'},
            body=json.dumps({'version': ver or ''}).encode())
    except Exception as e:
        await send_response(writer,500,'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error':str(e)}).encode())
async def handle_wb_status(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer,401,'Unauthorized',body=b'Unauthorized'); return
    if req['method']!='GET':
        await send_response(writer,405,'Method Not Allowed',body=b''); return
    try:
        st = wan_mod.get_wanblendr_status()
        await send_response(writer,200,'OK',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'status': st}).encode())
    except Exception as e:
        await send_response(writer,500,'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error':str(e)}).encode())
async def handle_wb_status_detail(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer,401,'Unauthorized',body=b'Unauthorized'); return
    if req['method']!='GET':
        await send_response(writer,405,'Method Not Allowed',body=b''); return
    try:
        health  = interfaces_mod.wb_health_data()
        status_web = interfaces_mod.wb_status_web_map()
        events = interfaces_mod.wb_status_event_lines()
        await send_response(writer,200,'OK',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'health': health, 'status_web': status_web, 'events': events}).encode())
    except Exception as e:
        await send_response(writer,500,'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error':str(e)}).encode())
async def handle_wb_logs(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer,401,'Unauthorized',body=b'Unauthorized'); return
    if req['method']!='GET':
        await send_response(writer,405,'Method Not Allowed',body=b''); return
    try:
        lines = interfaces_mod.wb_logs_filtered()
        await send_response(writer,200,'OK',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'lines': lines}).encode())
    except Exception as e:
        await send_response(writer,500,'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error':str(e)}).encode())

async def handle_wan_speed_config(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer,401,'Unauthorized',body=b'Unauthorized'); return
    if req['method']!='GET':
        await send_response(writer,405,'Method Not Allowed',body=b''); return
    try:
        items = wan_mod.get_speed_config()
        await send_response(writer,200,'OK',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'items': items}).encode())
    except Exception as e:
        await send_response(writer,500,'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error':str(e)}).encode())

async def handle_wan_speed_save(req, writer):
    sid = get_session(req['headers'])
    if not sid:
        await send_response(writer,401,'Unauthorized',body=b'Unauthorized'); return
    if req['method']!='POST':
        await send_response(writer,405,'Method Not Allowed',body=b''); return
    try:
        payload = parse_body_to_dict(req) or {}
        items = payload.get('items') or []
        ok, msg = wan_mod.save_speed_settings(items)
        await send_response(writer, 200 if ok else 500, 'OK' if ok else 'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'ok': bool(ok), 'message': msg}).encode())
    except Exception as e:
        await send_response(writer,500,'Internal Server Error',
            headers={'Content-Type':'application/json; charset=utf-8'},
            body=json.dumps({'error':str(e)}).encode())


async def handle_client(reader, writer):
    req = await read_request(reader)
    if not req:
        try:
            await writer.aclose()
        except:
            pass
        return
    path = req['path']
    try:
        if path == '/':
            await handle_root(req, writer)
        elif path.startswith('/static/'):
            await handle_static(req, writer)
        elif path == '/login':
            await handle_login(req, writer)
        elif path == '/logout':
            await handle_logout(req, writer)
        elif path == '/dashboard/wan/source_lans':
            await handle_wan_source_list_lans(req, writer)
        elif path == '/dashboard/wan/source_policies':
            await handle_wan_source_policies(req, writer)
        elif path == '/dashboard/wan/source_wans':
            await handle_wan_source_list_wans(req, writer)
        elif path == '/dashboard/wan/source_add':
            await handle_wan_source_add(req, writer)
        elif path == '/dashboard/wan/source_delete':
            await handle_wan_source_delete(req, writer)
        
        elif path == '/reboot_system':
            await handle_reboot(req, writer)
        elif path == '/api/interfaces':
            await handle_api_interfaces(req, writer)
        elif path == '/dashboard/health/data':
            await handle_health_data(req, writer)
        elif path == '/dashboard/version':
            await handle_version(req, writer)
        elif path == '/dashboard/wb/status':
            await handle_wb_status(req, writer)
        elif path == '/dashboard/wb/status_detail':
            await handle_wb_status_detail(req, writer)
        elif path == '/dashboard/wb/logs':
            await handle_wb_logs(req, writer)

        elif path == '/dashboard/vlan/data':
            await handle_vlan_data(req, writer)
        elif path == '/dashboard/vlan/eths':
            await handle_vlan_eths(req, writer)
        elif path == '/dashboard/vlan/add_batch':
            await handle_vlan_add_batch(req, writer)
        elif path == '/dashboard/vlan/delete':
            await handle_vlan_delete(req, writer)
        elif path == '/dashboard/lan/data':
            await handle_lan_data(req, writer)
        elif path == '/dashboard/lan/interfaces_list':
            await handle_lan_interfaces_list(req, writer)
        elif path == '/dashboard/lan/add':
            await handle_lan_add(req, writer)
        elif path == '/dashboard/lan/edit':
            await handle_lan_edit(req, writer)
        elif path == '/dashboard/lan/delete':
            await handle_lan_delete(req, writer)
        elif path == '/dashboard/wan':
            await handle_wan_page(req, writer)
        elif path == '/dashboard/wan/data':
            await handle_wan_data(req, writer)
        elif path == '/dashboard/wan/interfaces':
            await handle_wan_interfaces(req, writer)
        elif path == '/dashboard/wan/add':
            await handle_wan_add(req, writer)
        elif path == '/dashboard/wan/delete':
            await handle_wan_delete(req, writer)
        elif path == '/dashboard/wan/auto':
            await handle_wan_auto(req, writer)
        elif path == '/dashboard/wan/dns/list':
            await handle_wan_dns_list(req, writer)
        elif path == '/dashboard/wan/dns/save':
            await handle_wan_dns_save(req, writer)
        elif path == '/dashboard/wan/speed/config':
            await handle_wan_speed_config(req, writer)
        elif path == '/dashboard/wan/speed/save':
            await handle_wan_speed_save(req, writer)
        
        elif path == '/dashboard/dmz':
            await handle_dmz_page(req, writer)
        elif path == '/dashboard/dmz/data':
            await handle_dmz_data(req, writer)
        elif path == '/dashboard/dmz/add':
            await handle_dmz_add(req, writer)
        elif path == '/dashboard/dmz/edit':
            await handle_dmz_edit(req, writer)
        elif path == '/dashboard/dmz/delete':
            await handle_dmz_delete(req, writer)
        elif path == '/dashboard/ip_tools':
            await handle_iptools_page(req, writer)
        elif path == '/dashboard/iptools/ping':
            await handle_iptools_ping(req, writer)
        elif path == '/dashboard/iptools/dns':
            await handle_iptools_dns(req, writer)
        elif path == '/dashboard/iptools/traceroute':
            await handle_iptools_traceroute(req, writer)
        elif path == '/dashboard/iptools/tcp_check':
            await handle_iptools_tcp(req, writer)
        elif path == '/dashboard/license':
            await handle_license_page(req, writer)
        elif path == '/dashboard/license/check':
            await handle_license_check(req, writer)
        elif path == '/dashboard/license/export':
            await handle_license_export(req, writer)
        elif path == '/dashboard/setting':
            await handle_setting_page(req, writer)
        elif path == '/dashboard/setting/data':
            await handle_setting_data(req, writer)
        elif path == '/dashboard/setting/change_password':
            await handle_setting_change_password(req, writer)
        elif path == '/dashboard/setting/save_port':
            await handle_setting_save_port(req, writer)
        elif path == '/dashboard/setting/upload':
            await handle_setting_upload(req, writer)
        elif path == '/dashboard/setting/update':
            await handle_setting_update(req, writer)
        elif path == '/dashboard/setting/update_online/start':
            await handle_setting_update_online_start(req, writer)
        elif path == '/dashboard/setting/update_online/status':
            await handle_setting_update_online_status(req, writer)
        elif path == '/dashboard/setting/update_online/confirm':
            await handle_setting_update_online_confirm(req, writer)
        elif path == '/dashboard/wireless':
            await handle_wireless_page(req, writer)
        elif path == '/dashboard/wireless/data':
            await handle_wireless_data(req, writer)
        elif path == '/dashboard/wireless/save':
            await handle_wireless_save(req, writer)
        elif path == '/dashboard/about':
            await handle_about_page(req, writer)
        elif path == '/dashboard' or path.startswith('/dashboard/'):
            await handle_dashboard(req, writer)
        else:
            await send_response(writer, 404, 'Not Found', body=b'Not Found')
    except Exception as e:
        err = ('Internal Error: %s' % str(e)).encode()
        await send_response(writer, 500, 'Internal Server Error', body=err)
    try:
        await writer.aclose()
    except:
        pass
server = None
CURRENT_PORT = PORT                        
async def start_http_server(port):
    global server, CURRENT_PORT
    server = await asyncio.start_server(handle_client, HOST, port)
    CURRENT_PORT = port
    print('Listening on %s:%d' % (HOST, port))
    try:
        sys.stdout.flush()
    except:
        pass
async def stop_http_server():
    global server
    if server is not None:
        try:
            server.close()
            try:
                await server.wait_closed()
            except:
                pass
        except:
            pass
        server = None
async def restart_http_server(new_port):
    global CURRENT_PORT
    old_port = CURRENT_PORT
    await stop_http_server()
    try:
        await start_http_server(new_port)
        print('[PORT] switched from %d to %d' % (old_port, new_port))
    except Exception as e:
        print('[PORT] failed to bind %d: %s ; reverting to %d' % (new_port, e, old_port))
        try:
            await start_http_server(old_port)
        except Exception as e2:
            print('[PORT] CRITICAL: cannot re-bind old port %d: %s' % (old_port, e2))
    try:
        sys.stdout.flush()
    except:
        pass
async def watch_http_port():
    global CURRENT_PORT, REQUESTED_PORT
    while True:
        await asyncio.sleep(10)
        try:
            new_req = _read_http_port_file()
            if new_req == REQUESTED_PORT:
                continue
            REQUESTED_PORT = new_req
            if new_req == CURRENT_PORT:
                continue
            print('[PORT] detected file change -> requested:', new_req, ', restarting server...')
            try:
                sys.stdout.flush()
            except:
                pass
            await restart_http_server(new_req)
        except Exception as e:
            try:
                import sys
                sys.print_exception(e)
            except:
                print('[PORT] watcher error:', e)
async def main():
    print('Starting WanBlendr server (dynamic port from %s)' % HTTP_PORT_FILE)
    try:
        await start_http_server(PORT)
    except Exception as e:
        print('Failed to start server:', e)
        try: sys.stdout.flush()
        except: pass
        return
    try:
        asyncio.create_task(watch_http_port())
        asyncio.create_task(license_loop())                       
    except AttributeError:
        loop = asyncio.get_event_loop()
        loop.create_task(watch_http_port())
        loop.create_task(license_loop())
    print('Ready. (press Ctrl+C to stop)')
    try: sys.stdout.flush()
    except: pass
    while True:
        await asyncio.sleep(3600)
def _run_forever_compat():
    loop = asyncio.get_event_loop()
    loop.create_task(main())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
try:
    _ = asyncio.run
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
except AttributeError:
    _run_forever_compat()
