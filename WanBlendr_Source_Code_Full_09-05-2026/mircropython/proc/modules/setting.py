import os
import ubinascii
import uhashlib
import ujson as json
import utime as time
import ure as re
HTTP_PORT_FILE = '/mnt/ser/http_port'
PASS_FILE = '/mnt/ser/admin_password'
DEFAULT_MANIFEST_URL = 'https://raw.githubusercontent.com/abdulkader-alrezej/WanBlendr/refs/heads/main/update_link.txt'
CURL_UA = "WanBlendr/1.0"
FW_ALLOWED = {
    "5009.zip": "5009",
    "hap-dk.zip": "hap-dk",
    "750g-mt.zip": "750g-mt",
}
FW_PASSWORD = '_01@55_hello_568!@_0_'
TMP_DIR = "/tmp"
FW_DL_OUTPUT = "/tmp/fmupWanBlendr"
FW_DL_PROGRESS = "/tmp/fw_dl.progress"
FW_DL_TOTAL = "/tmp/fw_dl.total"
FW_ONLINE_STATE = "/tmp/fw_online.state"
FW_ONLINE_DEBUG = "/tmp/fw_online.debug"
ONLINE_DEBUG = True
FW_MANIFEST_RAW = "/tmp/fw_manifest.raw"
FW_MANIFEST_HDR = "/tmp/fw_manifest.hdr"
FW_MANIFEST_TRACE = "/tmp/fw_manifest.trace"
FW_HTTP_COOKIE = "/tmp/fw_http.cookie"
                                         
def license_allowed():
    try:
        with open('/sbin/ubsd', 'r') as f:
            enc = f.read().strip()
    except:
        enc = ''
    if not enc:
        return False
    try:
        dec = ubinascii.a2b_base64(enc)
    except:
        return False
    try:
        dec_txt = dec.decode()
    except:
        return False
    return dec_txt == 'ok!'
def _tmp_join(name):
    if name not in FW_ALLOWED:
        return None
    return "%s/%s" % (TMP_DIR, name)
def _out_dir_for(filename):
    base = FW_ALLOWED.get(filename)
    if not base:
        return None, None
    return "%s/%s" % (TMP_DIR, base), base
def _read_board_identifier():
    path = "/sys/firmware/mikrotik/hard_config/board_identifier"
    try:
        with open(path, "r") as f:
            return (f.read() or "").strip()
    except:
        return ""
def _rm_rf(path):
    try:
        os.system('rm -rf "%s"' % path.replace('"', ''))
    except:
        pass
def _del_if_exists(path):
    try:
        os.remove(path)
    except:
        pass
def _cmd_exists(cmd):
    try:
        rc = os.system('command -v %s >/dev/null 2>&1' % cmd)
        if rc == 0:
            return True
    except:
        pass
    if cmd == 'sysupgrade':
        return os.path.exists('/sbin/sysupgrade') or os.path.exists('/usr/sbin/sysupgrade')
    if cmd == 'unzip':
        return os.path.exists('/usr/bin/unzip') or os.path.exists('/bin/unzip')
    return False
def _sysupgrade_path():
    # Prefer explicit absolute path to avoid PATH issues under non-login shells
    try:
        if os.path.exists('/sbin/sysupgrade'):
            return '/sbin/sysupgrade'
    except:
        pass
    try:
        if os.path.exists('/usr/sbin/sysupgrade'):
            return '/usr/sbin/sysupgrade'
    except:
        pass
    return None
def _dbg(msg):
    try:
        if not ONLINE_DEBUG:
            return
        try:
            print("[UPD-DBG]", msg)
        except:
            pass
        try:
            with open(FW_ONLINE_DEBUG, 'a') as f:
                f.write("[UPD-DBG] %s\n" % (msg if isinstance(msg, str) else str(msg)))
        except:
            pass
    except:
        pass
def _stat_size(path):
    try:
        st = os.stat(path)
        return int(st[6] if len(st) > 6 else 0)
    except:
        return 0
def _read_text(path):
    try:
        with open(path, 'r') as f:
            return f.read()
    except:
        return ''
def _write_text(path, txt):
    try:
        with open(path, 'w') as f:
            f.write(txt if isinstance(txt, str) else str(txt))
        return True
    except:
        return False
