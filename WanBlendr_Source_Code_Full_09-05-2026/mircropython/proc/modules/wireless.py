                                                   
import os, ujson
CFG_FILE = '/etc/config/wireless'                                  
def _read_lines():
    try:
        with open(CFG_FILE) as f:
            return f.readlines()
    except:
        return []
def _write_lines(lines):
    try:
        tmp = CFG_FILE + '.tmp'
        with open(tmp, 'w') as f:
            for ln in lines:
                f.write(ln)
        os.rename(tmp, CFG_FILE)                                            
        return True, 'saved'
    except Exception as e:
        return False, str(e)
def _block_end(lines, start):
    i = start + 1
    while i < len(lines) and not lines[i].lstrip().startswith('config '):
        i += 1
    return i
def _find_iface_block(lines, radio):
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith('config wifi-iface'):
            end = _block_end(lines, i)
            for j in range(i, end):
                parts = lines[j].strip().split(None, 2)
                if len(parts) >= 3 and parts[0] == 'option' and parts[1] == 'device':
                    if parts[2].strip('\'"') == radio:
                        return i, end
            i = end
        else:
            i += 1
    return None, None
def _insert_option(lines, blk_start, blk_end, indent, key, value):
    insert_at = blk_end
    while insert_at - 1 > blk_start and lines[insert_at - 1].strip() == '':
        insert_at -= 1
    lines.insert(insert_at, f"{indent}option {key} '{value}'\n")
    return blk_end + 1                         
def read_radio(radio):
    out = {'ssid': '', 'key': '', 'disabled': 0}
    lns = _read_lines()
    i, end = _find_iface_block(lns, radio)
    if i is None:
        return out
    for j in range(i, end):
        parts = lns[j].strip().split(None, 2)
        if len(parts) < 3 or parts[0] != 'option':
            continue
        k, v = parts[1], parts[2].strip('\'"')
        if   k == 'ssid'    : out['ssid']     = v
        elif k == 'key'     : out['key']      = v
        elif k == 'disabled': out['disabled'] = int(v or 0)
    return out
def snapshot():
    return {'radio0': read_radio('radio0'),
            'radio1': read_radio('radio1')}
def save_radio(radio, ssid, key, disabled):
    disabled = 1 if str(disabled) in ('1', 'true', 'True') else 0
    lns = _read_lines()
    i, end = _find_iface_block(lns, radio)
    if i is None:
        return False, f'radio {radio} not found'
    f_ssid = f_key = f_dis = False
    for j in range(i, end):
        stripped = lns[j].lstrip()
        indent   = lns[j][:-len(stripped)] if stripped else ''
        if stripped.startswith('option ssid'):
            lns[j] = f"{indent}option ssid '{ssid}'\n"
            f_ssid = True
        elif stripped.startswith('option key'):
            lns[j] = f"{indent}option key '{key}'\n"
            f_key = True
        elif stripped.startswith('option disabled'):
            lns[j] = f"{indent}option disabled '{disabled}'\n"
            f_dis = True
    indent = '  '
    if i + 1 < len(lns):
        indent = lns[i + 1][:-len(lns[i + 1].lstrip())] or indent
    if not f_ssid:
        end = _insert_option(lns, i, end, indent, 'ssid', ssid)
    if not f_key:
        end = _insert_option(lns, i, end, indent, 'key',  key)
    if not f_dis:
        _insert_option(lns, i, end, indent, 'disabled', disabled)
    ok, msg = _write_lines(lns)
    if ok:
        os.system('/etc/init.d/network reload >/dev/null 2>&1 &')
    return ok, msg
