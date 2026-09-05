                         
                                                                  
import os
import ure as re
import ujson as json
import utime as time
NETWORK_FILE = "/etc/config/network"
FIREWALL_FILE = "/etc/config/firewall"
                                     
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
        with open(path, "r") as f:
            return f.read()
    except:
        return None
def _write_text(path, text):
    try:
        with open(path, "w") as f:
            f.write(text)
        return True
    except:
        return False
def _read_lines(path):
    txt = _read_text(path)
    return txt.splitlines(True) if txt is not None else None
def _ticks_now():
    try:
        return time.ticks_ms()
    except:
        return int(time.time() * 1000)
def _capture_cmd(cmd):
    c = safe_str(cmd)
    tmp = "/tmp/_uipy_%s.txt" % safe_str(_ticks_now())
    os.system("%s > %s 2>&1" % (c, tmp))
    out = _read_text(tmp) or ""
    try:
        os.remove(tmp)
    except:
        pass
    return out
_CIDR_LOOKUP = {
    "255.0.0.0": 8,
    "255.128.0.0": 9,
    "255.192.0.0": 10,
    "255.224.0.0": 11,
    "255.240.0.0": 12,
    "255.248.0.0": 13,
    "255.252.0.0": 14,
    "255.254.0.0": 15,
    "255.255.0.0": 16,
    "255.255.128.0": 17,
    "255.255.192.0": 18,
    "255.255.224.0": 19,
    "255.255.240.0": 20,
    "255.255.248.0": 21,
    "255.255.252.0": 22,
    "255.255.254.0": 23,
    "255.255.255.0": 24,
    "255.255.255.128": 25,
    "255.255.255.192": 26,
    "255.255.255.224": 27,
    "255.255.255.240": 28,
    "255.255.255.248": 29,
    "255.255.255.252": 30,
    "255.255.255.254": 31,
    "255.255.255.255": 32,
}
def netmask_to_cidr(netmask):
    nm = (netmask or "").strip()
    if not nm:
        return ""
    if nm.isdigit():
        return nm
    if nm in _CIDR_LOOKUP:
        return str(_CIDR_LOOKUP[nm])
                          
    parts = nm.split(".")
    if len(parts) != 4:
        return ""
    try:
        ones = 0
        for p in parts:
            v = int(p)
            if v < 0 or v > 255:
                return ""
            while v:
                ones += (v & 1)
                v >>= 1
        return str(ones)
    except:
        return ""
def cidr_to_netmask(cidr):
    try:
        c = int(cidr)
        mask = (0xffffffff << (32 - c)) & 0xffffffff
        return "%d.%d.%d.%d" % ((mask >> 24) & 0xff, (mask >> 16) & 0xff, (mask >> 8) & 0xff, mask & 0xff)
    except:
        return ""
def is_valid_gateway_ip(ip):
    octets = ip.split(".")
    if len(octets) != 4:
        return False
    try:
        for i in range(3):
            v = int(octets[i])
            if v < 0 or v > 255:
                return False
        last_v = int(octets[3])
        if last_v < 1 or last_v > 253:
            return False
    except:
        return False
    return True
def parse_config_interfaces():
    if not os.path.exists(NETWORK_FILE):
        return []
    lines = _read_lines(NETWORK_FILE) or []
    interfaces = []
    i = 0
    while i < len(lines):
        line_raw = lines[i]
        line = line_raw.strip()
        if line.startswith("config interface '"):
            m = re.search(r"config interface '([^']+)'", line)
            if not m:
                i += 1
                continue
            iface_name = m.group(1)
            if not (iface_name == "lan" or re.match(r"^lan\d+$", iface_name)):
                i += 1
                continue
            iface = {'name': iface_name, 'device': '', 'ipaddr': '', 'netmask': '', 'prefix': '', 'start': i, 'end': i}
            i += 1
            while i < len(lines):
                sub_raw = lines[i]
                sub = sub_raw.strip()
                if sub.startswith("config "):
                    break
                dm = re.search(r"option device\s+['\"]?([^'\"\s]+)", sub)
                if not dm:
                    dm = re.search(r"option ifname\s+['\"]?([^'\"\s]+)", sub)
                if dm and not iface['device']:
                    iface['device'] = dm.group(1)
                im = re.search(r"option ipaddr\s+['\"]?([^'\"\s]+)", sub)
                if im and not iface['ipaddr']:
                    iface['ipaddr'] = im.group(1)
                mm = re.search(r"option netmask\s+['\"]?([^'\"\s]+)", sub)
                if mm and not iface['netmask']:
                    iface['netmask'] = mm.group(1)
                pm = re.search(r"option prefix\s+['\"]?(\d+)", sub)
                if pm and not iface['prefix']:
                    iface['prefix'] = pm.group(1)
                i += 1
            iface['end'] = i - 1
            interfaces.append(iface)
        else:
            i += 1
    return interfaces