def _write_bytes(path, data):
    try:
        with open(path, 'wb') as f:
            if isinstance(data, bytes):
                f.write(data)
            else:
                try:
                    f.write(bytes(data))
                except:
                    return False
        return True
    except:
        return False
def _sha256_hex(s):
    try:
        h = uhashlib.sha256(s.encode('utf-8')).digest()
    except:
        h = uhashlib.sha256(bytes(s)).digest()
    return ubinascii.hexlify(h).decode()
def verify_password(plain, stored):
    if stored.startswith('sha256:'):
        return _sha256_hex(plain) == stored.split(':', 1)[1]
    if stored.startswith('plain:'):
        return plain == stored[6:]
    return plain == stored
def load_stored_password():
    try:
        with open(PASS_FILE) as f:
            return f.read().strip()
    except:
        return 'plain:admin123'
def change_password(old_pw, new_pw, confirm):
    if new_pw != confirm:
        return False, "Passwords do not match"
    stored = load_stored_password()
    if not verify_password(old_pw, stored):
        return False, "Old password incorrect"
    new_line = 'sha256:' + _sha256_hex(new_pw)
    try:
        with open(PASS_FILE, 'w') as f:
            f.write(new_line + '\n')
        return True, "Password changed successfully"
    except:
        return False, "Cannot write password file"
def read_http_port():
    try:
        for ln in open(HTTP_PORT_FILE):
            ln = ln.strip()
            if ln.startswith('port='):
                return ln.split('=', 1)[1].strip()
    except:
        pass
    return ''
def save_http_port(port_str):
    try:
        p = int(port_str)
        if not (1 <= p <= 9999):
            raise ValueError
    except:
        return False, "Port must be 1-9999"
    try:
        with open(HTTP_PORT_FILE, 'w') as f:
            f.write('port=%d\n' % p)
        return True, "Port saved – server will move automatically"
    except:
        return False, "Cannot write http_port file"
def fw_save_zip(filename, data_bytes):
    target = _tmp_join(filename)
    if (not target) or (data_bytes is None):
        return False, "The uploaded file is not valid"
    try:
        _del_if_exists(target)
        with open(target, "wb") as f:
            f.write(data_bytes)
        if _stat_size(target) <= 0:
            return False, "The uploaded file is not valid"
        return True, target
    except:
        return False, "The uploaded file is not valid"
def fw_prepare_and_validate(filename):
    zip_path = _tmp_join(filename)
    if (not zip_path) or (not os.path.exists(zip_path)):
        return ('invalid', "The uploaded file is not valid")
    out_dir, base = _out_dir_for(filename)
    if not out_dir:
        _del_if_exists(zip_path)
        return ('invalid', "The uploaded file is not valid")
    _rm_rf(out_dir)
    try:
        os.mkdir(out_dir)
    except:
        pass
    if not _cmd_exists('unzip'):
        _del_if_exists(zip_path)
        _rm_rf(out_dir)
        return ('invalid', "The uploaded file is not valid")
    unzip_cmd = 'unzip -o -P "%s" "%s" -d "%s"' % (FW_PASSWORD.replace('"', ''), zip_path.replace('"', ''), out_dir.replace('"', ''))
    rc = os.system(unzip_cmd)
    img_expected = "%s/upd_%s" % (out_dir, base)
    if (rc != 0) or (not os.path.exists(img_expected)):
        _del_if_exists(zip_path)
        _rm_rf(out_dir)
        return ('invalid', "The uploaded file is not valid")
    board_id = _read_board_identifier()
    if not board_id:
        _del_if_exists(zip_path)
        _rm_rf(out_dir)
        return ('invalid', "The uploaded file is not valid")
    if board_id.strip() != base.strip():
        _del_if_exists(zip_path)
        _rm_rf(out_dir)
        return ('mismatch', "The Firmware is not intended for this Router and has been deleted ~/tmp/firmware/updateFW.")
    if not _cmd_exists('sysupgrade'):
        _del_if_exists(zip_path)
        _rm_rf(out_dir)
        return ('invalid', "The uploaded file is not valid")
    return ('ok', {'image': img_expected})
