import os
import ure as re
import ujson as json
import ubinascii
import utime as time
METRIC_START = 101
def _device_type_for_name(dev_name):
    lines = _network_show_lines()
    r_name = re.compile(r"^network\.@device\[(\d+)\]\.name='?([^']+)'?")
    r_type = re.compile(r"^network\.@device\[(\d+)\]\.type='?([^']+)'?")
    devs = {}
    for ln in lines:
        ln = ln.strip()
        m = r_name.match(ln)
        if m:
            i, nm = m.group(1), m.group(2)
            devs.setdefault(i, {})["name"] = nm
            continue
        m = r_type.match(ln)
        if m:
            i, tp = m.group(1), (m.group(2) or "")
            devs.setdefault(i, {})["type"] = tp
            continue
    for i, d in devs.items():
        if d.get("name") == dev_name:
            return (d.get("type") or "").lower()
    return ""
def _is_vlan_ifname(ifname):
    return bool(re.match(r"^(?:p\d+|sfp)\.\d+$", safe_str(ifname) or ""))
def _list_names(path):
    names = []
    try:
        raw = os.listdir(path)
    except:
        raw = []
    for ent in raw:
        name = ent
        if isinstance(ent, (tuple, list)):
            name = ent[0] if ent else ""
        if not isinstance(name, str):
            try:
                name = name.decode()
            except:
                name = "%s" % (name,)
        names.append(name)
    return names
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
def _read_text(path):
    try:
        with open(path, 'r') as f:
            return f.read()
    except:
        return None
def _stat_mtime(path):
    try:
        st = os.stat(path)
        # mtime typically at index 8 in MicroPython's stat tuple
        if len(st) > 8:
            return int(st[8])
        if len(st) > 7:
            return int(st[7])
        return 0
    except:
        return 0
def _run_bg(cmd):
    try:
        os.system("%s &" % cmd)
    except:
        pass
def _capture_cmd(cmd):
                            
    try:
        rnd = ubinascii.hexlify(os.urandom(4)).decode()
    except:
        rnd = "tmp%08d" % (os.urandom(1)[0] if hasattr(os, "urandom") else 0)
    tmp = "/tmp/_wan_%s.txt" % rnd
    os.system("%s > %s 2>&1" % (cmd, tmp))
    out = _read_text(tmp) or ""
    try:
        os.remove(tmp)
    except:
        pass
    return out
def display_interface_name(name):
    s = safe_str(name)
    m = re.match(r"^p(\d+)(?:\.(\d+))?$", s)
    if m:
        idx = m.group(1)
        vid = m.group(2)
        if vid:
            return "eth%s.%s" % (idx, vid)
        return "eth%s" % idx
    return s
def _fmt_type_title(proto):
    p = (proto or "").lower()
    if p == "dhcp":   return "DHCP"
    if p == "static": return "Static"
    if p == "pppoe":  return "PPPoE"
    return (proto or "").upper()
def _fmt_uptime(sec):
    try:
        s = int(sec or 0)
    except:
        s = 0
    h = s // 3600
    m = (s % 3600) // 60
    se = s % 60
    return "%02d:%02d:%02d" % (h, m, se)
def _uci_show(pkg):
    return _capture_cmd("uci -q show %s" % pkg)
def _uci_get(key, default=""):
    v = _capture_cmd("uci -q get %s" % key).strip()
    return v if v else default
def _uci_set(k, v):
    os.system("uci set %s='%s'" % (k, safe_str(v)))
def _uci_add_list(k, v):
    os.system("uci add_list %s='%s'" % (k, safe_str(v)))
def _uci_del_list(k, v):
    os.system("uci del_list %s='%s'" % (k, safe_str(v)))
def _uci_add(pkg, section_type):
    os.system("uci add %s %s" % (pkg, section_type))
def _uci_delete(key):
    os.system("uci delete %s" % key)
def _uci_commit(pkg):
    os.system("uci commit %s" % pkg)
def _uci_get_list(section, option):
    vals = []
    try:
        prefix = "wanblendr.%s.%s=" % (safe_str(section), safe_str(option))
        for ln in (_uci_show("wanblendr") or "").splitlines():
            s = (ln or "").strip()
            if not s.startswith(prefix):
                continue
            rhs = s[len(prefix):].strip()
            cleaned = rhs.replace("'", " ").replace('"', " ")
            parts = [p.strip() for p in cleaned.split() if p.strip()]
            for p in parts:
                vals.append(p)
    except:
        pass
    return vals
def _uci_set_list(section, option, items):
    try:
        _uci_delete("wanblendr.%s.%s" % (safe_str(section), safe_str(option)))
    except:
        pass
    try:
        for it in (items or []):
            _uci_add_list("wanblendr.%s.%s" % (safe_str(section), safe_str(option)), safe_str(it))
    except:
        pass
def _uci_reorder(pkg, section, index):
    try:
        os.system("uci reorder %s.%s=%s" % (pkg, safe_str(section), str(int(index))))
    except:
        pass
def _network_show_lines():
    return _uci_show("network").splitlines()
def _firewall_show_lines():
    return _uci_show("firewall").splitlines()
def _mwan3_show_lines():
    return _uci_show("mwan3").splitlines()
def wanblendr_get_lan_if_list():
    raw = _uci_get('wanblendr.globals.lan_if', '').strip()
    if not raw:
        return []
    return [x for x in raw.split() if x]
def wanblendr_set_lan_if_list(if_list):
    try:
        items = []
        for it in (if_list or []):
            s = safe_str(it).strip()
            if s:
                items.append(s)
        joined = ' '.join(items)
        _uci_set('wanblendr.globals.lan_if', joined)
        _uci_commit('wanblendr')
        return True
    except:
        return False
def list_available_px_for_lan_lb():
    out = []
    for d in get_physical_interfaces():
        if re.match(r'^p\d+$', safe_str(d)):
            out.append(d)
    try:
        out.sort(key=lambda x: int(x[1:]))
    except:
        out.sort()
    return out
