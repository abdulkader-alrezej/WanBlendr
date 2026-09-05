                                                 
import utime as time
                                                                             
_BLOCK  = {'tot': 0, 'idle': 0, 'first': True}
def _read_cpu():
    try:
        with open('/proc/stat') as f:
            parts = f.readline().split()[1:]
            return list(map(int, parts[:10]))
    except Exception:
        return [0] * 10
def cpu_usage_pct():
    p = _read_cpu()
    user, nice, system, idle, iowait, irq, softirq, steal, guest, guest_nice = p
    total = sum(p[:8]) + guest + guest_nice
    idle_t = idle + iowait
    if _BLOCK['first']:
        _BLOCK.update({'tot': total, 'idle': idle_t, 'first': False})
        return 0.0
    diff_tot  = total - _BLOCK['tot']
    diff_idle = idle_t - _BLOCK['idle']
    _BLOCK['tot'], _BLOCK['idle'] = total, idle_t
    if diff_tot <= 0:
        return 0.0
    usage = (1.0 - (diff_idle / diff_tot)) * 100.0
    val = max(0.0, round(usage - 15.0, 2))
                    
    if val < 0:
        val = 0.0
    if val > 100:
        val = 100.0
    return val
def uptime_str():
    try:
        with open('/proc/uptime') as f:
            secs = float(f.read().split()[0])
        d = int(secs // 86400)
        h = int((secs % 86400) // 3600)
        m = int((secs % 3600) // 60)
        s = int(secs % 60)
        return "%dd %dh %dm %ds" % (d, h, m, s)
    except Exception:
        return "N/A"
def mem_info():
    try:
        info = {}
        with open('/proc/meminfo') as f:
            for ln in f:
                parts = ln.split()
                if not parts:
                    continue
                k = parts[0]
                v = parts[1] if len(parts) > 1 else '0'
                if k.endswith(':'):
                    k = k[:-1]
                try:
                    info[k] = int(v)
                except Exception:
                    info[k] = 0
        total = info.get('MemTotal', 0) // 1024
        avail = info.get('MemAvailable', info.get('MemFree', 0)) // 1024
        used  = total - avail
        pct   = round((used / total) * 100, 1) if total else 0
        return total, used, pct
    except Exception:
        return 0, 0, 0
_LAST = {'ts': 0, 'data': None}
def snapshot():
                                                                  
    now = time.time()
    cached = _LAST['data']
    if cached and (now - _LAST['ts'] < 1):
        t = time.localtime()
        cached['date'] = "%04d-%02d-%02d" % (t[0], t[1], t[2])
        cached['time'] = "%02d:%02d:%02d" % (t[3], t[4], t[5])
        return cached
    t = time.localtime()
    total, used, pct = mem_info()
                                                 
    fw_cnt = 0
    try:
        with open('/proc/sys/net/netfilter/nf_conntrack_count') as f:
            s = (f.read() or '').strip()
            fw_cnt = int(s) if s and s.isdigit() else 0
    except Exception:
        fw_cnt = 0
    data = {
        'uptime'        : uptime_str(),
        'date'          : "%04d-%02d-%02d" % (t[0], t[1], t[2]),
        'time'          : "%02d:%02d:%02d" % (t[3], t[4], t[5]),
        'memory_total'  : total,
        'memory_used'   : used,
        'memory_percent': pct,
        'cpu_usage'     : cpu_usage_pct(),
        'fw_conntrack'  : fw_cnt,
    }
    _LAST['ts'] = now
    _LAST['data'] = data
    return data

