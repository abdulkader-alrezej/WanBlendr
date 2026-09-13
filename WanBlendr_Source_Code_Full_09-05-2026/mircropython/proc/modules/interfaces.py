import os
import ure as re
import ujson as json
import utime as time
_last_reads = {}                                                 
_MAC_RE = r"([0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:" \
          r"[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f]:[0-9A-Fa-f][0-9A-Fa-f])"
def safe_str(x):
    try:
        if isinstance(x, str):
            return x
        return str(x)
    except:
        try:
            return "%s" % (x,)
        except:
            return ""
def _ticks_now():
    try:
        return time.ticks_ms()
    except:
        return int((time.time() if hasattr(time, "time") else 0) * 1000)
def _ticks_diff_ms(new, old):
    try:
        return time.ticks_diff(new, old)
    except:
        return new - old
def _human_size_bytes(n):
    try:
        v = 0 if n is None else float(n)
    except:
        return "0 B"
    units = ["B","KB","MB","GB","TB","PB"]
    i = 0
    while v >= 1024 and i < len(units)-1:
        v /= 1024.0
        i += 1
    if v >= 100:
        return "%0.0f %s" % (v, units[i])
    return "%0.2f %s" % (v, units[i])
def _human_speed_bps(bps):
    try:
        x = 0 if bps is None else float(bps)
    except:
        x = 0.0
    units = ["bps","Kbps","Mbps","Gbps","Tbps","Pbps"]
    i = 0
    while x >= 1000 and i < len(units)-1:
        x /= 1000.0
        i += 1
    return "%0.2f %s" % (x, units[i])
def _capture_cmd(cmd):
    c = safe_str(cmd)
    tmp = "/tmp/_ifc_%s.txt" % safe_str(_ticks_now())
    os.system("%s > %s 2>&1" % (c, tmp))
    try:
        with open(tmp, "r") as f:
            out = f.read()
    except:
        out = ""
    try:
        os.remove(tmp)
    except:
        pass
    return out or ""
def _human_link_speed_en(s):
    txt = safe_str(s).strip()
    if not txt or txt.lower() == "n/a":
        return "N/A"
    low = txt.lower()
    m = re.search(r"(\d+(?:\.\d+)?)", low)
    if not m:
        return txt
    try:
        n = float(m.group(1))
    except:
        return txt
    if "mb/s" in low or "mbps" in low:
        if n >= 1000:
            return ("%g Gbps" % (n / 1000.0)).replace(".0", "")
        return ("%g Mbps" % n).replace(".0", "")
    if "gb/s" in low or "gbps" in low or "gb" in low:
        return ("%g Gbps" % n).replace(".0", "")
    if n >= 1000:
        return ("%g Gbps" % (n / 1000.0)).replace(".0", "")
    return ("%g Mbps" % n).replace(".0", "")
def _ethtool_basic(dev):
    out = _capture_cmd("ethtool %s" % safe_str(dev))
    speed, duplex, status = "N/A", "N/A", "Unknown"
    if out:
        for line in out.splitlines():
            s = line.strip()
            sl = s.lower()
            if sl.startswith("speed:"):
                val = s.split(":", 1)[1].strip()
                speed = val if val and val.lower() != "unknown!" else "N/A"
            elif sl.startswith("duplex:"):
                duplex = s.split(":", 1)[1].strip() or "N/A"
            elif sl.startswith("link detected:"):
                yesno = s.split(":", 1)[1].strip().lower()
                status = "Up+" if yesno == "yes" else "Down-"
    try:
        if (duplex or '').lower().startswith('unknown'):
            duplex = 'N/A'
    except:
        pass
    return speed, duplex, status
def _parse_stats_to_dict(text):
    stats = {}
    if not text:
        return stats
    for line in text.splitlines():
        if ":" not in line:
            continue
        try:
            k, v = line.split(":", 1)
            key = k.strip().lower().replace(" ", "_").replace("-", "_")
            raw = v.strip()
            num_s = raw.replace(",", " ").split()[0]
            try:
                num = int(num_s)
            except:
                try:
                    num = int(float(num_s))
                except:
                    continue
            stats[key] = num
        except:
            pass
    return stats