def _extract_value(line):
    i = line.find("=")
    if i < 0:
        return ""
    val = line[i+1:].strip()
    if val.startswith("'") and val.endswith("'"):
        val = val[1:-1]
    return val
def get_physical_interfaces():
    devs = _list_names("/sys/class/net")
    out = []
    for d in devs:
        if d == "lo":    continue
        if d == "eth0":  continue
        if d.startswith("br"): continue
        if "@" in d:     continue
        if re.match(r"^p\d+$", d) or d == "sfp":
            out.append(d)
    try:
        out.sort(key=lambda x: (x != "sfp", int(x[1:]) if x.startswith("p") else 0))
    except:
        out.sort()
    return out
def get_vlan_interfaces():
    names = set()
    lines = _network_show_lines()
    r_dev_type   = re.compile(r"^network\.@device\[(\d+)\]\.type='?([^']+)'?")
    r_dev_name   = re.compile(r"^network\.@device\[(\d+)\]\.name='?([^']+)'?")
    r_dev_ifname = re.compile(r"^network\.@device\[(\d+)\]\.ifname='?([^']+)'?")
    r_dev_vid    = re.compile(r"^network\.@device\[(\d+)\]\.vid='?(\d+)'?")
    devs = {}
    for ln in lines:
        ln = ln.strip()
        m = r_dev_type.match(ln)
        if m:
            i, tp = m.group(1), (m.group(2) or "").lower()
            devs.setdefault(i, {})["type"] = tp
            continue
        m = r_dev_name.match(ln)
        if m:
            i, nm = m.group(1), m.group(2)
            devs.setdefault(i, {})["name"] = nm
            continue
        m = r_dev_ifname.match(ln)
        if m:
            i, ifn = m.group(1), m.group(2)
            devs.setdefault(i, {})["ifname"] = ifn
            continue
        m = r_dev_vid.match(ln)
        if m:
            i, vid = m.group(1), m.group(2)
            devs.setdefault(i, {})["vid"] = vid
            continue
    for _, d in devs.items():
        tp = (d.get("type") or "").lower()
        if tp in ("8021q", "vlan"):
            nm = d.get("name", "")
            if nm:
                if re.match(r"^(?:p\d+|sfp)\.\d+$", nm):
                    names.add(nm)
            else:
                ifn = d.get("ifname", "")
                vid = d.get("vid", "")
                if ifn and vid and re.match(r"^(?:p\d+|sfp)$", ifn) and vid.isdigit():
                    names.add("%s.%s" % (ifn, vid))
    r_ifc_dev   = re.compile(r"^network\.([A-Za-z0-9_]+)\.device='?([^']+)'?")
    r_ifc_ifn   = re.compile(r"^network\.([A-Za-z0-9_]+)\.ifname='?([^']+)'?")
    vlan_pat    = re.compile(r"^(?:p\d+|sfp)\.\d+$")
    for ln in lines:
        ln = ln.strip()
        m = r_ifc_dev.match(ln)
        if m:
            val = m.group(2)
            if vlan_pat.match(val):
                names.add(val)
            continue
        m = r_ifc_ifn.match(ln)
        if m:
            val = m.group(2)
            parts = [x.strip() for x in val.split() if x.strip()]
            for x in parts:
                if vlan_pat.match(x):
                    names.add(x)
    try:
        for d in _list_names("/sys/class/net"):
            if vlan_pat.match(d):
                names.add(d)
    except:
        pass
    lst = list(names)
    try:
        def _key(s):
            if s.startswith("sfp."):
                port_rank = -1
                vid = int(s.split(".")[1])
                return (port_rank, 0, vid)
            if s.startswith("p") and "." in s:
                p, v = s.split(".", 1)
                port = int(p[1:]) if p[1:].isdigit() else 9999
                vid  = int(v) if v.isdigit() else 9999
                return (0, port, vid)
            return (1, 9999, 9999)
        lst.sort(key=_key)
    except:
        lst.sort()
    return lst
def list_lan_network_cidrs():
    nets = []
    try:
        r = re.compile(r"^network\.lan[\w]*\.ipaddr='?([^']+)'?")
        for ln in _network_show_lines():
            m = r.match((ln or '').strip())
            if not m:
                continue
            ip = (m.group(1) or '').strip()
            parts = ip.split('.')
            if len(parts) == 4:
                try:
                    p = [int(x) for x in parts]
                    if all(0 <= x <= 255 for x in p):
                        cidr = "%d.%d.%d.0/24" % (p[0], p[1], p[2])
                        if cidr not in nets:
                            nets.append(cidr)
                except:
                    pass
    except:
        pass
    return nets
def list_wan_interface_names():
    names = []
    try:
        r = re.compile(r"^network\.([A-Za-z0-9_]+)=interface")
        for ln in _network_show_lines():
            ln = (ln or '').strip()
            m = r.match(ln)
            if not m:
                continue
            nm = (m.group(1) or '').strip()
            if re.match(r"^wan(\d+)?$", nm):
                names.append(nm)
        def _key(n):
            m = re.match(r"^wan(\d+)?$", n)
            if m and m.group(1):
                try:
                    return int(m.group(1)) + 1
                except:
                    return 9999
            return 1 if n == 'wan' else 9999
        names = sorted(set(names), key=_key)
    except:
        pass
    return names
def list_source_policies():
    # Return rows representing src rules (excluding default_all) joined with their policy members as wans string
    items = []
    try:
        # collect rule names and their attributes
        rules = []
        r_rule = re.compile(r"^wanblendr\.([A-Za-z0-9_]+)=rule$")
        for ln in (_uci_show('wanblendr') or '').splitlines():
            s = (ln or '').strip()
            m = r_rule.match(s)
            if not m:
                continue
            rn = (m.group(1) or '').strip()
            if rn == 'default_all':
                continue
            src = _uci_get("wanblendr.%s.src" % rn, '')
            pol = _uci_get("wanblendr.%s.use_policy" % rn, '')
            rules.append({'rule': rn, 'src': safe_str(src), 'policy': safe_str(pol)})
        # stable order by rule name
        rules.sort(key=lambda x: x['rule'])
        for idx, it in enumerate(rules):
            pol = it['policy']
            # read members of policy and convert m_wanX -> wanX
            members = _uci_get_list(pol, 'members')
            wans = []
            for mname in members:
                mm = safe_str(mname)
                if mm.startswith('m_'):
                    wans.append(mm[2:])
            wans_s = ' '.join(wans)
            items.append({'id': idx, 'src': it['src'], 'dest': wans_s})
    except:
        pass
    return items
