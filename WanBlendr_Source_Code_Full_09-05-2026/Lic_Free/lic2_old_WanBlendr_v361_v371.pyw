from __future__ import annotations
import os
import re
import base64
import hashlib
import datetime as dt
from typing import Optional
import zipfile
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    raise SystemExit("Tkinter is not available in this Python installation.")
SECRET=b"Abd_@_!!_88_22_@Hello_@!0!"
BLOCKSIZE=64
def _hmac_sha256_hex(key: bytes,msg: bytes)->str:
    if len(key)>BLOCKSIZE:
        key=hashlib.sha256(key).digest()
    if len(key)<BLOCKSIZE:
        key=key+b'\x00'*(BLOCKSIZE-len(key))
    o_key_pad=bytes((b^0x5C) for b in key)
    i_key_pad=bytes((b^0x36) for b in key)
    inner=hashlib.sha256(i_key_pad+msg).digest()
    outer=hashlib.sha256(o_key_pad+inner).digest()
    return outer.hex().upper()
def base36_encode(number:int)->str:
    alphabet='0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    if number==0:
        return '0'
    out=[]
    n=number
    while n:
        n,rem=divmod(n,36)
        out.append(alphabet[rem])
    out.reverse()
    return ''.join(out)
def _pad6(s:str)->str:
    return ('000000'+s)[-6:]
def generate_license_key(machine_key:str)->str:
    if not isinstance(machine_key,str) or not machine_key.strip():
        raise ValueError("Invalid Machine value.")
    hm=_hmac_sha256_hex(SECRET,machine_key.strip().encode('utf-8'))
    seed=int(hm,16)
    m,s,MOD=6364136223846793005,1442695040888963407,36**6
    blocks=[]
    for _ in range(6):
        seed=abs(seed*m-s)
        blocks.append(_pad6(base36_encode(seed%MOD)))
    return "-".join(blocks)
def read_text_file(path:str)->str:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")
    with open(path,"rb") as f:
        data=f.read()
    try:
        text=data.decode("utf-8",errors="ignore").strip()
    except Exception:
        text=data.decode("latin1",errors="ignore").strip()
    return text
def b64_decode_str(s:str)->str:
    compact="".join(s.strip().splitlines())
    try:
        decoded=base64.b64decode(compact,validate=True)
        out=decoded.decode("utf-8",errors="ignore").strip()
        return out
    except Exception:
        decoded=base64.b64decode(compact+"===")
        out=decoded.decode("utf-8",errors="ignore").strip()
        return out
def parse_fields_from_text(decoded_text:str)->dict:
    full=decoded_text
    def find_value(labels):
        for label in labels:
            pattern=rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$"
            m=re.search(pattern,full)
            if m:
                return m.group(1).strip()
        return None
    hw=find_value(["HW","Hw","hw"])
    machine=find_value(["Machine","MACHINE","machine"])
    id_=find_value(["ID","Id","id"])
    if not machine:
        raise ValueError("Could not extract Machine from decoded text.")
    return {"HW":hw,"Machine":machine,"ID":id_}
def get_base_dir()->str:
    return os.path.abspath(os.path.dirname(__file__))
def get_db_path()->str:
    return os.path.join(get_base_dir(),"data_base")
def id_exists_in_db(db_path:str,id_value:str)->bool:
    if not id_value:
        return False
    if not os.path.exists(db_path):
        return False
    try:
        with open(db_path,"r",encoding="utf-8",errors="ignore") as f:
            content=f.read()
        pattern=rf"(?m)^\s*ID:\s*{re.escape(id_value)}\s*$"
        return re.search(pattern,content)is not None
    except Exception:
        return False
def append_record_to_db(db_path:str,record_text:str):
    entry=record_text.strip()+"\n-----\n"
    with open(db_path,"a",encoding="utf-8") as f:
        f.write(entry)
def write_individual_license(id_value:str,record_text:str):
    if not id_value:
        return
    safe=re.sub(r'[^A-Za-z0-9._-]+','_',id_value)
    out_path=os.path.join(get_base_dir(),f"{safe}.txt")
    with open(out_path,"w",encoding="utf-8") as f:
        f.write(record_text.strip()+"\n")