def parse_firewall_zone_lan():
    if not os.path.exists(FIREWALL_FILE):
        return {'start': -1, 'end': -1, 'lines': [], 'networks': []}, []
    fw_lines = _read_lines(FIREWALL_FILE) or []
    zone = {'start': -1, 'end': -1, 'lines': [], 'networks': []}
    i = 0
    while i < len(fw_lines):
        line = fw_lines[i].strip()
        if line.startswith("config zone"):
            j = i + 1
            has_lan_name = False
            while j < len(fw_lines) and fw_lines[j].strip().startswith("option "):
                if "option name 'lan'" in fw_lines[j]:
                    has_lan_name = True
                    break
                j += 1
            if has_lan_name:
                start_idx = i
                i += 1
                while i < len(fw_lines) and not fw_lines[i].strip().startswith("config "):
                    i += 1
                end_idx = i - 1
                zone['start'] = start_idx
                zone['end'] = end_idx
                zone['lines'] = fw_lines[start_idx:end_idx+1]
                break
        i += 1
    if zone['start'] >= 0:
        nets = []
        for ln in zone['lines']:
            s = ln.strip()
            m = re.search(r"list network\s+'([^']+)'", s)
            if m:
                nets.append(m.group(1))
        zone['networks'] = nets
    return zone, fw_lines
                                                  
def get_available_interfaces():
    result = []
    out = _capture_cmd("ip -br link show")
    if out:
        for line in out.splitlines():
            s = line.strip()
            if not s:
                continue
            first = s.split()[0]                              
            base = first.split('@')[0]
            if re.match(r"^p\d+(\.\d+)?$", base) \
               or re.match(r"^zeoip\d+$", base) \
               or re.match(r"^br\d+$", base) \
               or re.match(r"^sfp\d*$", base) \
               or ('.' in base):
                result.append(base)
    if not result:
        try:
            for d in os.listdir('/sys/class/net'):
                base = safe_str(d)
                if base in ('lo',):
                    continue
                if re.match(r"^p\d+(\.\d+)?$", base) \
                   or re.match(r"^zeoip\d+$", base) \
                   or re.match(r"^br\d+$", base) \
                   or re.match(r"^sfp\d*$", base) \
                   or ('.' in base):
                    result.append(base)
        except:
            pass
    lines = _read_lines(NETWORK_FILE) or []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("config device"):
            name_val = None
            type_val = None
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("config "):
                nm = re.search(r"option name\s+['\"]([^'\"]+)", lines[j].strip())
                tm = re.search(r"option type\s+['\"]([^'\"]+)", lines[j].strip())
                if nm: name_val = nm.group(1)
                if tm: type_val = tm.group(1)
                j += 1
            if name_val and (type_val in ("bridge", "8021q")):
                result.append(name_val)
            i = j
        else:
            i += 1
    out_list = []
    seen = {}
    for x in result:
        if x not in seen:
            seen[x] = True
            out_list.append(x)
    return out_list
def get_next_lan_name(exist_names):
    found_lan = False
    nums = []
    for n in exist_names:
        if n == "lan":
            found_lan = True
        else:
            m = re.match(r"^lan(\d+)$", n)
            if m:
                try:
                    nums.append(int(m.group(1)))
                except:
                    pass
    if not found_lan:
        return "lan"
    nums.sort()
    expected = 1
    for x in nums:
        if x != expected:
            return "lan%d" % expected
        expected += 1
    return "lan%d" % expected