def _policy_name_for_wans(wans):
    lst = []
    for w in (wans or []):
        s = safe_str(w).strip()
        if s:
            lst.append(s)
    if not lst:
        return ''
    lst = sorted(set(lst))
    return 'only_%s' % ('_'.join(lst))
def _rule_name_for_src(src_cidr):
    s = safe_str(src_cidr).strip()
    if not s:
        return ''
    # Derive stable unique name from full CIDR, e.g. 192.168.43.0/24 -> src_192_168_43_0_24
    try:
        s2 = s.replace('/', '_').replace('.', '_')
        # keep digits and underscores only
        s2 = re.sub(r'[^0-9_]+', '_', s2)
        s2 = re.sub(r'_+', '_', s2).strip('_')
        if not s2:
            raise ValueError
        return 'src_%s' % s2
    except:
        # fallback: fully sanitized lowercase
        s3 = re.sub(r'[^a-z0-9]+', '_', s.lower())
        s3 = re.sub(r'_+', '_', s3).strip('_')
        return 'src_%s' % s3
def add_source_policy(src_cidr, dest_wans='wan2'):
    try:
        s = safe_str(src_cidr).strip()
        if not s:
            return False, 'Missing src'
        # normalize wan list
        if isinstance(dest_wans, (list, tuple)):
            wlist = [safe_str(x).strip() for x in dest_wans if safe_str(x).strip()]
        else:
            val = safe_str(dest_wans).strip()
            wlist = [p for p in val.split() if p] if val else []
        if not wlist:
            return False, 'Missing WAN selection'
        # build policy name and members
        pol_name = _policy_name_for_wans(wlist)
        member_names = ['m_%s' % w for w in sorted(set(wlist))]
        # create/update policy
        _uci_set("wanblendr.%s" % pol_name, "policy")
        _uci_set_list(pol_name, "members", member_names)
        # create/update rule bound to this policy by src
        rule_name = _rule_name_for_src(s)
        _uci_set("wanblendr.%s" % rule_name, "rule")
        _uci_set("wanblendr.%s.src" % rule_name, s)
        _uci_set("wanblendr.%s.dest" % rule_name, "0.0.0.0/0")
        _uci_set("wanblendr.%s.use_policy" % rule_name, pol_name)
        # order: ensure goes after balanced and before default_all
        _ensure_default_rule_and_policy()
        _normalize_wanblendr_order()
        _uci_commit('wanblendr')
        return True, 'ok'
    except Exception as e:
        return False, safe_str(e)
def _list_source_rules():
    rules = []
    r_rule = re.compile(r"^wanblendr\.([A-Za-z0-9_]+)=rule$")
    for ln in (_uci_show('wanblendr') or '').splitlines():
        s = (ln or '').strip()
        m = r_rule.match(s)
        if not m:
            continue
        rn = (m.group(1) or '').strip()
        if rn == 'default_all':
            continue
        pol = _uci_get("wanblendr.%s.use_policy" % rn, '')
        src = _uci_get("wanblendr.%s.src" % rn, '')
        rules.append({'rule': rn, 'policy': safe_str(pol), 'src': safe_str(src)})
    rules.sort(key=lambda x: x['rule'])
    return rules
def delete_source_policy(index):
    try:
        i = int(index)
    except:
        return False, 'Bad index'
    try:
        rules = _list_source_rules()
        if i < 0 or i >= len(rules):
            return False, 'Not found'
        rn = rules[i]['rule']
        pol = rules[i]['policy']
        # delete rule
        _uci_delete("wanblendr.%s" % rn)
        # if no other rule uses this policy, delete policy too
        still_used = False
        for j, it in enumerate(rules):
            if j == i:
                continue
            if it['policy'] == pol:
                still_used = True
                break
        if not still_used and pol:
            _uci_delete("wanblendr.%s" % pol)
        _uci_commit('wanblendr')
        _normalize_wanblendr_order()
        return True, 'ok'
    except Exception as e:
        return False, safe_str(e)
def get_weight_config():
    weights = []
    try:
        for nm in list_wan_interface_names():
            w = _uci_get('wanblendr.%s.weight' % nm, '50').strip() or '50'
            dns = _uci_get('wanblendr.%s.probe_ip' % nm, '').strip()
            weights.append({'name': nm, 'weight': w, 'probe_ip': dns})
    except:
        pass
    return {'weights': weights}
def save_weights(weights):
    try:
        if isinstance(weights, dict):
            items = [{'name': k, 'weight': v} for k, v in weights.items()]
        else:
            items = list(weights or [])
        for it in items:
            nm = safe_str(it.get('name') if isinstance(it, dict) else '').strip()
            wt = safe_str(it.get('weight') if isinstance(it, dict) else '').strip()
            if not nm:
                continue
            if not wt or not wt.isdigit():
                wt = '50'
            _uci_set('wanblendr.%s.weight' % nm, wt)
        _uci_commit('wanblendr')
        return True, 'ok'
    except Exception as e:
        return False, safe_str(e)

def get_speed_config():
    # Retrieve weight and track_ip for all WANs
    items = []
    try:
        for nm in list_wan_interface_names():
            # weight from member section m_wanX
            w = _uci_get('wanblendr.m_%s.weight' % nm, '50').strip()
            if not w: w = '50'
            # track_ip from wan section wanX (list)
            # We assume single IP for the UI input, so take first one if multiple
            t_ips = _uci_get_list(nm, 'track_ip')
            t_ip = t_ips[0] if t_ips else ''
            items.append({'name': nm, 'weight': w, 'track_ip': t_ip})
    except:
        pass
    return items