ZIP_PASSWORD=b"01_08_2025@!00_99!!"
def read_first_txt_from_zip(zip_path:str,password:bytes=ZIP_PASSWORD)->str:
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"ZIP not found: {zip_path}")
    try:
        with zipfile.ZipFile(zip_path,'r') as zf:
            target_info=None
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.filename.lower().endswith(".txt"):
                    target_info=info
                    break
            if not target_info:
                raise ValueError("No TXT file found inside the ZIP.")
            with zf.open(target_info,'r',pwd=password) as fp:
                raw=fp.read()
            try:
                text=raw.decode("utf-8",errors="ignore").strip()
            except Exception:
                text=raw.decode("latin1",errors="ignore").strip()
            return text
    except RuntimeError as e:
        raise ValueError("Failed to open ZIP: check password.") from e
    except zipfile.BadZipFile as e:
        raise ValueError("Bad or corrupted ZIP file.") from e
def read_b64_source_from_path(path:str)->str:
    lower=path.lower()
    if lower.endswith(".zip"):
        return read_first_txt_from_zip(path,ZIP_PASSWORD)
    else:
        return read_text_file(path)
class LicenseGeneratorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("License Generator")
        self.geometry("760x580")
        self.minsize(700,540)
        try:
            self.call("tk","scaling",1.0)
        except Exception:
            pass
        self.file_path_var=tk.StringVar()
        self.check_var=tk.StringVar(value="—")
        self.hw_var=tk.StringVar(value="")
        self.date_var=tk.StringVar(value=dt.datetime.now().strftime("%Y-%m-%d"))
        self.id_var=tk.StringVar(value="")
        self.key_var=tk.StringVar(value="")
        self._build_ui()
    def _build_ui(self):
        pad=10
        frm_file=ttk.LabelFrame(self,text="License file (Protected ZIP or Base64 TXT)")
        frm_file.pack(fill="x",padx=pad,pady=(pad,5))
        ent=ttk.Entry(frm_file,textvariable=self.file_path_var)
        ent.pack(side="left",fill="x",expand=True,padx=(pad,5),pady=pad)
        ttk.Button(frm_file,text="Choose file…",command=self.on_browse_file).pack(side="left",padx=(0,6),pady=pad)
        ttk.Button(frm_file,text="Extract & Run",command=self.on_process).pack(side="left",padx=(0,pad),pady=pad)
        frm_out=ttk.LabelFrame(self,text="Result")
        frm_out.pack(fill="x",padx=pad,pady=5)
        grid=ttk.Frame(frm_out);grid.pack(fill="x",padx=pad,pady=pad)
        ttk.Label(grid,text="Check:",width=14).grid(row=0,column=0,sticky="w",padx=5,pady=5)
        ttk.Entry(grid,textvariable=self.check_var,state="readonly").grid(row=0,column=1,sticky="we",padx=5,pady=5)
        ttk.Label(grid,text="HW:",width=14).grid(row=1,column=0,sticky="w",padx=5,pady=5)
        ttk.Entry(grid,textvariable=self.hw_var,state="readonly").grid(row=1,column=1,sticky="we",padx=5,pady=5)
        ttk.Label(grid,text="Date:",width=14).grid(row=2,column=0,sticky="w",padx=5,pady=5)
        ttk.Entry(grid,textvariable=self.date_var,state="readonly").grid(row=2,column=1,sticky="we",padx=5,pady=5)
        ttk.Label(grid,text="ID:",width=14).grid(row=3,column=0,sticky="w",padx=5,pady=5)
        ttk.Entry(grid,textvariable=self.id_var,state="readonly").grid(row=3,column=1,sticky="we",padx=5,pady=5)
        ttk.Label(grid,text="Key-License:",width=14).grid(row=4,column=0,sticky="w",padx=5,pady=5)
        ttk.Entry(grid,textvariable=self.key_var,state="readonly").grid(row=4,column=1,sticky="we",padx=5,pady=5)
        grid.columnconfigure(1,weight=1)
        frm_dec=ttk.LabelFrame(self,text="Decoded text (review/copy)")
        frm_dec.pack(fill="both",expand=True,padx=pad,pady=(5,pad))
        self.txt_dec=tk.Text(frm_dec,height=14,wrap="word")
        self.txt_dec.pack(fill="both",expand=True,padx=pad,pady=pad)
        self.txt_dec.configure(state="normal")
        self.txt_dec.insert("1.0","")
        self.txt_dec.configure(state="disabled")
        bottom=ttk.Frame(self);bottom.pack(fill="x",padx=pad,pady=(0,pad))
        ttk.Button(bottom,text="Copy Key",command=self.copy_key_only).pack(side="right",padx=(6,0))
        ttk.Button(bottom,text="Copy All Text",command=self.copy_all_text).pack(side="right",padx=(6,0))
        ttk.Button(bottom,text="Exit",command=self.on_exit).pack(side="right")
    def on_browse_file(self):
        path=filedialog.askopenfilename(title="Choose a protected ZIP or Base64 TXT",filetypes=[("ZIP Archive","*.zip"),("Text","*.txt"),("All Files","*.*")])
        if path:
            self.file_path_var.set(path)
            if path.lower().endswith(".zip"):
                self.on_process()
    def on_process(self):
        self._reset_outputs()
        path=self.file_path_var.get().strip()
        if not path:
            messagebox.showwarning("Warning","Please choose a ZIP or TXT file.")
            return
        try:
            raw_text=read_b64_source_from_path(path)
            decoded=b64_decode_str(raw_text)
            fields=parse_fields_from_text(decoded)
            hw=fields.get("HW") or ""
            machine=fields.get("Machine") or ""
            id_=fields.get("ID") or ""
            key=generate_license_key(machine)
            self.check_var.set("ok")
            self.hw_var.set(hw)
            self.date_var.set(dt.datetime.now().strftime("%Y-%m-%d"))
            self.id_var.set(id_)
            self.key_var.set(key)
            merged_text=self._compose_decoded_block(hw,machine,id_,key)
            self._set_decoded_preview(merged_text)
            db_path=get_db_path()
            if id_ and not id_exists_in_db(db_path,id_):
                append_record_to_db(db_path,merged_text)
            if id_:
                write_individual_license(id_,merged_text)
        except Exception as e:
            self.check_var.set("failed")
            self.key_var.set("")
            messagebox.showerror("Error",str(e))
    def copy_all_text(self):
        content=self.txt_dec.get("1.0","end-1c")
        if not content.strip():
            messagebox.showinfo("Copy","No text to copy.")
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("Copy","All text copied to clipboard.")
    def copy_key_only(self):
        key=(self.key_var.get() or "").strip()
        if not key:
            messagebox.showinfo("Copy","No key to copy.")
            return
        self.clipboard_clear()
        self.clipboard_append(key)
        messagebox.showinfo("Copy","Key copied to clipboard.")
    def on_exit(self):
        self.destroy()
    def _reset_outputs(self):
        self.check_var.set("—")
        self.hw_var.set("")
        self.id_var.set("")
        self.key_var.set("")
        self._set_decoded_preview("")
    def _set_decoded_preview(self,text:str):
        self.txt_dec.configure(state="normal")
        self.txt_dec.delete("1.0","end")
        if text:
            self.txt_dec.insert("1.0",text)
        self.txt_dec.configure(state="disabled")
    def _compose_decoded_block(self,hw:str,machine:str,id_:str,key:str)->str:
        lines=[]
        if hw:lines.append(f"HW: {hw}")
        if machine:lines.append(f"Machine: {machine}")
        if id_:lines.append(f"ID: {id_}")
        if key:lines.append(f"Key-License: {key}")
        lines.append(f"Date: {dt.datetime.now().strftime('%Y-%m-%d')}")
        return "\n".join(lines)
if __name__=="__main__":
    app=LicenseGeneratorApp()
    try:
        app.update_idletasks()
        w=app.winfo_width()
        h=app.winfo_height()
        x=(app.winfo_screenwidth()//2)-(w//2)
        y=(app.winfo_screenheight()//2)-(h//2)
        app.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass
    app.mainloop()
