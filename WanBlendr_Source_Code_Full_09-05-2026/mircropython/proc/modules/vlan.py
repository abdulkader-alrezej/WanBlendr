                          
                                                              
import os
import ure as re
import ujson as json
import utime as time
NETWORK_FILE = "/etc/config/network"
                                     
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
def parse_vlan_devices():
    devices = []
    content = _read_text(NETWORK_FILE)
    if not content:
        return devices
    sections = content.split("config device")
    for section in sections[1:]:
        lines = section.strip().splitlines()
        data = {}
        for line in lines:
            s = line.strip()
            if s.startswith("option "):
                parts = s.split(None, 2)
                if len(parts) == 3:
                    key = parts[1]
                    val = parts[2].strip().strip("'")
                    data[key] = val
        if data.get("type") == "8021q":
            devices.append({
                "name"     : data.get("name", ""),
                "vlan_type": "802.1Q",
                "nic"      : data.get("ifname", ""),
                "vlan_id"  : data.get("vid", ""),
                "ipv6"     : data.get("ipv6", ""),
            })
    return devices
def vlan_exists(nic, vlan_id):
    nic = safe_str(nic).strip()
    vlan_id = safe_str(vlan_id).strip()
    devs = parse_vlan_devices()
    for d in devs:
        if d.get("nic") == nic and safe_str(d.get("vlan_id")) == vlan_id:
            return True
    return False
def _append_vlan_section(nic, vlan_id):
    name = "%s.%s" % (nic, vlan_id)
    sect = [
        "config device",
        "\toption type '8021q'",
        "\toption ifname '%s'" % nic,
        "\toption vid '%s'" % vlan_id,
        "\toption name '%s'" % name,
        "\toption ipv6 '0'",
    ]
    section_text = "\n".join(sect)
    content = _read_text(NETWORK_FILE)
    if content is None:
        return _write_text(NETWORK_FILE, section_text + "\n\n")
    stripped = content.rstrip("\n")
    new_content = stripped + "\n\n" + section_text + "\n\n"
    return _write_text(NETWORK_FILE, new_content)
def add_vlan_device(nic, vlan_id):
    if not nic or not vlan_id:
        return False
    if vlan_exists(nic, vlan_id):
        return False
    devices = parse_vlan_devices()
    name = "%s.%s" % (nic, vlan_id)
    for d in devices:
        if d.get("name") == name:
            return False
    return _append_vlan_section(nic, vlan_id)
def commit_and_reload():
    _capture_cmd("uci commit network")
    _capture_cmd("uci commit firewall")
    _capture_cmd("/etc/init.d/network reload")
    _capture_cmd("/etc/init.d/firewall reload")
    return True, ""
def list_virtual_eths():
    out = _capture_cmd("ip link show")
    eths = []
    re_p = re.compile(r"^\s*\d+:\s+(p(\d+))@")
    re_sfp = re.compile(r"^\s*\d+:\s+(sfp)@")
    seen = {}
    for line in out.splitlines():
        m = re_p.match(line)
        if m:
            num = m.group(2)       
            if num:
                virt = "eth%s" % num
                if virt != "eth0" and (virt not in seen):
                    seen[virt] = True
                    eths.append(virt)
            continue
        m2 = re_sfp.match(line)
        if m2:
            virt = "sfp"
            if virt not in seen:
                seen[virt] = True
                eths.append(virt)
    return eths
def virtual_to_physical(virtual_nic):
    v = safe_str(virtual_nic)
    m = re.match(r"^eth(\d+)$", v)
    if m:
        return "p%s" % m.group(1)
    return v
def is_vlan_linked_to_interface(vlan_name):
    lines = _read_lines(NETWORK_FILE)
    if not lines:
        return False, None
    in_iface = False
    for line in lines:
        s = line.strip()
        if s.startswith("config interface"):
            in_iface = True
            continue
        if in_iface and s.startswith("option device"):
            if ("'%s'" % vlan_name) in s:
                return True, None
        if s.startswith("config "):
            in_iface = False
    return False, None
def delete_vlan_device(nic_physical, vlan_id):
    vlan_name = "%s.%s" % (nic_physical, vlan_id)
    linked, _ = is_vlan_linked_to_interface(vlan_name)
    if linked:
        return False, "Remove VLAN from interface first."
    lines = _read_lines(NETWORK_FILE)
    if lines is None:
        return False, "Network config not found."
    new_lines = []
    buffer = []
    in_dev = False
    match_type = match_if = match_vid = False
    def flush_buffer(keep):
        nonlocal buffer, new_lines
        if keep and buffer:
            new_lines.extend(buffer)
        buffer = []
    for line in lines:
        stripped_lead = line.lstrip()
        if stripped_lead.startswith("config device"):
            if in_dev:
                keep_prev = not (match_type and match_if and match_vid)
                flush_buffer(keep_prev)
            in_dev = True
            match_type = match_if = match_vid = False
            buffer.append(line)
            continue
        if in_dev:
            buffer.append(line)
            s = stripped_lead.strip()
            if s.startswith("option type") and "8021q" in s:
                match_type = True
            elif s.startswith("option ifname") and ("'%s'" % nic_physical) in s:
                match_if = True
            elif s.startswith("option vid") and ("'%s'" % vlan_id) in s:
                match_vid = True
            if stripped_lead.startswith("config ") and not stripped_lead.startswith("config device"):
                keep_prev = not (match_type and match_if and match_vid)
                flush_buffer(keep_prev)
                in_dev = False
        else:
            new_lines.append(line)
    if in_dev:
        keep_prev = not (match_type and match_if and match_vid)
        flush_buffer(keep_prev)
    ok = _write_text(NETWORK_FILE, "".join(new_lines))
    if not ok:
        return False, "Failed to write network config."
    ok2, err2 = commit_and_reload()
    if not ok2:
        return False, err2
    return True, ""
def list_vlan_devices_display():
    out = []
    for d in parse_vlan_devices():
        nic = safe_str(d.get("nic", ""))
        name = safe_str(d.get("name", ""))
        m_n = re.match(r"^p(\d+)$", nic)
        if m_n:
            nic_disp = "eth%s" % m_n.group(1)
        else:
            nic_disp = nic
        m2 = re.match(r"^p(\d+)\.(\d+)$", name)
        if m2:
            name_disp = "eth%s.%s" % (m2.group(1), m2.group(2))
        else:
            name_disp = name
        out.append({
            "name": name_disp,
            "vlan_type": d.get("vlan_type", "802.1Q"),
            "nic": nic_disp,
            "vlan_id": safe_str(d.get("vlan_id", "")),
        })
    return out
def add_vlan_batch_from_virtual(nic_virtual, start_vlan, end_vlan):
    if not nic_virtual:
        return False, [], [], "Missing NIC."
    try:
        s = int(start_vlan)
        e = int(end_vlan)
    except:
        return False, [], [], "VLAN values must be numbers."
    if s < 1 or e > 4060 or s > e:
        return False, [], [], "Invalid VLAN range."
    nic_phys = virtual_to_physical(nic_virtual)
    added, skipped = [], []
    for vid in range(s, e + 1):
        vid_s = safe_str(vid)
        if vlan_exists(nic_phys, vid_s):
            skipped.append(vid)
            continue
        if add_vlan_device(nic_phys, vid_s):
            added.append(vid)
        else:
            skipped.append(vid)
    ok, err = commit_and_reload()
    if not ok:
        return False, added, skipped, err
    return True, added, skipped, ""