def save_speed_settings(items):
    # items: list of {name, weight, track_ip}
    try:
        for it in (items or []):
            nm = safe_str(it.get('name') or '').strip()
            if not nm: continue
            
            # Validate Weight: 1 - 999
            w_str = safe_str(it.get('weight') or '').strip()
            try:
                w_val = int(w_str)
            except:
                w_val = 50
            if w_val < 1: w_val = 1
            if w_val > 999: w_val = 999
            
            # Validate Track IP: must be valid IPv4
            t_ip = safe_str(it.get('track_ip') or '').strip()
            # If empty or invalid, maybe fallback to something safe or just don't set?
            # User said: "must enforce ipv4 standards... to avoid error data"
            # If invalid, we should probably fail or skip.
            # But since we are processing a list, maybe we skip or use a default?
            # Let's assume 8.8.8.8 if invalid, or keep previous?
            # Better: if invalid, don't update track_ip (or set empty if allowed).
            # The user said "prevent sending error data".
            valid_ip = False
            if t_ip and _is_valid_ipv4(t_ip):
                valid_ip = True
            
            # Save Weight (to m_wanX)
            _uci_set('wanblendr.m_%s.weight' % nm, str(w_val))
            
            # Save Track IP (to wanX)
            # User example: list track_ip '8.8.4.4'
            if valid_ip:
                _uci_set_list(nm, 'track_ip', [t_ip])
            elif not t_ip:
                 # If user cleared it, maybe remove?
                 # For now, let's just not set it if invalid/empty
                 pass

        _uci_commit('wanblendr')
        return True, 'ok'
    except Exception as e:
        return False, safe_str(e)
_WB_STATUS_FILE = '/tmp/wanblendr_status'
_WB_STATUS_CACHE = ''
_WB_STATUS_TS = 0
_WB_STATUS_REQ_TICK = 0

def _write_text(path, txt):
    try:
        with open(path, 'w') as f:
            f.write(txt if isinstance(txt, str) else str(txt))
        return True
    except:
        return False

def _trigger_wb_status_refresh():
    try:
        os.system('/etc/init.d/wanblendr status > %s 2>&1 &' % _WB_STATUS_FILE)
    except:
        pass
def get_wanblendr_status():
    global _WB_STATUS_CACHE, _WB_STATUS_TS, _WB_STATUS_REQ_TICK
    # Refresh cache from file if newer
    try:
        mt = _stat_mtime(_WB_STATUS_FILE)
        if mt and mt != _WB_STATUS_TS:
            txt = _read_text(_WB_STATUS_FILE) or ''
            txt = (txt or '').strip()
            if txt:
                _WB_STATUS_CACHE = txt
                _WB_STATUS_TS = mt
    except:
        pass
    # Throttle/async refresh every ~5s without blocking requests
    try:
        now_ms = time.ticks_ms()
    except:
        now_ms = 0
    try:
        if (_WB_STATUS_REQ_TICK == 0) or (now_ms and (time.ticks_diff(now_ms, _WB_STATUS_REQ_TICK) > 5000)):
            _WB_STATUS_REQ_TICK = now_ms
            _trigger_wb_status_refresh()
    except:
        pass
    return _WB_STATUS_CACHE or ''
def wb_weights_lines():
    try:
        txt = _read_text('/var/run/wanblendr.weights') or ''
        lines = [l.strip() for l in txt.splitlines() if l.strip()]
        return lines
    except:
        return []
def _list_interface_sections():
    names = []
    r = re.compile(r"^network\.([A-Za-z0-9_]+)=interface")
    for ln in _network_show_lines():
        m = r.match(ln.strip())
        if m:
            names.append(m.group(1))
    return names
def _get_interface_field(name, field):
    return _uci_get("network.%s.%s" % (name, field), "")
def _set_interface_field(name, field, value):
    _uci_set("network.%s.%s" % (name, field), value)
def _delete_interface(name):
    _uci_delete("network.%s" % name)
def _find_firewall_wan_zone_index():
    lines = _firewall_show_lines()
    r = re.compile(r"^firewall\.@zone\[(\d+)\]\.name='?wan'?")
    for ln in lines:
        m = r.match(ln.strip())
        if m:
            return m.group(1)
    return None
def _add_interface_to_wan_zone(name):
    idx = _find_firewall_wan_zone_index()
    if idx is None:
        return
    lines = _firewall_show_lines()
    prefix = "firewall.@zone[%s].network=" % idx
    for ln in lines:
        ln = ln.strip()
        if ln.startswith(prefix):
            if _extract_value(ln) == name:
                return                
    _uci_add_list("firewall.@zone[%s].network" % idx, name)
def is_interface_in_mwan3(name):
    needle = ".interface='%s'" % name
    for ln in _mwan3_show_lines():
        if needle in ln:
            return True
    return False
def _collect_used_metrics():
    used = set()
    for ifn in _list_interface_sections():
        m = _get_interface_field(ifn, "metric").strip()
        if m and m.isdigit():
            used.add(int(m))
    return used
def _choose_free_metric():
    used = _collect_used_metrics()
    existing_names = set(_list_interface_sections())
    n = int(METRIC_START or 101)
    while True:
        if n in used:
            n += 1
            continue
        if _name_for_metric(n) in existing_names:
            n += 1
            continue
        return n
def _name_for_metric(metric):
    try:
        m = int(metric)
    except:
        m = 0
    if m >= 101:
        return "wan%s" % (m - 100)
    if m <= 1:
        return "wan"
    return "wan%s" % (m - 1)
def _wan_suffix_number(wan_name):
    s = safe_str(wan_name).strip().lower()
    m = re.match(r"^wan(\d+)?$", s)
    if not m:
        return 0
    num = m.group(1)
    try:
        return int(num) if num else 0
    except:
        return 0
