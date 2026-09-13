import os
import ure as re
import ujson as json
import ubinascii
FIREWALL_FILE = "/etc/config/firewall"                         
def _read_text(path):
    try:
        with open(path, 'r') as f:
            return f.read()
    except:
        return ""
def _read_lines(path):
    try:
        with open(path, 'r') as f:
            return f.readlines()
    except:
        return []
def _atomic_write_text(path, data):
    try:
        rnd = ubinascii.hexlify(os.urandom(4)).decode()
    except:
        rnd = "tmp"
    tmp = "%s.%s.tmp" % (path, rnd)
    ok = False
    try:
        with open(tmp, 'w') as f:
            f.write(data)
        if hasattr(os, "rename"):
            os.rename(tmp, path)
        else:
            os.system("mv %s %s" % (tmp, path))
        ok = True
    except:
        try:
            os.remove(tmp)
        except:
            pass
    return ok
def _write_text(path, data):
    return _atomic_write_text(path, data)
def _service_reload():
    os.system("/etc/init.d/firewall reload")                                                                         
_DIGIT_MAP = {
    '٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9',
    '۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'7','۸':'8','۹':'9',
}
_HYPHENS = {'–':'-','—':'-','−':'-','-':'-','﹘':'-','﹣':'-'}
def _normalize_port(s):
    s = (s or '').strip()
    out = []
    for ch in s:
        if ch in _DIGIT_MAP:
            out.append(_DIGIT_MAP[ch]); continue
        if ch in _HYPHENS:
            out.append('-'); continue
        if '0' <= ch <= '9' or ch == '-':
            out.append(ch); continue                     
    return ''.join(out)
def _normalize_ipv4(s):
    s = (s or '').strip()
    out = []
    for ch in s:
        if ch in _DIGIT_MAP:
            out.append(_DIGIT_MAP[ch]); continue
        if ch == '٫':                                   
            out.append('.'); continue
        if ch == '.':
            out.append('.'); continue
        if '0' <= ch <= '9':
            out.append(ch); continue
    return ''.join(out)
def _is_ipv4(s):
    r = re.compile(
        r"^(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\."
        r"(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\."
        r"(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\."
        r"(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])$"
    )
    return True if (s and r.match(s)) else False
def _is_port_or_range(s):
    s = str(s or '').strip()
    if not s:
        return False
    if s.isdigit():
        try:
            p = int(s)
            return 1 <= p <= 65535
        except:
            return False
    if '-' in s:
        parts = s.split('-', 1)
        if len(parts) != 2:
            return False
        a = parts[0].strip()
        b = parts[1].strip()
        if not (a.isdigit() and b.isdigit()):
            return False
        try:
            ai = int(a); bi = int(b)
            return 1 <= ai <= 65535 and 1 <= bi <= 65535 and ai <= bi
        except:
            return False
    return False
def _norm_proto(s):
    s = (s or "").strip().lower()
    if s in ("any", "all", "tcpudp", "udp tcp", "tcp udp", "tcp,udp", "udp,tcp"):
        return "tcp udp"
    if s in ("tcp", "udp"):
        return s
                        
    return "tcp udp"
def _rand8():
    try:
        return ubinascii.hexlify(os.urandom(4)).decode()
    except:
        return "ab12cd34"
def _collapse_blank_lines(s):
    lines = (s or "").splitlines(True)
    out = []
    prev_blank = False
    for L in lines:
        if L.strip() == "":
            if not prev_blank:
                out.append("\n")
            prev_blank = True
        else:
            prev_blank = False
            out.append(L if L.endswith("\n") else (L + "\n"))
    if out and not out[-1].endswith("\n"):
        out[-1] = out[-1] + "\n"
    return "".join(out)
def fix_newlines(content):
    return _collapse_blank_lines(content or "")
def _build_dmz_block(dmz_id, dest_ip, proto, src_dport, dest_port, src_zone='wan', dest_zone='lan'):
    L = []
    L.append("##dmz_%s\n" % dmz_id)
    L.append("config redirect 'dmz_%s'\n" % dmz_id)
    L.append("\toption src '%s'\n" % (src_zone or 'wan'))
    L.append("\toption dest '%s'\n" % (dest_zone or 'lan'))
    L.append("\toption proto '%s'\n" % _norm_proto(proto))
    if src_dport:
        L.append("\toption src_dport '%s'\n" % src_dport)
    if dest_port:
        L.append("\toption dest_port '%s'\n" % dest_port)
    L.append("\toption dest_ip '%s'\n" % dest_ip)
    L.append("\n")
    return "".join(L)
def _append_snippet(original_content, snippet):
    text = original_content or ""
    if not snippet.endswith("\n"):
        snippet += "\n"
    if not text:
        return snippet
    return text.rstrip("\n") + "\n\n" + snippet