def fw_start_sysupgrade(image_path):
                                                      
    try:
        with open('/sbin/ubsd', 'r') as f:
            enc = f.read().strip()
    except:
        enc = ''
    try:
        dec = ubinascii.a2b_base64(enc) if enc else b''
    except:
        dec = b''
    if (not dec) or (dec.decode() != 'ok!'):
        try:
            print('Update not allowed: system is not licensed.')
        except:
            pass
        return                                                     
                                   
    try:
        try:
            time.sleep_ms(200)
        except:
            try:
                time.sleep(0.2)
            except:
                pass
    except:
        pass
    # Resolve sysupgrade absolute path and execute explicitly to avoid PATH problems (e.g., remote/NAT sessions)
    sup = _sysupgrade_path()
    if not sup:
        try:
            print('sysupgrade binary not found')
        except:
            pass
        return
    # Best-effort flush before upgrade
    try:
        os.system('sync')
    except:
        pass
    os.system('%s -v -n -F "%s" >/tmp/sysupgrade.log 2>&1' % (sup, image_path.replace('"', '')))
def fw_cleanup_all(filename):
    zip_path = _tmp_join(filename)
    out_dir, _ = _out_dir_for(filename)
    if zip_path:
        _del_if_exists(zip_path)
    if out_dir:
        _rm_rf(out_dir)
def _capture_cmd(cmd):
    try:
        rnd = ubinascii.hexlify(os.urandom(3)).decode()
    except:
        rnd = "tmp%06d" % (os.urandom(1)[0] if hasattr(os, "urandom") else 0)
    tmp = "/tmp/_cap_%s.txt" % rnd
    os.system("%s > %s 2>&1" % (cmd, tmp))
    out = _read_text(tmp) or ""
    try:
        os.remove(tmp)
    except:
        pass
    return out
def _read_local_version():
    try:
        txt = _read_text("/mnt/ser/WanBlendr_Ver") or ""
        for ln in txt.splitlines():
            s = (ln or '').strip()
            if s.startswith("ver="):
                v = s.split("=",1)[1].strip().strip("'\"")
                return v
    except:
        pass
    return ""
def _version_tuple(v):
    s = (v or '').strip()
    parts = s.split('.')
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except:
            try:
                out.append(int(''.join([c for c in p if c.isdigit()])))
            except:
                out.append(0)
    while len(out) < 3:
        out.append(0)
    return tuple(out[:3])
def _detect_device_key():
    dev = (_read_text("/sys/firmware/mikrotik/hard_config/board_identifier") or "").strip()
    if not dev:
        model = (_read_text("/proc/device-tree/model") or "").strip()
        if ("KT-708" in model) or ("KT-704" in model):
            return ">> KT-708 & >> KT-704"
        dev = model
    return dev
def _parse_manifest(manifest_txt):
    try:
        _write_text(FW_MANIFEST_RAW, manifest_txt or '')
    except:
        pass
    items = []
    try:
        # Robust, regex-free parser for lines like:
        # WanBelndrVER='3.6'_DEV='750g-mt'_WanBlendrURL='https://.../upd_750g-mt'
        for ln in (manifest_txt or "").splitlines():
            s = (ln or '').strip()
            if not s or s.startswith('#'):
                continue
            rec = {'ver':'','dev':'','url':''}
            for key, dst in (('WanBelndrVER','ver'), ('DEV','dev'), ('WanBlendrURL','url')):
                marker = key + "='"
                i = s.find(marker)
                if i >= 0:
                    j = s.find("'", i + len(marker))
                    if j > i:
                        val = s[i+len(marker):j]
                        rec[dst] = (val or '').strip()
            if rec['ver'] and rec['dev']:
                items.append(rec)
    except:
        pass
    return items
def _gdrive_to_direct(url):
    try:
        s = (url or '').strip()
        # Match /file/d/<ID>/view?... → uc?export=download&id=<ID>
        m = re.search(r'/file/+/d/+([^/]+)/+', s)
        if not m:
            m = re.search(r'/file/d/([^/]+)/', s)
        if m:
            fid = (m.group(1) or '').strip()
            if fid:
                return "https://drive.google.com/uc?export=download&id=%s" % fid
    except:
        pass
    return url
def _html_unescape_amp(s):
    try:
        return (s or '').replace('&amp;', '&')
    except:
        return s
def _read_tail(path, max_bytes=2000):
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            if size <= max_bytes:
                f.seek(0)
                data = f.read()
            else:
                f.seek(size - max_bytes)
                data = f.read()
        try:
            return data.decode(errors='ignore')
        except:
            return ''
    except:
        return ''