def _ensure_wanblendr_globals():
    # Ensure globals according to the new schema
    try:
        _uci_set("wanblendr.globals", "globals")
        _uci_set("wanblendr.globals.interval", "60")
        _uci_set("wanblendr.globals.retries_down", "2")
        _uci_set("wanblendr.globals.retries_up", "1")
        _uci_set("wanblendr.globals.default_policy", "balanced")
        _uci_set("wanblendr.globals.flush_conntrack", "1")
    except:
        pass
def _list_wanblendr_wan_names():
    names = []
    try:
        r = re.compile(r"^wanblendr\.([A-Za-z0-9_]+)=wan$")
        for ln in (_uci_show("wanblendr") or "").splitlines():
            s = (ln or "").strip()
            m = r.match(s)
            if m:
                nm = (m.group(1) or "").strip()
                if re.match(r"^wan(\d+)?$", nm):
                    names.append(nm)
        # natural sort wan, wan1, wan2, ...
        def _key(n):
            m = re.match(r"^wan(\d+)?$", n)
            if m and m.group(1):
                try:
                    return int(m.group(1)) + 1
                except:
                    return 9999
            return 1 if n == "wan" else 9999
        names = sorted(set(names), key=_key)
    except:
        pass
    return names
def _ensure_default_rule_and_policy():
    # Ensure policy 'balanced' and rule 'default_all'
    try:
        _uci_set("wanblendr.balanced", "policy")
        _uci_set("wanblendr.balanced.comment", "Default: equal split across all WANs")
        # members populated separately
        _uci_set("wanblendr.default_all", "rule")
        _uci_set("wanblendr.default_all.src", "0.0.0.0/0")
        _uci_set("wanblendr.default_all.dest", "0.0.0.0/0")
        _uci_set("wanblendr.default_all.use_policy", "balanced")
    except:
        pass
def _rebuild_balanced_members():
    # Rebuild 'balanced.members' list from current wan sections
    try:
        wan_names = _list_wanblendr_wan_names()
        _uci_delete("wanblendr.balanced.members")
        for nm in wan_names:
            mname = "m_%s" % nm
            _uci_add_list("wanblendr.balanced.members", mname)
    except:
        pass
def _cleanup_source_policies_for_wan(wan_name):
    try:
        target_member = "m_%s" % safe_str(wan_name)
        sections = _parse_wanblendr_sections()
        # collect policies (non-balanced)
        policy_names = [s['name'] for s in sections if s['type'] == 'policy' and s['name'] != 'balanced']
        # rules map policy->list of rule names
        rules = _list_source_rules()
        policy_to_rules = {}
        for r in rules:
            arr = policy_to_rules.get(r['policy'], [])
            arr.append(r['rule'])
            policy_to_rules[r['policy']] = arr
        for pn in policy_names:
            members = _uci_get_list(pn, 'members')
            if target_member not in members:
                continue
            new_members = [m for m in members if m != target_member]
            if not new_members:
                # delete policy and its rules
                _uci_delete("wanblendr.%s" % pn)
                for rn in policy_to_rules.get(pn, []):
                    _uci_delete("wanblendr.%s" % rn)
                continue
            # derive new WAN list and a new policy name
            wans = []
            for m in new_members:
                mm = safe_str(m)
                if mm.startswith('m_'):
                    wans.append(mm[2:])
            new_pn = _policy_name_for_wans(wans)
            if not new_pn:
                # safety: if failed, just update members on same policy
                _uci_set_list(pn, 'members', new_members)
                continue
            if new_pn == pn:
                _uci_set_list(pn, 'members', new_members)
                continue
            # move: create/update new policy with new members, re-point rules, delete old policy
            _uci_set("wanblendr.%s" % new_pn, "policy")
            _uci_set_list(new_pn, 'members', new_members)
            for rn in policy_to_rules.get(pn, []):
                _uci_set("wanblendr.%s.use_policy" % rn, new_pn)
            _uci_delete("wanblendr.%s" % pn)
        _uci_commit('wanblendr')
    except:
        pass
def _parse_wanblendr_sections():
    # Return ordered list of section names and types as they appear
    sections = []
    try:
        r = re.compile(r"^wanblendr\.([^=]+)=([A-Za-z0-9_]+)$")
        for ln in (_uci_show("wanblendr") or "").splitlines():
            s = (ln or "").strip()
            m = r.match(s)
            if not m:
                continue
            name = (m.group(1) or "").strip()
            stype = (m.group(2) or "").strip()
            # Only record section headers, not options
            if "." in name:
                # option assignment line
                continue
            sections.append({'name': name, 'type': stype})
    except:
        pass
    return sections
def _normalize_wanblendr_order():
    # Desired order: globals, wan* (sorted), m_wan* (sorted), balanced(policy), default_all(rule), others
    try:
        sections = _parse_wanblendr_sections()
        by_name = {s['name']: s for s in sections}
        names_in_order = [s['name'] for s in sections]
        def _wan_num(n):
            m = re.match(r"^wan(\d+)?$", n)
            if not m:
                return 0
            try:
                return int(m.group(1) or "0")
            except:
                return 0
        wan_names = [n for n in names_in_order if by_name[n]['type'] == 'wan' and re.match(r"^wan(\d+)?$", n)]
        wan_names = sorted(set(wan_names), key=_wan_num)
        mem_names = [n for n in names_in_order if by_name[n]['type'] == 'member' and n.startswith("m_wan")]
        def _mem_num(n):
            m = re.match(r"^m_wan(\d+)?$", n)
            if not m:
                return 0
            try:
                return int(m.group(1) or "0")
            except:
                return 0
        mem_names = sorted(set(mem_names), key=_mem_num)
        # collect policies/rules
        src_policy_names = [n for n in names_in_order if by_name[n]['type'] == 'policy' and n != 'balanced']
        src_policy_names = sorted(set(src_policy_names))
        src_rule_names = [n for n in names_in_order if by_name[n]['type'] == 'rule' and n != 'default_all']
        src_rule_names = sorted(set(src_rule_names))
        desired = []
        if 'globals' in by_name and by_name['globals']['type'] == 'globals':
            desired.append('globals')
        desired.extend(wan_names)
        desired.extend(mem_names)
        if 'balanced' in by_name and by_name['balanced']['type'] == 'policy':
            desired.append('balanced')
        # place source policies and rules here
        desired.extend(src_policy_names)
        desired.extend(src_rule_names)
        if 'default_all' in by_name and by_name['default_all']['type'] == 'rule':
            desired.append('default_all')
        # Append all other sections not already placed, preserving their original order
        placed = set(desired)
        for n in names_in_order:
            if n not in placed:
                desired.append(n)
        # Apply reorder to match desired indices
        for idx, sec_name in enumerate(desired):
            _uci_reorder('wanblendr', sec_name, idx)
        _uci_commit('wanblendr')
    except:
        pass