def _pick_first(stats, keys):
    for k in keys:
        if k in stats:
            return stats[k]
    return 0
def _ethtool_stats(dev):
    out = _capture_cmd("ethtool -S %s" % safe_str(dev))
    if not out:
        return 0, 0
    stats = _parse_stats_to_dict(out)
    rx_pref = ["rxbytes", "rx_bytes"]
    tx_pref = ["txbytes", "tx_bytes"]
    rx_candidates = rx_pref + [
        "rx_octets",
        "in_good_octets", "in_octets",
        "good_octets_received",
        "ifhcin_octets",
        "rbytes",
    ]
    tx_candidates = tx_pref + [
        "tx_octets",
        "out_octets", "out_good_octets",
        "good_octets_sent",
        "ifhcout_octets",
        "obytes",
    ]
    rx_val = _pick_first(stats, rx_candidates)
    tx_val = _pick_first(stats, tx_candidates)
    return rx_val, tx_val
def _ethtool_mac(dev):
    out = _capture_cmd("ethtool -P %s" % safe_str(dev))
    if out:
        for line in out.splitlines():
            s = line.strip()
            if s.lower().startswith("permanent address:"):
                mac = s.split(":", 1)[1].strip()
                if mac:
                    return mac.upper()
    return "N/A"
_P_PAT   = r"^p\d+(\.\d+)?$"                        
_SFP_PAT = r"^sfp\d*(\.\d+)?$|^sfp(\.\d+)?$"                          
def _discover_ifaces():
    out = _capture_cmd("ip -o link show")
    devs = []
    if not out:
        return devs
    lines = out.splitlines()
    for idx, line in enumerate(lines):
        s = line.strip()
        m = re.search(r"^\d+:\s+([^\s@:]+)", s)
        if not m:
            continue
        dev = m.group(1)
        mac = None
        m2 = re.search(r"link/ether\s+" + _MAC_RE, s)
        if m2:
            mac = m2.group(1).upper()
        low = dev.lower()
        if re.match(_P_PAT, low) or re.match(_SFP_PAT, low):
            devs.append((dev, mac or "N/A"))
    if out and devs:
        for i in range(len(lines)-1):
            s1 = lines[i].strip()
            m1 = re.search(r"^\d+:\s+([^\s@:]+)", s1)
            if not m1:
                continue
            dev = m1.group(1)
            if not (re.match(_P_PAT, dev.lower()) or re.match(_SFP_PAT, dev.lower())):
                continue
            s2 = lines[i+1].strip()
            if "link/ether" in s2:
                m2 = re.search(r"link/ether\s+" + _MAC_RE, s2)
                if m2:
                    mac = m2.group(1).upper()
                    for j, (d, oldmac) in enumerate(devs):
                        if d == dev and (oldmac == "N/A" or not oldmac):
                            devs[j] = (d, mac)
    return devs
def _calc_speeds(dev, rx_bytes, tx_bytes, t_ms):
    try:
        rx_b = int(rx_bytes or 0)
    except:
        rx_b = 0
    try:
        tx_b = int(tx_bytes or 0)
    except:
        tx_b = 0
    prev = _last_reads.get(dev)
    if not prev:
        _last_reads[dev] = {"rx": rx_b, "tx": tx_b, "t_ms": t_ms}
        return 0, 0
    dt = max(1, _ticks_diff_ms(t_ms, prev.get("t_ms", t_ms)))      
    drx = max(0, rx_b - prev.get("rx", rx_b))
    dtx = max(0, tx_b - prev.get("tx", tx_b))
    _last_reads[dev] = {"rx": rx_b, "tx": tx_b, "t_ms": t_ms}
    rx_bps = (drx * 8 * 1000) // dt
    tx_bps = (dtx * 8 * 1000) // dt
    return rx_bps, tx_bps
def _normalize_rows(rows):
    try:
        rows = list(rows or [])
    except:
        return []
    rows.sort(key=lambda r: safe_str(r.get("device","")))
    return rows
