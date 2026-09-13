import os, ubinascii, uhashlib
def _rename_file(src, dst):
    try:
        os.replace(src, dst)
    except AttributeError:
        os.rename(src, dst)
SECRET     = b"Abd_@_!!_88_22_@Hello_@!0!"
BLOCKSIZE  = 64
def _sha256_hex(data: bytes) -> str:
    h = uhashlib.sha256(data)
    return ubinascii.hexlify(h.digest()).decode()
def _hmac_sha256_hex(key: bytes, msg: bytes) -> str:
    if len(key) > BLOCKSIZE:
        key = uhashlib.sha256(key).digest()
    key = key + b'\x00' * (BLOCKSIZE - len(key))
    o_key_pad = bytes([b ^ 0x5C for b in key])
    i_key_pad = bytes([b ^ 0x36 for b in key])
    inner = uhashlib.sha256(i_key_pad + msg).digest()
    outer = uhashlib.sha256(o_key_pad + inner).digest()
    return ubinascii.hexlify(outer).decode()
def base36_encode(number: int) -> str:
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if number == 0:
        return '0'
    out = []
    while number:
        number, rem = divmod(number, 36)
        out.append(alphabet[rem])
    return ''.join(reversed(out))
def get_hw_model():
    base = "/sys/firmware/mikrotik/hard_config"
    try:
        with open(base + "/product_name") as f:
            prod = f.read().strip()
    except Exception:
        prod = "N/A"
    try:
        with open(base + "/board_product_code") as f:
            code = f.read().strip()
    except Exception:
        code = "N/A"
    return "%s - %s" % (prod, code)
def get_disk_serial():
    try:
        with open("/sys/firmware/mikrotik/hard_config/board_serial") as f:
            return f.read().strip().upper()
    except Exception:
        return None
def get_system_id():
    try:
        with open("/sys/bus/spi/devices/spi0.0/unique_id") as f:
            return f.read().strip().upper()
    except Exception:
        return None
def _pad6(s: str) -> str:
    return ('000000' + s)[-6:]
def generate_machine_key(system_id: str) -> str:
    seed = int(_sha256_hex(system_id.encode()), 16)
    m, s, MOD = 1103515245, 12345, 36**6
    blocks = []
    for _ in range(6):
        seed = abs(seed * m - s)
        blocks.append(_pad6(base36_encode(seed % MOD)))
    return "-".join(blocks)
def generate_license_key(machine_key: str) -> str:
    hm = _hmac_sha256_hex(SECRET, machine_key.encode())
    seed = int(hm, 16)
    m, s, MOD = 6364136223846793005, 1442695040888963407, 36**6
    blocks = []
    for _ in range(6):
        seed = abs(seed * m - s)
        blocks.append(_pad6(base36_encode(seed % MOD)))
    return "-".join(blocks)
def is_valid_license(user_key: str) -> bool:
    sid = get_system_id()
    if not sid:
        return False
    expected = generate_license_key(generate_machine_key(sid))
    return user_key.strip().upper() == expected.upper()
def get_license_status():
    try:
        with open("/sbin/ubsd", "r") as f:
            enc = (f.read() or "").strip()
    except Exception:
        enc = ""
    if not enc:
        return ""
    try:
        dec = ubinascii.a2b_base64(enc)
    except Exception:
        return ""
    try:
        dec_txt = dec.decode()
    except Exception:
        dec_txt = ""
    return "Done" if dec_txt == "ok!" else ""
def get_remaining_time(status: str):
    try:
        with open("/mnt/ser/lic/rem_time") as f:
            t = f.read().strip()
    except Exception:
        return "Trial Expired"
    if status == "Done":
        return "unlimited"
    if t == "00:00:00" or t.startswith("-"):
        return "Trial Expired"
    return t