def _configure_wanblendr_for(wan_name):
    try:
        idx = _wan_suffix_number(wan_name)
        tmark_dec = int("20%s" % idx)
        tmark_hex = "0x%X" % tmark_dec
        # Ensure globals and default rule/policy exist
        _ensure_wanblendr_globals()
        _ensure_default_rule_and_policy()
        # Create/Update WAN section with fixed track_ip=8.8.8.8
        _uci_set("wanblendr.%s" % wan_name, "wan")
        _uci_set("wanblendr.%s.ifname" % wan_name, wan_name)
        _uci_set("wanblendr.%s.table" % wan_name, str(tmark_dec))
        _uci_set("wanblendr.%s.mark" % wan_name, tmark_hex)
        _uci_delete("wanblendr.%s.track_ip" % wan_name)
        _uci_add_list("wanblendr.%s.track_ip" % wan_name, "8.8.4.4")
        # Create/Update member section m_wanX with weight=1
        mname = "m_%s" % wan_name
        _uci_set("wanblendr.%s" % mname, "member")
        _uci_set("wanblendr.%s.interface" % mname, wan_name)
        _uci_set("wanblendr.%s.weight" % mname, "1")
        # Rebuild balanced members list to include all current members
        _rebuild_balanced_members()
        _uci_commit("wanblendr")
        _normalize_wanblendr_order()
        return True, "ok"
    except Exception as e:
        try:
            return False, safe_str(e)
        except:
            return False, "wanblendr error"
def commit_and_restart_network():
    _uci_commit("network")
    _uci_commit("firewall")
    _run_bg("/etc/init.d/network reload")
    return True, "scheduled"
def _ubus_status(name):
    out = _capture_cmd("ubus call network.interface.%s status" % safe_str(name))
    out = (out or "").strip()
    res = {'up': False, 'uptime': 0, 'ipv4_address': '', 'gateway': '', 'dns': ''}
    if not out:
        return res
    try:
        data = json.loads(out)
    except:
        return res
                 
    res['up'] = bool(data.get('up'))
    try:
        res['uptime'] = int(data.get('uptime') or 0)
    except:
        res['uptime'] = 0
    ip4_list = data.get('ipv4-address') or []
    if isinstance(ip4_list, list) and ip4_list:
        addr = ip4_list[0].get('address')
        if addr:
            res['ipv4_address'] = safe_str(addr)
    dns_list = data.get('dns-server') or []
    if isinstance(dns_list, list) and dns_list:
        try:
            res['dns'] = ", ".join([safe_str(x) for x in dns_list])
        except:
            res['dns'] = ""
    routes = data.get('route') or []
    gw = ''
    if isinstance(routes, list):
        for r in routes:
            tgt = r.get('target')
            msk = r.get('mask')
            if (tgt == '0.0.0.0' and (msk in (0, '0', None))) or (tgt == '0.0.0.0/0'):
                gw = safe_str(r.get('nexthop') or '')
                if gw:
                    break
    res['gateway'] = gw
    return res
def _ubus_dns_list(name):
    try:
        out = _capture_cmd("ubus call network.interface.%s status" % safe_str(name))
        out = (out or "").strip()
        if not out:
            return []
        data = json.loads(out)
        dns_list = data.get('dns-server') or []
        if isinstance(dns_list, list):
            try:
                return [safe_str(x).strip() for x in dns_list if safe_str(x).strip()]
            except:
                return []
        return []
    except:
        return []
def _mac_compact_lower(mac):
    s = safe_str(mac or '').strip()
    try:
        s = s.replace(":", "").replace("-", "").lower()
    except:
        pass
    return s
def _read_mac_for_dev(dev):
    d = safe_str(dev or '').strip()
    if not d:
        return 'N/A'
    base = d.split('.', 1)[0]
    try:
        with open('/sys/class/net/%s/address' % base, 'r') as f:
            mac = (f.read() or '').strip()
            if mac:
                return mac
    except:
        pass
    try:
        out = _capture_cmd("ethtool -P %s" % base)
        if out:
            for line in out.splitlines():
                s = (line or '').strip().lower()
                if s.startswith('permanent address:'):
                    mac = line.split(':', 1)[1].strip()
                    if mac:
                        return mac
    except:
        pass
    return 'N/A'
def _hostname_for_dev(dev):
    return "*"
def _is_valid_ipv4(addr):
    s = safe_str(addr).strip()
    parts = s.split('.')
    if len(parts) != 4:
        return False
    for p in parts:
        if not p.isdigit():
            return False
        try:
            n = int(p)
        except:
            return False
        if n < 0 or n > 255:
            return False
        if p != str(n):
            return False
    return True
def _display_iface_label_from_dev(dev):
    s = safe_str(dev or '')
    m = re.match(r"^p(\d+)\.(\d+)$", s)
    if m:
        return "eth%s.%s" % (m.group(1), m.group(2))
    m = re.match(r"^p(\d+)$", s)
    if m:
        return "eth%s" % m.group(1)
    return s
