import os
import ure as re
import ubinascii
import utime as time
import usocket as socket
_DIGIT_MAP = {
    '٠':'0','١':'1','٢':'2','٣':'3','٤':'4','٥':'5','٦':'6','٧':'7','٨':'8','٩':'9',
    '۰':'0','۱':'1','۲':'2','۳':'3','۴':'4','۵':'5','۶':'6','۷':'8','۸':'8','۹':'9',
}
_DIGIT_MAP['۷'] = '7'
def _normalize_host(s):
    s = (s or '').strip()
    out = []
    for ch in s:
        if ch in _DIGIT_MAP:
            out.append(_DIGIT_MAP[ch]); continue
        if ch == '٫':                                   
            out.append('.'); continue
        if ch == '.':
            out.append('.'); continue
                                       
        oc = ord(ch)
        if (48 <= oc <= 57) or (65 <= oc <= 90) or (97 <= oc <= 122) or ch in ('-',):
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
def _is_domain(s):
    if not s or s.startswith('.') or s.endswith('.') or '..' in s:
        return False
    if len(s) > 253:
        return False
    parts = s.split('.')
    for p in parts:
        if not p or len(p) > 63:
            return False
        for ch in p:
            oc = ord(ch)
            if not ((48 <= oc <= 57) or (65 <= oc <= 90) or (97 <= oc <= 122) or ch == '-'):
                return False
        if p[0] == '-' or p[-1] == '-':
            return False
    return True
def _normalize_int(s, default=0, lo=None, hi=None):
    try:
        if isinstance(s, (int, float)):
            v = int(s)
        else:
            txt = ('' if s is None else str(s)).strip()
            if txt:
                                                   
                txt = ''.join(_DIGIT_MAP.get(ch, ch) for ch in txt)
                v = int(txt)
            else:
                v = default
    except:
        v = default
    if lo is not None and v < lo:
        v = lo
    if hi is not None and v > hi:
        v = hi
    return v
def _rand8():
    try:
        return ubinascii.hexlify(os.urandom(4)).decode()
    except:
        return "ab12cd34"
def _read_text(path):
    try:
        with open(path, 'r') as f:
            return f.read()
    except:
        return ""
def _safe_unlink(path):
    try:
        os.remove(path)
    except:
        pass
def _run_cmd_capture(cmd):
    tmp = "/tmp/iptools_%s.out" % _rand8()
    full = "%s > %s 2>&1" % (cmd, tmp)
    rc = os.system(full)
    out = _read_text(tmp)
    _safe_unlink(tmp)
    return (rc == 0), out or ""
def ping(host, count=4, size=0, ipv6=False):
    h = _normalize_host(host)
    if not (_is_ipv4(h) or _is_domain(h)):
        return False, "Invalid host"
    c = _normalize_int(count, default=4, lo=1, hi=10)
    sz = _normalize_int(size, default=0, lo=0, hi=1500)
    if ipv6:
        ok, out = _run_cmd_capture("ping -6 -c %d -W 1 %s%s" % (
            c, ("-s %d " % sz if sz > 0 else ""), h))
        if not ok and "unrecognized option" in out:
            ok, out = _run_cmd_capture("ping6 -c %d -W 1 %s%s" % (
                c, ("-s %d " % sz if sz > 0 else ""), h))
        return ok, out
    else:
        ok, out = _run_cmd_capture("ping -c %d -W 1 %s%s" % (
            c, ("-s %d " % sz if sz > 0 else ""), h))
        return ok, out
def dns_lookup(qname):
    h = _normalize_host(qname)
    if not (_is_ipv4(h) or _is_domain(h)):
        return False, "Invalid host"
    ok, out = _run_cmd_capture("nslookup %s" % h)
    return ok, out
def traceroute(host, max_hops=30):
    h = _normalize_host(host)
    if not (_is_ipv4(h) or _is_domain(h)):
        return False, "Invalid host"
    m = _normalize_int(max_hops, default=30, lo=1, hi=64)
    ok, out = _run_cmd_capture("traceroute -n -m %d %s" % (m, h))
    if (not ok) and ("not found" in out or "not installed" in out):
        return False, "traceroute: command not found"
    return ok, out
def tcp_check(host, port, timeout=3):
    h = _normalize_host(host)
    if not (_is_ipv4(h) or _is_domain(h)):
        return False, "Invalid host"
    p = _normalize_int(port, default=0, lo=1, hi=65535)
    to = _normalize_int(timeout, default=3, lo=1, hi=30)
    s = None
    try:
        s = socket.socket()
        s.settimeout(to)
        ai = socket.getaddrinfo(h, p)[0][-1]
        t0 = time.ticks_ms()
        s.connect(ai)
        t1 = time.ticks_ms()
        s.close(); s = None
        ms = time.ticks_diff(t1, t0)
        return True, "TCP connect to %s:%d OK in %d ms" % (h, p, ms)
    except Exception as e:
        try:
            if s: s.close()
        except:
            pass
        return False, "TCP connect to %s:%d FAILED: %s" % (h, p, str(e))