def fix_blank_lines_in_network_file():
    lines = _read_lines(NETWORK_FILE)
    if lines is None:
        return
    out_lines = []
    for line in lines:
        if line.strip().startswith("config interface") and out_lines and out_lines[-1].strip() != "":
            out_lines.append("\n")
        out_lines.append(line)
    _write_text(NETWORK_FILE, "".join(out_lines))
                                                   
def add_lan_interface(name, device, ipaddr, netmask):
    try:
        with open(NETWORK_FILE, "a") as f:
            f.write("config interface '%s'\n" % name)
            f.write("\toption proto 'static'\n")
            f.write("\toption device '%s'\n" % device)
            f.write("\toption ipaddr '%s'\n" % ipaddr)
            f.write("\toption netmask '%s'\n" % netmask)
            f.write("\toption delegate '0'\n")
            f.write("\n")
    except:
        return False, "Unable to write network config."
    zone_data, fw_lines = parse_firewall_zone_lan()
    if zone_data['start'] >= 0:
        if name not in zone_data['networks']:
                                              
            last_list_idx = zone_data['start']
            for idx in range(zone_data['start'], zone_data['end'] + 1):
                if "list network" in fw_lines[idx].strip():
                    last_list_idx = idx
            insert_idx = last_list_idx + 1
            fw_lines.insert(insert_idx, "\tlist network '%s'\n" % name)
            if not _write_text(FIREWALL_FILE, "".join(fw_lines)):
                return False, "Unable to update firewall config."
    fix_blank_lines_in_network_file()
    return True, "OK"
def remove_lan_interface(name):
    lines = _read_lines(NETWORK_FILE)
    if lines is None:
        return False, "Unable to read network config."
    interfaces = parse_config_interfaces()
    target = None
    for itf in interfaces:
        if itf['name'] == name:
            target = itf
            break
    if not target:
        return False, "Interface not found."
    new_lines = lines[:target['start']] + lines[target['end'] + 1:]
    if not _write_text(NETWORK_FILE, "".join(new_lines)):
        return False, "Unable to update network config."
    zone_data, fw_lines = parse_firewall_zone_lan()
    if zone_data['start'] >= 0:
        new_fw = []
        removed = False
        for ln in fw_lines:
            if ln.strip() == "list network '%s'" % name:
                removed = True
                continue
            new_fw.append(ln)
        if removed:
            if not _write_text(FIREWALL_FILE, "".join(new_fw)):
                return False, "Unable to update firewall config."
    fix_blank_lines_in_network_file()
    return True, "OK"
def update_lan_interface(old_name, new_device, new_ip, new_mask):
    lines = _read_lines(NETWORK_FILE)
    if lines is None:
        return False, "Unable to read network config."
    interfaces = parse_config_interfaces()
    target = None
    for itf in interfaces:
        if itf['name'] == old_name:
            target = itf
            break
    if not target:
        return False, "Interface not found."
    block = []
    block.append("config interface '%s'\n" % old_name)
    block.append("\toption proto 'static'\n")
    block.append("\toption device '%s'\n" % new_device)
    block.append("\toption ipaddr '%s'\n" % new_ip)
    block.append("\toption netmask '%s'\n" % new_mask)
    block.append("\toption delegate '0'\n")
    block.append("\n")
    new_file = lines[:target['start']] + block + lines[target['end'] + 1:]
    if not _write_text(NETWORK_FILE, "".join(new_file)):
        return False, "Unable to update network config."
    fix_blank_lines_in_network_file()
    return True, "OK"
def commit_and_reload():
    _capture_cmd("uci commit network")
    _capture_cmd("uci commit firewall")
    _capture_cmd("/etc/init.d/network reload")
    _capture_cmd("/etc/init.d/firewall reload")
    return True, ""
                                               
def _device_label(dev):
    d = safe_str(dev)
    m = re.match(r"^p(\d+)(?:\.(\d+))?$", d)
    if m:
        idx = m.group(1)
        vlan = m.group(2)
        return "eth%s%s" % (idx, ("." + vlan) if vlan else "")
    if d.startswith("zeoip"):
        m2 = re.match(r"^zeoip(\d+)$", d)
        if m2:
            return "EoIP-%s" % m2.group(1)
    return d