def _pick_gateway_from_routes(st):
    try:
        routes = st.get("route") or []
        for r in routes:
            tgt = r.get("target")
            msk = r.get("mask", -1)
            if (tgt == "0.0.0.0") or (msk == 0):
                nh = r.get("nexthop")
                if nh:
                    return nh
    except:
        pass
    return st.get("ipv4-gateway") or ""
def _join_dns(st):
    try:
        dns = st.get("dns-server") or []
        if isinstance(dns, list):
            return ", ".join([safe_str(x) for x in dns])
    except:
        pass
    return ""
def _first_ipv4_cidr(st):
    try:
        addrs = st.get("ipv4-address") or []
        if addrs:
            a = addrs[0]
            ip = a.get("address") or ""
            mask = int(a.get("mask") or 0)
            if ip and mask >= 0:
                return "%s/%s" % (ip, mask)
    except:
        pass
    return ""
def build_wan_table_rows():
    rows = []
    names = []
    for ifn in _list_interface_sections():
        if re.match(r"^wan(\d+)?$", ifn):
            names.append(ifn)
    def _wan_key(nm):
        m = re.match(r"^wan(\d+)?$", nm)
        if m:
            if m.group(1):
                return int(m.group(1)) + 1
            return 1
        return 9999
    names.sort(key=_wan_key)
    for ifn in names:
        proto = _get_interface_field(ifn, "proto") or ""
        dev   = _get_interface_field(ifn, "device") or _get_interface_field(ifn, "ifname") or ""
        cmt   = _get_interface_field(ifn, "comment") or ""
        iface_label = _display_iface_label_from_dev(dev)
        st = _ubus_status(ifn)
        status = "Up+" if st.get('up') else "Down-"
        uptime = _fmt_uptime(st.get('uptime', 0))
        ip4    = st.get('ipv4_address') or ""
        gw     = st.get('gateway') or ""
        dns    = st.get('dns') or ""
        typ = proto.upper() if proto else ""
        auto_val = _get_interface_field(ifn, "auto").strip()
        rows.append({
            "Name": ifn,
            "RealName": ifn,
            "Type": typ,
            "Interface": iface_label,
            "IP_Address": ip4,
            "Gateway": gw,
            "DNS": dns,
            "Status": status,
            "Uptime": uptime,
            "Comment": cmt,
            "Auto": auto_val if auto_val else ""
        })
    def _wan_sort_key(row):
        m = re.match(r"^wan(\d+)?$", row.get("Name",""))
        if m:
            if m.group(1):
                return int(m.group(1)) + 1
            return 1
        return 9999
    rows.sort(key=_wan_sort_key)
    return rows
def set_wan_auto(name, auto_value):
    nm = safe_str(name).strip()
    val = "1" if safe_str(auto_value).strip() == "1" else "0"
    if not nm:
        return False, "Missing name"
    _uci_set("network.%s.auto" % nm, val)
    ok, msg = commit_and_restart_network()
    return (True, "ok") if ok else (False, msg or "reload failed")
def get_wan_info(name):
    name = (name or "").strip()
    if not name:
        return {}
    proto = _get_interface_field(name, "proto")
    dev   = _get_interface_field(name, "device") or _get_interface_field(name, "ifname")
    metric= _get_interface_field(name, "metric")
    cmt   = _get_interface_field(name, "comment")
    info = {
        "name": name,
        "type": (proto or "").lower(),
        "interface": dev or "",
        "metric": metric or "",
        "comment": cmt or ""
    }
    if proto == "static":
        info["ip_address"] = _get_interface_field(name, "ipaddr")
        info["net_mask"]   = _get_interface_field(name, "netmask")
        info["gateway"]    = _get_interface_field(name, "gateway")
        info["dns"]        = _get_interface_field(name, "dns")
    elif proto == "pppoe":
        info["username"] = _get_interface_field(name, "username")
    return info
def add_wan_interface(payload_or_ifname, proto=None, comment=None, **kw):
    if isinstance(payload_or_ifname, dict):
        d = payload_or_ifname
        ifname  = (d.get("ifname") or d.get("interface") or "").strip()
        proto   = (d.get("proto")  or d.get("type")      or "").strip().lower()
        comment = (d.get("comment") or "").strip()
        username= (d.get("username") or "").strip()
        password= (d.get("password") or "").strip()
        ipaddr  = (d.get("ip_address") or "").strip()
        netmask = (d.get("net_mask")   or "").strip()
        gateway = (d.get("gateway")    or "").strip()
        dns     = (d.get("dns")        or "").strip()
    else:
        ifname  = (payload_or_ifname or "").strip()
        proto   = (proto or "").strip().lower()
        comment = (comment or "").strip()
        username= kw.get("username","").strip()
        password= kw.get("password","").strip()
        ipaddr  = kw.get("ip_address","").strip()
        netmask = kw.get("net_mask","").strip()
        gateway = kw.get("gateway","").strip()
        dns     = kw.get("dns","").strip()
    if not ifname or not proto:
        return False, "Missing interface/proto"
    metric = _choose_free_metric()
    name   = _name_for_metric(metric)
    if proto in ("dhcp", "static"):
        _uci_set("network.%s" % name, "interface")
        _uci_set("network.%s.proto"   % name, proto)
        _uci_set("network.%s.device"  % name, ifname)
        _uci_set("network.%s.metric"  % name, str(metric))
        _uci_set("network.%s.ipv6"    % name, "0")
        _uci_set("network.%s.delegate"% name, "0")
        _uci_set("network.%s.hostname"% name, _hostname_for_dev(ifname))
        _uci_set("network.%s.auto"    % name, "1")
        if proto == "dhcp":
            # Default: use ISP DNS (peerdns=1); switching to static will set it to 0 in editor
            _uci_set("network.%s.peerdns" % name, "1")
        if comment:
            _uci_set("network.%s.comment" % name, comment)
        if proto == "static":
            if not (ipaddr and netmask):
                return False, "Missing IP/Netmask for static"
            _uci_set("network.%s.ipaddr"  % name, ipaddr)
            _uci_set("network.%s.netmask" % name, netmask)
            if gateway:
                _uci_set("network.%s.gateway" % name, gateway)
            if dns:
                _uci_set("network.%s.dns" % name, dns)
        _add_interface_to_wan_zone(name)
        _configure_wanblendr_for(name)
        ok, msg = commit_and_restart_network()
        return (True, "added") if ok else (False, msg)
    elif proto == "pppoe":
        if not (username and password):
            return False, "PPPoE requires credentials"
        _uci_set("network.%s" % name, "interface")
        _uci_set("network.%s.proto"    % name, "pppoe")
        _uci_set("network.%s.device"   % name, ifname)                                      
        _uci_set("network.%s.username" % name, username)
        _uci_set("network.%s.password" % name, password)
        _uci_set("network.%s.ipv6"     % name, "0")
        _uci_set("network.%s.metric"   % name, str(metric))
        _uci_set("network.%s.delegate" % name, "0")
        _uci_set("network.%s.keepalive"% name, "3 10")
        _uci_set("network.%s.hostname"% name, _hostname_for_dev(ifname))
        _uci_set("network.%s.auto"     % name, "1")
        # Default: use ISP DNS (peerdns=1)
        _uci_set("network.%s.peerdns" % name, "1")
        if comment:
            _uci_set("network.%s.comment" % name, comment)
        _add_interface_to_wan_zone(name)
        _configure_wanblendr_for(name)
        ok, msg = commit_and_restart_network()
        return (True, "added") if ok else (False, msg)
    else:
        return False, "Unsupported type"