def _hex_head(path, max_bytes=256):
    try:
        with open(path, 'rb') as f:
            data = f.read(max_bytes)
        if not data:
            return ''
        try:
            import ubinascii as binmod
        except:
            binmod = None
        out = []
        for i in range(0, len(data), 16):
            chunk = data[i:i+16]
            hexs = ' '.join(['%02X' % b for b in chunk])
            if len(chunk) < 16:
                hexs = hexs + ' ' * (3*(16-len(chunk)))
            try:
                ascii_s = ''.join([chr(b) if 32 <= b <= 126 else '.' for b in chunk])
            except:
                ascii_s = ''
            out.append("%04X  %s  |%s|" % (i, hexs, ascii_s))
        return '\n'.join(out)
    except:
        return ''
def _parse_pct_from_text(prog_txt):
    try:
        s = prog_txt or ''
        # Find last '%' and read preceding digits
        idx = s.rfind('%')
        if idx <= 0:
            return -1
        j = idx - 1
        digits = []
        while j >= 0:
            ch = s[j]
            if not ('0' <= ch <= '9'):
                break
            digits.append(ch)
            j -= 1
        digits.reverse()
        if not digits:
            return -1
        val = int(''.join(digits))
        if val < 0: val = 0
        if val > 100: val = 100
        return val
    except:
        return -1
def start_online_update(manifest_url):
    try:
        try: os.remove(FW_DL_PROGRESS)
        except: pass
        try: os.remove(FW_ONLINE_STATE)
        except: pass
        try: os.remove(FW_MANIFEST_RAW)
        except: pass
        try: os.remove(FW_MANIFEST_TRACE)
        except: pass
        try:
            os.remove(FW_ONLINE_DEBUG)
        except:
            pass
        url = (manifest_url or '').strip()
        if not url:
            url = DEFAULT_MANIFEST_URL
        if not url:
            return False, "Bad manifest URL"
        _dbg("Starting online update. Manifest URL: %s" % url)
        # Basic internet connectivity check (busybox ping)
        ping_out = _capture_cmd("ping -c 1 -W 2 8.8.8.8 2>&1")
        _dbg("Ping 8.8.8.8 output:\n%s" % ping_out)
        if (("1 received" not in ping_out) and ("1 packets received" not in ping_out) and ("bytes from" not in ping_out)):
            return False, "Internet connectivity is required"
        # Safe-escape single quotes for shell
        safe_url = url.replace("'", "'\\''")
        # Fetch manifest headers for diagnostics
        head_cmd = "curl -A '%s' -sSLI --connect-timeout 10 --max-time 30 -c '%s' -b '%s' '%s'" % (CURL_UA, FW_HTTP_COOKIE, FW_HTTP_COOKIE, safe_url)
        hdr_txt = _capture_cmd(head_cmd) or ''
        _write_text(FW_MANIFEST_HDR, hdr_txt)
        if hdr_txt:
            first = (hdr_txt.splitlines() or [''])[0]
            _dbg("Manifest HEAD first line: %s" % first)
        else:
            _dbg("Manifest HEAD empty")
        # Fetch manifest body
        body_cmd = "curl -A '%s' -fSL --connect-timeout 10 --max-time 30 -c '%s' -b '%s' '%s' -o '%s'" % (CURL_UA, FW_HTTP_COOKIE, FW_HTTP_COOKIE, safe_url, FW_MANIFEST_RAW)
        _dbg("Fetching manifest with: %s" % body_cmd)
        os.system(body_cmd)
        man_txt = _read_text(FW_MANIFEST_RAW) or ''
        _dbg("Manifest bytes: %d" % len(man_txt))
        _dbg("Manifest preview:\n%s" % ((man_txt[:512] + ('...' if len(man_txt) > 512 else '')) if man_txt else '(empty)'))
        if not man_txt.strip():
            return False, "Cannot fetch manifest"
        items = _parse_manifest(man_txt)
        _dbg("Parsed %d manifest entries" % (len(items) if items else 0))
        if not items:
            return False, "Manifest is empty"
        local_ver = _read_local_version() or "0.0.0"
        dev_key = _detect_device_key()
        _dbg("Local version: %s, Device key: %s" % (local_ver, dev_key))
        best = None
        for it in items:
            if it.get('dev') == dev_key:
                if (best is None) or (_version_tuple(it['ver']) > _version_tuple(best['ver'])):
                    best = it
        _dbg("Best match: %s" % (json.dumps(best) if best else "None"))
        if not best:
            return False, "Device not found"
        if _version_tuple(best['ver']) <= _version_tuple(local_ver):
            return False, "Already up-to-date"
        if not license_allowed():
            return False, "Update not allowed: system is not licensed."
        dl = (best.get('url') or '').strip()
        if not dl:
            _dbg("Selected device has empty WanBlendrURL – no update available")
            return False, "No update available"
        safe_dl = dl.replace("'", "'\\''")
        # Try to discover total size for progress calculation
        try:
            os.remove(FW_DL_TOTAL)
        except:
            pass
        try:
            head_cmd2 = "curl -A '%s' -sSLI --connect-timeout 7 --max-time 20 -c '%s' -b '%s' '%s'" % (CURL_UA, FW_HTTP_COOKIE, FW_HTTP_COOKIE, safe_dl)
            hdr = _capture_cmd(head_cmd2) or ''
            for ln in (hdr.splitlines() if hdr else []):
                s = (ln or '').strip().lower()
                if s.startswith('content-length:'):
                    try:
                        t = int(s.split(':',1)[1].strip())
                        if t > 0:
                            _write_text(FW_DL_TOTAL, str(t))
                            _dbg("Firmware content-length: %d" % t)
                            break
                    except:
                        pass
        except Exception as e:
            pass
        try:
            os.remove(FW_DL_OUTPUT)
        except:
            pass
        # Start curl with progress-bar only; status watcher will flip to 'ready' when complete
        cmd = "sh -c \"curl -A '%s' -fSL --progress-bar -c '%s' -b '%s' '%s' -o '%s' 2> '%s'\"" % (CURL_UA, FW_HTTP_COOKIE, FW_HTTP_COOKIE, safe_dl, FW_DL_OUTPUT, FW_DL_PROGRESS)
        os.system("rm -f '%s' '%s'" % (FW_DL_OUTPUT, FW_ONLINE_STATE))
        _write_text(FW_ONLINE_STATE, "downloading")
        try:
            _dbg("Launching download: %s" % cmd)
            os.system("%s &" % cmd)
        except:
            os.system(cmd)
        return True, "Downloading"
    except Exception as e:
        try:
            return False, str(e)
        except:
            return False, "Unexpected error"