def list_lan_table():
    out = []
    ifaces = parse_config_interfaces()
    for itf in ifaces:
        device  = (itf.get('device') or '').strip()
        ipaddr  = (itf.get('ipaddr') or '').strip()
        netmask = (itf.get('netmask') or '').strip()
        prefix  = (itf.get('prefix') or '').strip()
        ip_cidr = ""
        if ipaddr:
            if '/' in ipaddr:
                ip_cidr = ipaddr
                try:
                    pref = ipaddr.split('/', 1)[1]
                    if not netmask and pref.isdigit():
                        netmask = cidr_to_netmask(int(pref)) or netmask
                except:
                    pass
            else:
                if prefix.isdigit():
                    ip_cidr = "%s/%s" % (ipaddr, prefix)
                    if not netmask:
                        try:
                            netmask = cidr_to_netmask(int(prefix)) or netmask
                        except:
                            pass
                else:
                    cidr = netmask_to_cidr(netmask)
                    if cidr:
                        ip_cidr = "%s/%s" % (ipaddr, cidr)
                    else:
                                                           
                        ip_cidr = ipaddr
        row = {
            'name': itf.get('name', ''),
            'device': device,
            'device_label': _device_label(device),
            'ip_cidr': ip_cidr,
            'netmask': netmask
        }
        out.append(row)
    return out
def interfaces_list():
    raw = get_available_interfaces()
    out = []
    for iface in raw:
        out.append({"value": iface, "label": _device_label(iface)})
    return out
def add_entry(device, ip_cidr):
    device = safe_str(device).strip()
    ip_cidr = safe_str(ip_cidr).strip()
    if not device:
        return False, "Interface is required."
    if not ip_cidr or '/' not in ip_cidr:
        return False, "IP Address/CIDR is required."
    parts = ip_cidr.split('/')
    ipaddr = parts[0]
    try:
        cidr_val = int(parts[1])
    except:
        return False, "Invalid CIDR."
    if cidr_val < 1 or cidr_val > 32:
        return False, "CIDR must be between 1 and 32."
    if not is_valid_gateway_ip(ipaddr):
        return False, "Invalid IP address for gateway (must be x.x.x.1-253)."
    existing = parse_config_interfaces()
    for e in existing:
        if e.get('device') == device and e.get('ipaddr') == ipaddr:
            return False, "This IP is already used on the same interface."
    netmask = cidr_to_netmask(cidr_val)
    exist_names = [x.get('name') for x in existing]
    new_name = get_next_lan_name(exist_names)
    ok, msg = add_lan_interface(new_name, device, ipaddr, netmask)
    if not ok:
        return False, msg
    commit_and_reload()
    return True, "OK"
def edit_entry(old_name, device, ip_cidr):
    old_name = safe_str(old_name).strip()
    device = safe_str(device).strip()
    ip_cidr = safe_str(ip_cidr).strip()
    if not old_name:
        return False, "Invalid LAN name."
    if not device:
        return False, "Interface is required."
    if not ip_cidr or '/' not in ip_cidr:
        return False, "IP Address/CIDR is required."
    parts = ip_cidr.split('/')
    ipaddr = parts[0]
    try:
        cidr_val = int(parts[1])
    except:
        return False, "Invalid CIDR."
    if cidr_val < 1 or cidr_val > 32:
        return False, "CIDR must be between 1 and 32."
    if not is_valid_gateway_ip(ipaddr):
        return False, "Invalid IP address (must be x.x.x.1-253)."
    existing = parse_config_interfaces()
    for e in existing:
        if e.get('name') != old_name:
            if e.get('device') == device and e.get('ipaddr') == ipaddr:
                return False, "This IP is already used on the same interface."
    netmask = cidr_to_netmask(cidr_val)
    ok, msg = update_lan_interface(old_name, device, ipaddr, netmask)
    if not ok:
        return False, msg
    commit_and_reload()
    return True, "OK"
def delete_entry(name):
    name = safe_str(name).strip()
    if not name:
        return False, "Invalid name."
    ok, msg = remove_lan_interface(name)
    if not ok:
        return False, msg
    commit_and_reload()
    return True, "OK"