def delete_wan_interface(name):
    name = (name or "").strip()
    if not name:
        return False
    dev = _get_interface_field(name, "device") or _get_interface_field(name, "ifname")
    _delete_interface(name)
    if dev:
        idx = _find_device_section_index_by_name(dev)
        if idx is not None:
            dtype = _device_type_for_name(dev)
            if dtype == "macvlan":
                _uci_delete("network.@device[%s]" % idx)
    idx_zone = _find_firewall_wan_zone_index()
    if idx_zone is not None:
        _uci_del_list("firewall.@zone[%s].network" % idx_zone, name)
    try:
        # Delete WAN section
        _uci_delete("wanblendr.%s" % name)
        # Delete member section
        _uci_delete("wanblendr.m_%s" % name)
        # Cleanup Source LB policies that reference this WAN
        _cleanup_source_policies_for_wan(name)
        # Update balanced policy members after deletion
        _ensure_wanblendr_globals()
        _ensure_default_rule_and_policy()
        _rebuild_balanced_members()
        _normalize_wanblendr_order()
        _uci_commit("wanblendr")
    except:
        pass
    ok, _ = commit_and_restart_network()
    return ok
def _find_device_section_index_by_name(dev_name):
    r = re.compile(r"^network\.@device\[(\d+)\]\.name='?([^']+)'?")
    for ln in _network_show_lines():
        ln = ln.strip()
        m = r.match(ln)
        if m and m.group(2) == dev_name:
            return m.group(1)
    return None
def get_pppoe_list_for_ui():
    out = []
    for nm in _list_interface_sections():
        if _get_interface_field(nm, "proto") == "pppoe":
            out.append({
                "name": nm,
                "username": _get_interface_field(nm, "username")
            })
    return out
def save_pppoe_selection(selected):
    return True
def _get_dns_list(name):
    dns = []
    try:
        prefix = "network.%s.dns=" % safe_str(name)
        for ln in _uci_show('network').splitlines():
            s = (ln or '').strip()
            if not s.startswith(prefix):
                continue
            rhs = s[len(prefix):].strip()
            if not rhs:
                continue
            cleaned = rhs.replace("'", " ").replace('"', " ")
            parts = [p.strip() for p in cleaned.split() if p.strip()]
            for p in parts:
                if _is_valid_ipv4(p):
                    dns.append(p)
    except:
        pass
    return dns
def list_dhcp_interfaces_for_dns():
    items = []
    try:
        for nm in _list_interface_sections():
            proto = (_get_interface_field(nm, "proto") or "").lower()
            if proto not in ("dhcp", "pppoe"):
                continue
            pd = _get_interface_field(nm, "peerdns").strip()
            dns = _get_dns_list(nm)
            if (pd == '1' or pd == '') and not dns:
                try:
                    dns = _ubus_dns_list(nm)
                except:
                    dns = []
            if not isinstance(dns, list):
                dns = []
            try:
                dns = [x for x in dns if x][:2]
            except:
                pass
            items.append({
                'name': nm,
                'peerdns': pd if pd else '',
                'dns': dns
            })
    except:
        pass
    return items
def save_dns_settings(payload):
    try:
        items = payload if isinstance(payload, list) else []
    except:
        items = []
    # validate first to avoid partial commit
    for it in items:
        try:
            static = bool(it.get('static', False))
            if not static:
                continue
            d1 = safe_str(it.get('dns1','')).strip()
            d2 = safe_str(it.get('dns2','')).strip()
            if d1 and not _is_valid_ipv4(d1):
                return False
            if d2 and not _is_valid_ipv4(d2):
                return False
        except:
            return False
    for it in items:
        try:
            nm = safe_str(it.get('name','')).strip()
            if not nm: 
                continue
            static = bool(it.get('static', False))
            dns1 = safe_str(it.get('dns1','')).strip()
            dns2 = safe_str(it.get('dns2','')).strip()
            if static:
                _uci_set("network.%s.peerdns" % nm, "0")
                _uci_delete("network.%s.dns" % nm)
                if dns1:
                    _uci_add_list("network.%s.dns" % nm, dns1)
                if dns2:
                    _uci_add_list("network.%s.dns" % nm, dns2)
            else:
                _uci_set("network.%s.peerdns" % nm, "1")
                _uci_delete("network.%s.dns" % nm)
        except:
            continue
    _uci_commit("network")
    ok, _ = commit_and_restart_network()
    return ok