def online_update_status():
    # returns {'state': 'idle|downloading|ready|error', 'progress': int, 'message': str}
    try:
        state = (_read_text(FW_ONLINE_STATE) or '').strip() or 'idle'
        prog_txt = _read_text(FW_DL_PROGRESS) or ''
        pct = -1
        # Prefer computed percent from file size vs total if available
        try:
            total = int((_read_text(FW_DL_TOTAL) or "0").strip() or "0")
        except:
            total = 0
        size_now = _stat_size(FW_DL_OUTPUT)
        if total > 0 and size_now > 0:
            try:
                pct = int((size_now * 100) / total)
                if pct > 100: pct = 100
            except:
                pct = -1
        if prog_txt:
            # extract last NN% in a way compatible with MicroPython
            p2 = _parse_pct_from_text(prog_txt)
            if p2 >= 0:
                pct = max(pct, p2) if pct >= 0 else p2
        if (state != 'upgrading') and os.path.exists(FW_DL_OUTPUT) and _stat_size(FW_DL_OUTPUT) > 0 and (pct >= 100 or (total > 0 and size_now >= total)):
            state = 'ready'
        out = {
            'state': state,
            'progress': (pct if pct >= 0 else 0),
            'message': '',
        }
        return out
    except:
        return {'state': 'error', 'progress': 0, 'message': 'status error'}
def online_update_confirm():
    try:
        # Verify file present
        sz = _stat_size(FW_DL_OUTPUT)
        if sz <= 0:
            return False, "No downloaded update found"
        if not license_allowed():
            return False, "Update not allowed: system is not licensed."
        sup = _sysupgrade_path() or "/sbin/sysupgrade"
        _write_text(FW_ONLINE_STATE, "upgrading")
        cmd = "sh -c \"echo upgrading > '%s' && %s -v -n -F '%s' >>/tmp/sysupgrade.log 2>&1\"" % (FW_ONLINE_STATE, sup, FW_DL_OUTPUT)
        os.system("%s &" % cmd)
        return True, "Upgrading"
    except Exception as e:
        return False, str(e)