def _display_name(dev):
    d = safe_str(dev)
    low = d.lower()
    vlan_suffix = ""
    m = re.search(r"(\.\d+)$", d)
    if m:
        vlan_suffix = m.group(1)
    m = re.match(r"^p(\d+)", low)
    if m:
        return "eth%s%s" % (m.group(1), vlan_suffix)
    if re.match(r"^sfp\d*$", low) or re.match(r"^sfp$", low):
        return "SFP+%s" % vlan_suffix
    return dev
def compute_interfaces_data():
    devs = _discover_ifaces()                              
    t_ms = _ticks_now()
    rows = []
    for d, mac_guess in devs:
        rx_bytes, tx_bytes = _ethtool_stats(d)
        sp_rx, sp_tx = _calc_speeds(d, rx_bytes, tx_bytes, t_ms)
        link_speed, duplex, status = _ethtool_basic(d)
                                                              
        base = safe_str(d).split('.', 1)[0]
        up_count = 0
        try:
            with open('/sys/class/net/%s/carrier_up_count' % base, 'r') as f:
                txt = f.read().strip()
                up_count = int(txt) if txt.isdigit() else 0
        except:
            up_count = 0
        mac = mac_guess if (mac_guess and mac_guess != "N/A") else _ethtool_mac(d)
        row = {
            "device"    : safe_str(d),
            "name"      : safe_str(_display_name(d)),
            "mac"       : safe_str(mac),
            "link_speed": _human_link_speed_en(link_speed),
            "duplex"    : safe_str(duplex),
            "up_count"  : up_count,
            "tx"        : _human_speed_bps(sp_tx),
            "rx"        : _human_speed_bps(sp_rx),
            "tx_bytes"  : _human_size_bytes(tx_bytes),
            "rx_bytes"  : _human_size_bytes(rx_bytes),
            "status"    : safe_str(status),
        }
        rows.append(row)
    return _normalize_rows(rows)

def _read_text(path):
    try:
        with open(path, 'r') as f:
            return f.read()
    except:
        return None

def wb_health_data():
    rows = []
    raw  = []
    try:
        txt = _read_text('/var/run/wanblendr.health') or ''
        for ln in txt.splitlines():
            line = (ln or '').strip()
            if not line:
                continue
            raw.append(line)
            parts = line.split()
            # expected: wanX 44 0 50 50 0xC9 8.8.4.4 pN
            name = parts[0] if len(parts) > 0 else ''
            probe_err = parts[2] if len(parts) > 2 else ''
            code = parts[5] if len(parts) > 5 else ''
            status = 'Online' if str(probe_err) == '0' else 'Offline'
            rows.append({'wan': name, 'status': status, 'code': code})
    except:
        pass
    return {'rows': rows, 'raw': raw}

def wb_status_web_lines():
    try:
        txt = _read_text('/var/run/wanblendr.status-web') or ''
        return [l.strip() for l in (txt.splitlines() if txt else []) if l.strip()]
    except:
        return []

def wb_status_event_lines():
    try:
        txt = _read_text('/var/run/wanblendr.status') or ''
        lines = [l.strip() for l in (txt.splitlines() if txt else []) if l.strip()]
        # Limit to last 50 lines to prevent UI freeze/lag
        if len(lines) > 50:
            return lines[-50:]
        return lines
    except:
        return []

def wb_status_web_map():
    m = {}
    try:
        for ln in wb_status_web_lines():
            parts = (ln or '').strip().split()
            if len(parts) >= 2:
                wan = parts[0].strip()
                st  = parts[1].strip().lower()
                m[wan] = st
    except:
        pass
    return m

def wb_logs_filtered():
    try:
        out = _capture_cmd('logread -e wanblendr-healthd; logread -e wanblendr-route-apply; logread -e wanblendr-apply-nft') or ''
        lines = []
        for ln in out.splitlines():
            s = (ln or '').rstrip()
            # strip 'user.notice wanblendr-xxx: ' segments only, keep timestamps
            s = re.sub(r'\suser\.notice\s+wanblendr-[\w\-]+:\s*', ' ', s)
            lines.append(s)
        return lines
    except:
        return []