def adjust_firewall():
    FW_PATH = "/etc/config/firewall"
    if not os.path.exists(FW_PATH):
        return False
    try:
        with open(FW_PATH, "r") as f:
            src_lines = f.readlines()
    except Exception:
        return False
    dst_lines, zone = [], None
    for line in src_lines:
        st = line.strip()
        if st.startswith("config zone"):
            zone = None
        if "option name 'wan'" in st or 'option name "wan"' in st:
            zone = "wan"
        elif "option name 'lan'" in st or 'option name "lan"' in st:
            zone = "lan"
        if zone == "wan":
            if "option output 'REJECT'" in st:
                line = line.replace("REJECT", "ACCEPT")
            if st.startswith("#") and st[1:].lstrip().startswith("list network"):
                indent = line.split('#', 1)[0].rstrip(' \t')
                after  = line.split('#', 1)[1].lstrip()
                line   = indent + "\t" + after
                if not line.endswith("\n"):
                    line += "\n"
        elif zone == "lan":
            if "option forward 'REJECT'" in st:
                line = line.replace("REJECT", "ACCEPT")
            if st.startswith("#") and "option device 'ppp+ pptp+'" in st:
                indent = line.split('#', 1)[0].rstrip(' \t')
                after  = line.split('#', 1)[1].lstrip()
                line   = indent + "\t" + after
                if not line.endswith("\n"):
                    line += "\n"
        dst_lines.append(line)
    if not dst_lines:
        return False
    TMP = FW_PATH + ".tmp"
    BAK = FW_PATH + ".bak"
    try:
        with open(TMP, "w") as f:
            for l in dst_lines:
                f.write(l)
    except Exception:
        try:
            os.remove(TMP)
        except Exception:
            pass
        return False
    try:
        if os.path.exists(BAK):
            os.remove(BAK)
        _rename_file(FW_PATH, BAK)
        _rename_file(TMP, FW_PATH)
    except Exception:
        return False
    return True
def activate_license(user_key: str):
    if not is_valid_license(user_key):
        return False, "Invalid Product key."
    # os.system("/etc/init.d/licc stop")
    _ = adjust_firewall()
    try:
        b64 = ubinascii.b2a_base64(b"ok!")
        try:
            b64_txt = b64.decode().strip()
        except Exception:
            b64_txt = ""
        with open("/sbin/ubsd", "w") as f:
            f.write(b64_txt)
    except Exception:
        return False, "Cannot write lic_mode file."
    os.system("reboot")
    return True, "Device activated. Rebooting..."
def export_license_package():
    try:
        hw = get_hw_model() or 'N/A'
        sid_val = get_system_id() or ''
        machine = generate_machine_key(sid_val) if sid_val else 'N/A'
        raw = 'HW: %s\nMachine: %s\nID: %s\n' % (hw, machine, (sid_val or 'N/A'))
        try:
            b64_txt = ubinascii.b2a_base64(raw.encode()).decode().strip()
        except Exception:
            b64_txt = ''
        tmp_txt = '/tmp/license_export.txt'
        zip_name = 'Export_%s.zip' % ((sid_val or 'ID'))
        tmp_zip = '/tmp/' + zip_name
        ok_txt = False
        try:
            with open(tmp_txt, 'w') as f:
                f.write(b64_txt + '\n')
            ok_txt = True
        except Exception:
            ok_txt = False
        data_bytes = b''
        mime = 'text/plain; charset=utf-8'
        filename = 'license_export.txt'
        if ok_txt:
            try:
                if os.path.exists(tmp_zip):
                    os.remove(tmp_zip)
            except Exception:
                pass
            rc = os.system("cd /tmp && bsdtar --format=zip --options zip:encryption=zipcrypt,compression=store --passphrase '01_08_2025@!00_99!!' -cf '%s' '%s' >/dev/null 2>&1" % (zip_name, 'license_export.txt'))
            if (rc == 0) and os.path.exists(tmp_zip):
                try:
                    with open(tmp_zip, 'rb') as f:
                        data_bytes = f.read()
                    if len(data_bytes) >= 2 and data_bytes[:2] == b'PK':
                        mime = 'application/zip'
                        filename = zip_name
                    else:
                        return False, {'bytes': b'', 'mime': 'text/plain; charset=utf-8', 'filename': 'license_export.txt'}
                except Exception:
                    return False, {'bytes': b'', 'mime': 'text/plain; charset=utf-8', 'filename': 'license_export.txt'}
            else:
                return False, {'bytes': b'', 'mime': 'text/plain; charset=utf-8', 'filename': 'license_export.txt'}
        else:
            return False, {'bytes': b'', 'mime': 'text/plain; charset=utf-8', 'filename': 'license_export.txt'}
        try:
            os.remove(tmp_txt)
        except Exception:
            pass
        try:
            if os.path.exists(tmp_zip):
                os.remove(tmp_zip)
        except Exception:
            pass
        return True, {'bytes': data_bytes, 'mime': mime, 'filename': filename}
    except Exception:
        return False, {'bytes': b'', 'mime': 'text/plain; charset=utf-8', 'filename': 'license_export.txt'}