def parse_dmz():
    if not os.path.exists(FIREWALL_FILE):
        return []
    lines = _read_lines(FIREWALL_FILE)
    out = []
    i = 0
    n = len(lines)
    def _block_end(j):
        k = j
        while k < n:
            s = (lines[k] or "").strip()
            if s == "":
                k += 1
                break
            if s.startswith("config ") or s.startswith("##"):
                break
            k += 1
        return k - 1
    while i < n:
        s = (lines[i] or "").strip()
        if s.startswith("##dmz_"):
            idpart = s[6:]
            j = i + 1
            if j < n and (lines[j] or "").strip().startswith("config redirect"):
                k = j + 1
                proto = ''
                src_dport = ''
                dest_port = ''
                dest_ip = ''
                src_zone = 'wan'
                dest_zone = 'lan'
                while k < n:
                    t = (lines[k] or "").strip()
                    if t == "" or t.startswith("##") or t.startswith("config "):
                        break
                    m = re.match(r"^option\s+proto\s+'([^']+)'$", t)
                    if m:
                        proto = m.group(1); k += 1; continue
                    m = re.match(r"^option\s+src_dport\s+'([^']+)'$", t)
                    if m:
                        src_dport = m.group(1); k += 1; continue
                    m = re.match(r"^option\s+dest_port\s+'([^']+)'$", t)
                    if m:
                        dest_port = m.group(1); k += 1; continue
                    m = re.match(r"^option\s+dest_ip\s+'([^']+)'$", t)
                    if m:
                        dest_ip = m.group(1); k += 1; continue
                    m = re.match(r"^option\s+src\s+'([^']+)'$", t)
                    if m:
                        src_zone = m.group(1); k += 1; continue
                    m = re.match(r"^option\s+dest\s+'([^']+)'$", t)
                    if m:
                        dest_zone = m.group(1); k += 1; continue
                    k += 1
                end = _block_end(k)
                out.append({
                    'id': idpart,
                    'proto': proto,
                    'src_dport': src_dport,
                    'dest_port': dest_port,
                    'dest_ip': dest_ip,
                    'src_zone': src_zone,
                    'dest_zone': dest_zone,
                    'start': i,
                    'end': end
                })
                i = end + 1
                continue
        mname = re.match(r"^config\s+redirect\s+'(dmz_[^']+)'$", s)
        if mname:
            idpart = mname.group(1)[4:]
            k = i + 1
            proto = ''
            src_dport = ''
            dest_port = ''
            dest_ip = ''
            src_zone = 'wan'
            dest_zone = 'lan'
            while k < n:
                t = (lines[k] or "").strip()
                if t == "" or t.startswith("##") or t.startswith("config "):
                    break
                m = re.match(r"^option\s+proto\s+'([^']+)'$", t)
                if m:
                    proto = m.group(1); k += 1; continue
                m = re.match(r"^option\s+src_dport\s+'([^']+)'$", t)
                if m:
                    src_dport = m.group(1); k += 1; continue
                m = re.match(r"^option\s+dest_port\s+'([^']+)'$", t)
                if m:
                    dest_port = m.group(1); k += 1; continue
                m = re.match(r"^option\s+dest_ip\s+'([^']+)'$", t)
                if m:
                    dest_ip = m.group(1); k += 1; continue
                m = re.match(r"^option\s+src\s+'([^']+)'$", t)
                if m:
                    src_zone = m.group(1); k += 1; continue
                m = re.match(r"^option\s+dest\s+'([^']+)'$", t)
                if m:
                    dest_zone = m.group(1); k += 1; continue
                k += 1
            end = _block_end(k)
            out.append({
                'id': idpart,
                'proto': proto,
                'src_dport': src_dport,
                'dest_port': dest_port,
                'dest_ip': dest_ip,
                'src_zone': src_zone,
                'dest_zone': dest_zone,
                'start': i,
                'end': end
            })
            i = end + 1
            continue
        i += 1
    return out
def list_for_ui():
    arr = []
    for e in parse_dmz():
        proto = e.get('proto') or ''
        pl = proto.replace(',', ' ').lower().strip()
        proto_disp = 'ALL' if pl == 'tcp udp' else proto.upper()
        ports = e.get('src_dport') or ''
        if e.get('dest_port'):
            ports = "%s → %s" % ((e.get('src_dport') or ''), e.get('dest_port'))
        arr.append({
            'ID': e.get('id') or '',
            'Host': e.get('dest_ip') or '',
            'Proto': proto_disp,
            'Ports': ports,
            'SrcZone': e.get('src_zone') or 'wan',
            'DestZone': e.get('dest_zone') or 'lan'
        })
    return arr
def add_dmz(dest_ip, proto, src_dport, dest_port, src_zone='wan', dest_zone='lan'):
    dest_ip   = _normalize_ipv4(dest_ip)
    src_dport = _normalize_port(src_dport)
    dest_port = _normalize_port(dest_port)
    src_zone  = (src_zone or 'wan').strip() or 'wan'
    dest_zone = (dest_zone or 'lan').strip() or 'lan'
    if not _is_ipv4(dest_ip):
        return False, "Invalid IPv4 for dest_ip"
    if src_dport and not _is_port_or_range(src_dport):
        return False, "Invalid src_dport"
    if dest_port and not _is_port_or_range(dest_port):
        return False, "Invalid dest_port"
    dmz_id = _rand8()
    block = _build_dmz_block(dmz_id, dest_ip, proto, src_dport, dest_port, src_zone, dest_zone)
    content = _read_text(FIREWALL_FILE)
    content = _append_snippet(content, block)
    content = fix_newlines(content)
    if not _write_text(FIREWALL_FILE, content):
        return False, "Write failed"
    _service_reload()
    return True, dmz_id
def _replace_block(lines, dmz_id, new_block_text):
    out = []
    i = 0
    n = len(lines)
    inserted = False
    new_lines = (new_block_text if new_block_text.endswith("\n") else (new_block_text + "\n")).splitlines(True)
    def _skip_block(idx):
        j = idx + 1
        if j < n and (lines[j] or "").strip().startswith("config redirect"):
            j += 1
            while j < n:
                st = (lines[j] or "").strip()
                if st == "":
                    j += 1
                    break
                if st.startswith("config ") or st.startswith("##"):
                    break
                j += 1
        return j
    while i < n:
        s = (lines[i] or "").strip()
        if s == ("##dmz_" + dmz_id):
            out.extend(new_lines)
            i = _skip_block(i)
            inserted = True
            continue
        out.append(lines[i])
        i += 1
    return out, inserted
def edit_dmz(dmz_id, dest_ip, proto, src_dport, dest_port, src_zone='wan', dest_zone='lan'):
    dmz_id    = (dmz_id or '').strip()
    dest_ip   = _normalize_ipv4(dest_ip)
    src_dport = _normalize_port(src_dport)
    dest_port = _normalize_port(dest_port)
    src_zone  = (src_zone or 'wan').strip() or 'wan'
    dest_zone = (dest_zone or 'lan').strip() or 'lan'
    if not dmz_id:
        return False, "Missing id"
    if not _is_ipv4(dest_ip):
        return False, "Invalid IPv4 for dest_ip"
    if src_dport and not _is_port_or_range(src_dport):
        return False, "Invalid src_dport"
    if dest_port and not _is_port_or_range(dest_port):
        return False, "Invalid dest_port"
    block = _build_dmz_block(dmz_id, dest_ip, proto, src_dport, dest_port, src_zone, dest_zone)
    lines = _read_lines(FIREWALL_FILE)
    if not lines:
        return False, "Configuration not found"
    lines2, ok = _replace_block(lines, dmz_id, block)
    if not ok:
        return False, "Rule not found"
    text = "".join(lines2)
    text = fix_newlines(text)
    if not _write_text(FIREWALL_FILE, text):
        return False, "Write failed"
    _service_reload()
    return True, dmz_id
def delete_dmz(dmz_id):
    dmz_id = (dmz_id or '').strip()
    if not dmz_id:
        return False, "Missing id"
    lines = _read_lines(FIREWALL_FILE)
    if not lines:
        return False, "Configuration not found"
    out = []
    i = 0
    n = len(lines)
    def _skip_block(idx):
        j = idx + 1
                                                                                          
        if j < n and (lines[j] or "").strip().startswith("config redirect"):
            j += 1
            while j < n:
                st = (lines[j] or "").strip()
                if st == "":
                    j += 1
                    break
                if st.startswith("config ") or st.startswith("##"):
                    break
                j += 1
        return j
    removed = False
    while i < n:
        s = (lines[i] or "").strip()
        if s == ("##dmz_" + dmz_id):
            i = _skip_block(i)
            removed = True
            continue
                                                              
        m = re.match(r"^config\s+redirect\s+'([^']+)'$", s)
        if m and m.group(1) == ("dmz_" + dmz_id):
            i = _skip_block(i)
            removed = True
            continue
        out.append(lines[i])
        i += 1
    if not removed:
        return False, "Rule not found"
    text = "".join(out)
    text = fix_newlines(text)
    if not _write_text(FIREWALL_FILE, text):
        return False, "Write failed"
    _service_reload()
    return True, ""
