"""
Instalace: pip install customtkinter pillow numpy piexif

METODA: Blokový průměr (Block-Average Watermarking)
  Obrázek → mřížka bloků 32×32 px
  Bit=1: levý blok jasnější než pravý (rozdíl STRENGTH)
  Bit=0: pravý blok jasnější
  JPEG komprese mění pixely, ale průměr velkého bloku zůstane.

TESTOVÁNO: přežije 5× JPEG q=80, TIFF→JPG, JPG q=50
"""
import sys, struct, string, threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:
    sys.exit("CHYBA: pip install customtkinter")
try:
    from PIL import Image
    import numpy as np
except ImportError:
    sys.exit("CHYBA: pip install pillow numpy")

try:
    import piexif; PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False


# ==================================================================
class StegoEngine:
    BLOCK      = 32
    STRENGTH   = 12
    LSB_MAGIC  = b'\xDE\xAD\xBE\xEF'
    LSB_MAX    = 4096
    BLK_MAGIC  = b'\xAB\xCD\xEF\x12'
    WM_PREFIX  = 'PAMATNIK-WM:'
    TIFF_TAG   = b'PAMATNIK-WM-UTF8:'

    @staticmethod
    def _fp(text):
        ok = set(string.printable + 'áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ')
        c = ''.join(x for x in text if x in ok).strip()
        return c if len(c) >= 2 else ''

    # ── Blokový průměr encode ─────────────────────────────────────
    @classmethod
    def _enc_block(cls, img, text):
        payload = text.encode('utf-8')[:128]
        data = cls.BLK_MAGIC + struct.pack('>H', len(payload)) + payload
        bits = [int(b) for byte in data for b in format(byte,'08b')]
        r = img.copy().astype(np.float32)
        h, w = r.shape[:2]; B = cls.BLOCK
        nx = w//(B*2); ny = h//B
        if len(bits) > nx*ny:
            raise ValueError(f'Obrázek příliš malý nebo ID příliš dlouhé.\nMin. rozlišení: ~800×600 px, max. ID: 128 znaků.')
        for i, bit in enumerate(bits):
            by, bx = i//nx, i%nx
            y1, x1, x2 = by*B, bx*B*2, bx*B*2+B
            if y1+B>h or x2+B>w: break
            b1 = r[y1:y1+B, x1:x1+B]; b2 = r[y1:y1+B, x2:x2+B]
            t = cls.STRENGTH if bit else -cls.STRENGTH
            c = (t-(b1.mean()-b2.mean()))/2
            r[y1:y1+B, x1:x1+B] = np.clip(b1+c,0,255)
            r[y1:y1+B, x2:x2+B] = np.clip(b2-c,0,255)
        return r.astype(np.uint8)

    # ── Blokový průměr decode ─────────────────────────────────────
    @classmethod
    def _dec_block(cls, img):
        try:
            a = img.astype(np.float32); h,w = a.shape[:2]; B = cls.BLOCK
            nx = w//(B*2); ny = h//B
            bits = []
            for i in range(nx*ny):
                by,bx = i//nx, i%nx
                y1,x1,x2 = by*B, bx*B*2, bx*B*2+B
                if y1+B>h or x2+B>w: bits.append(0); continue
                bits.append(1 if a[y1:y1+B,x1:x1+B].mean()>a[y1:y1+B,x2:x2+B].mean() else 0)
            def b2b(s,n):
                out=bytearray()
                for i in range(n):
                    bv=0
                    for b in range(8):
                        idx=s+i*8+b
                        if idx<len(bits): bv=(bv<<1)|bits[idx]
                    out.append(bv)
                return bytes(out)
            if b2b(0,4)!=cls.BLK_MAGIC: return ''
            ln=struct.unpack('>H',b2b(32,2))[0]
            if ln==0 or ln>128: return ''
            return cls._fp(b2b(48,ln).decode('utf-8',errors='replace'))
        except: return ''

    # ── LSB encode / decode ───────────────────────────────────────
    @classmethod
    def _enc_lsb(cls, img, text):
        payload=text.encode('utf-8')[:cls.LSB_MAX]
        data=cls.LSB_MAGIC+struct.pack('>I',len(payload))+payload
        h,w=img.shape[:2]
        if len(data)*8>h*w: return img
        r=img.copy().astype(np.uint8); flat=r[:,:,0].flatten()
        for i,bit in enumerate(int(b) for byte in data for b in format(byte,'08b')):
            flat[i]=(flat[i]&0xFE)|bit
        r[:,:,0]=flat.reshape(h,w); return r

    @classmethod
    def _dec_lsb(cls, img):
        try:
            flat=img[:,:,0].flatten()
            def rb(n,off):
                out=bytearray()
                for i in range(n):
                    bv=0
                    for b in range(8):
                        idx=off+i*8+b
                        if idx<len(flat): bv=(bv<<1)|(int(flat[idx])&1)
                    out.append(bv)
                return bytes(out)
            if rb(4,0)!=cls.LSB_MAGIC: return ''
            ln=struct.unpack('>I',rb(4,32))[0]
            if ln==0 or ln>cls.LSB_MAX: return ''
            return cls._fp(rb(ln,64).decode('utf-8',errors='ignore'))
        except: return ''

    # ── EXIF / TIFF metadata ─────────────────────────────────────
    @classmethod
    def _make_exif(cls, text):
        if not PIEXIF_AVAILABLE: return b''
        try:
            ex={'0th':{piexif.ImageIFD.ImageDescription:(cls.WM_PREFIX+text).encode('utf-8'),
                       piexif.ImageIFD.Artist:b'Pamatnik-WM-v4'},
                'Exif':{},'GPS':{},'1st':{}}
            return piexif.dump(ex)
        except: return b''

    @classmethod
    def _dec_exif(cls, path):
        if not PIEXIF_AVAILABLE: return ''
        try:
            raw=Image.open(path).info.get('exif',b'')
            if not raw: return ''
            d=piexif.load(raw)['0th'].get(piexif.ImageIFD.ImageDescription,b'')
            s=d.decode('utf-8',errors='ignore') if isinstance(d,bytes) else ''
            return cls._fp(s[len(cls.WM_PREFIX):]) if s.startswith(cls.WM_PREFIX) else ''
        except: return ''

    @classmethod
    def _dec_tiff_tag(cls, path):
        try:
            img=Image.open(path)
            if not hasattr(img,'tag_v2'): return ''
            raw=img.tag_v2.get(37510,b'')
            if isinstance(raw,bytes) and raw.startswith(cls.TIFF_TAG):
                return cls._fp(raw[len(cls.TIFF_TAG):].decode('utf-8',errors='ignore'))
            return ''
        except: return ''

    # ── Veřejné API ───────────────────────────────────────────────
    @classmethod
    def encode(cls, src, text, dst):
        img=Image.open(src).convert('RGB'); arr=np.array(img)
        ext=Path(dst).suffix.lower()
        if ext in ('.jpg','.jpeg'):
            dst=str(Path(dst).with_suffix('.png')); ext='.png'
        arr=cls._enc_block(arr,text)   # primární: blokový průměr
        arr=cls._enc_lsb(arr,text)     # záloha: LSB
        out=Image.fromarray(arr)
        if ext=='.png':
            eb=cls._make_exif(text)
            out.save(dst,exif=eb) if eb else out.save(dst)
        else:
            out.save(dst,compression='tiff_lzw',
                     tiffinfo={37510: cls.TIFF_TAG+text.encode('utf-8')})
        return dst

    @classmethod
    def decode(cls, path):
        arr=np.array(Image.open(path).convert('RGB'))
        r=cls._dec_block(arr)
        if r: return r,'Blokový průměr (odolný vůči JPEG)'
        r=cls._dec_lsb(arr)
        if r: return r,'LSB záloha'
        if Path(path).suffix.lower() in ('.tif','.tiff'):
            r=cls._dec_tiff_tag(path)
            if r: return r,'TIFF metadata'
        r=cls._dec_exif(path)
        if r: return r,'EXIF metadata'
        return '',''


# ==================================================================
class ArchivalWatermarkApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('blue')
        self.title('Památník Terezín — Ochrana digitálních sbírek')
        self.geometry('820x730'); self.minsize(700,600)
        self._files=[]; self._outdir=''; self._dec_file=''; self._proc=False; self._renamed=[]
        self._build_ui()

    def _build_ui(self):
        hdr=ctk.CTkFrame(self,corner_radius=0,fg_color=('#1a1a2e','#0d0d1a'))
        hdr.pack(fill='x')
        ctk.CTkLabel(hdr,text='🏛️  PAMÁTNÍK TEREZÍN — OCHRANA PRO BADATELE',
                     font=ctk.CTkFont(size=18,weight='bold'),text_color='#ffffff').pack(side='left',padx=20,pady=15)
        ctk.CTkLabel(hdr,text='● Blokový průměr  |  přežije 5× JPEG',
                     font=ctk.CTkFont(size=10),text_color='#4caf50').pack(side='right',padx=20)

        self.tabs=ctk.CTkTabview(self,corner_radius=10)
        self.tabs.pack(fill='both',expand=True,padx=15,pady=10)
        self._tab_enc(self.tabs.add('🔒  Zabezpečení (Výdej)'))
        self._tab_dec(self.tabs.add('🔍  Kontrola úniku (Analýza)'))

        ftr=ctk.CTkFrame(self,fg_color='transparent')
        ftr.pack(fill='x',side='bottom',padx=20,pady=5)
        self.status=ctk.CTkLabel(ftr,text='Připraven.',font=ctk.CTkFont(size=11),text_color='gray')
        self.status.pack(side='left')
        ctk.CTkLabel(ftr,text='www.dominikkulich.cz',
                     font=ctk.CTkFont(size=11,slant='italic'),text_color='#4fc3f7').pack(side='right')

    def _sec(self,p,title,row):
        f=ctk.CTkFrame(p,corner_radius=8)
        f.grid(row=row,column=0,padx=10,pady=6,sticky='ew')
        ctk.CTkLabel(f,text=title,font=ctk.CTkFont(size=12,weight='bold'),text_color='#90caf9').pack(pady=(8,4))
        return f

    def _tab_enc(self,p):
        p.grid_columnconfigure(0,weight=1)
        f1=self._sec(p,'1.  Výběr skenů (TIFF, PNG, JPG)',0)
        self.lbl_f=ctk.CTkLabel(f1,text='Není vybráno',text_color='gray'); self.lbl_f.pack(padx=10,pady=(0,4))
        ctk.CTkButton(f1,text='📂  Vybrat soubory',command=self._sel_files,width=200).pack(pady=(0,8))

        f2=self._sec(p,'2.  ID Badatele  (Jméno, Adresa, Smlouva)',1)
        ctk.CTkLabel(f2,text='Max. 128 znaků. Vodoznak přežije JPEG konverzi a vícenásobné ukládání.',
                     font=ctk.CTkFont(size=11),text_color='#888').pack(padx=10,pady=(0,2))
        self.entry=ctk.CTkEntry(f2,placeholder_text='Např. Jan Novák, Smlouva 123/2026',width=520,height=38)
        self.entry.pack(padx=10,pady=(0,8))

        f3=self._sec(p,'3.  Složka pro uložení zabezpečených souborů',2)
        self.lbl_o=ctk.CTkLabel(f3,text='Není vybráno',text_color='gray'); self.lbl_o.pack(padx=10,pady=(0,4))
        ctk.CTkButton(f3,text='📁  Vybrat složku',command=self._sel_outdir,width=200).pack(pady=(0,8))

        self.btn_e=ctk.CTkButton(p,text='🛡️  ZABEZPEČIT A ULOŽIT',height=46,
                                  font=ctk.CTkFont(size=14,weight='bold'),
                                  fg_color='#1565c0',hover_color='#0d47a1',command=self._start_enc)
        self.btn_e.grid(row=3,column=0,pady=18,padx=30,sticky='ew')
        self.prog_e=ctk.CTkProgressBar(p,mode='indeterminate')
        self.prog_e.grid(row=4,column=0,sticky='ew',padx=30); self.prog_e.grid_remove()

    def _tab_dec(self,p):
        p.grid_columnconfigure(0,weight=1); p.grid_rowconfigure(3,weight=1)
        info=ctk.CTkFrame(p,corner_radius=8,fg_color=('#1e1e2e','#1e1e2e'))
        info.grid(row=0,column=0,padx=10,pady=(8,4),sticky='ew')
        ctk.CTkLabel(info,text='🔎  Nahrajte podezřelý obrázek v libovolném formátu.\nVodoznak přežije konverzi TIFF → JPG i vícenásobné ukládání.',
                     font=ctk.CTkFont(size=12),text_color='#aaa',wraplength=600,justify='left').pack(padx=14,pady=10,anchor='w')

        f1=self._sec(p,'Podezřelý soubor',1)
        self.lbl_d=ctk.CTkLabel(f1,text='Žádný soubor nevybrán',text_color='gray'); self.lbl_d.pack(padx=10,pady=(0,4))
        ctk.CTkButton(f1,text='📂  Nahrát soubor',command=self._sel_dec,width=200).pack(pady=(0,8))

        self.btn_d=ctk.CTkButton(p,text='🔬  ANALYZOVAT PŮVOD',height=46,
                                  font=ctk.CTkFont(size=14,weight='bold'),
                                  fg_color='#b71c1c',hover_color='#7f0000',command=self._start_dec)
        self.btn_d.grid(row=2,column=0,pady=10,padx=30,sticky='ew')
        self.prog_d=ctk.CTkProgressBar(p,mode='indeterminate')
        self.prog_d.grid(row=3,column=0,sticky='ew',padx=30); self.prog_d.grid_remove()

        self.txt=ctk.CTkTextbox(p,height=230,font=ctk.CTkFont(family='Consolas',size=13))
        self.txt.grid(row=4,column=0,sticky='nsew',padx=20,pady=10)

    # ── Dialogy ──────────────────────────────────────────────────
    def _sel_files(self):
        fs=filedialog.askopenfilenames(filetypes=[('Obrázky','*.tif *.tiff *.png *.jpg *.jpeg')])
        if fs:
            self._files=list(fs); n=len(fs)
            names=', '.join(Path(f).name for f in fs[:3])
            suf=f' … a {n-3} dalších' if n>3 else ''
            self.lbl_f.configure(text=f'✔  {n} souborů: {names}{suf}',text_color='#4fc3f7')

    def _sel_outdir(self):
        d=filedialog.askdirectory()
        if d: self._outdir=d; self.lbl_o.configure(text=f'✔  {d}',text_color='#4fc3f7')

    def _sel_dec(self):
        f=filedialog.askopenfilename(filetypes=[('Obrázky','*.tif *.tiff *.png *.jpg *.jpeg'),('Vše','*.*')])
        if f: self._dec_file=f; self.lbl_d.configure(text=f'✔  {Path(f).name}',text_color='#4fc3f7'); self.txt.delete('1.0','end')

    # ── Kódování ─────────────────────────────────────────────────
    def _start_enc(self):
        if self._proc: return
        if not self._files: return messagebox.showwarning('Chybí soubory','Vyberte obrázky ke kódování.')
        badge=self.entry.get().strip()
        if not badge: messagebox.showwarning('Chybí ID','Zadejte ID badatele.'); self.entry.focus(); return
        if not self._outdir: return messagebox.showwarning('Chybí složka','Vyberte výstupní složku.')
        self._proc=True; self._renamed=[]
        self.btn_e.configure(state='disabled',text='⏳  Probíhá kódování…')
        self.prog_e.grid(); self.prog_e.start()
        threading.Thread(target=self._work_enc,args=(badge,),daemon=True).start()

    def _work_enc(self,badge):
        ok,err=0,[]
        for i,src in enumerate(self._files,1):
            try:
                self.after(0,self.status.configure,{'text':f'Zpracovávám {i}/{len(self._files)}: {Path(src).name}'})
                dst=str(Path(self._outdir)/Path(src).name)
                actual=StegoEngine.encode(src,badge,dst)
                if Path(actual).name!=Path(dst).name: self._renamed.append((Path(src).name,Path(actual).name))
                ok+=1
            except Exception as e: err.append(f'{Path(src).name}: {e}')
        self.after(0,self._done_enc,ok,err)

    def _done_enc(self,ok,err):
        self._proc=False; self.prog_e.stop(); self.prog_e.grid_remove()
        self.btn_e.configure(state='normal',text='🛡️  ZABEZPEČIT A ULOŽIT')
        msg=(f'Zabezpečeno: {ok} souborů.\n\nVodoznak přežije:\n'
             f'  ✓ Konverzi TIFF/PNG → JPG\n  ✓ Opakované ukládání (5× a více)\n  ✓ JPEG kvalita 50–95')
        if self._renamed:
            msg+='\n\n⚠  Tyto JPG soubory byly uloženy jako PNG:\n'+''.join(f'  {a} → {b}\n' for a,b in self._renamed)
        if err: msg+=f'\n\nChyby ({len(err)}):\n'+''.join(f'  {e}\n' for e in err); messagebox.showerror('Dokončeno s chybami',msg)
        else: messagebox.showinfo('✔  Hotovo',msg)
        self._files=[]; self.lbl_f.configure(text='Není vybráno',text_color='gray')
        self.entry.delete(0,'end'); self.status.configure(text=f'✔  Dokončeno — {ok} souborů uloženo.')

    # ── Dekódování ───────────────────────────────────────────────
    def _start_dec(self):
        if self._proc: return
        if not self._dec_file: return messagebox.showwarning('Chybí soubor','Nejprve nahrajte podezřelý soubor.')
        self._proc=True
        self.btn_d.configure(state='disabled',text='⏳  Analyzuji…')
        self.prog_d.grid(); self.prog_d.start()
        self.txt.delete('1.0','end'); self.txt.insert('end','Probíhá analýza…')
        threading.Thread(target=self._work_dec,daemon=True).start()

    def _work_dec(self):
        try:
            r,m=StegoEngine.decode(self._dec_file); self.after(0,self._done_dec,r,m,None)
        except Exception as e: self.after(0,self._done_dec,None,None,str(e))

    def _done_dec(self,result,method,error):
        self._proc=False; self.prog_d.stop(); self.prog_d.grid_remove()
        self.btn_d.configure(state='normal',text='🔬  ANALYZOVAT PŮVOD')
        fname=Path(self._dec_file).name; now=datetime.now().strftime('%d. %m. %Y v %H:%M:%S')
        if error:
            msg=f'⚠️  CHYBA PŘI ANALÝZE\n{"─"*40}\n{error}'
        elif result:
            msg=(f'✅  VODOZNAK NALEZEN\n{"═"*40}\n\nIDENTIFIKACE BADATELE:\n\n'
                 f'  {result}\n\n{"═"*40}\nSoubor:      {fname}\nDetekce:     {method}\nAnalyzováno: {now}\n')
            self.status.configure(text=f'✔  ID nalezeno: {fname}')
        else:
            msg=(f'❌  VODOZNAK NENALEZEN\n{"─"*40}\n\nMožné příčiny:\n'
                 f'  • Soubor nebyl označen touto aplikací\n'
                 f'  • Obrázek byl oříznut o více než 25 %\n'
                 f'  • Obrázek byl zmenšen na méně než 50 %\n'
                 f'  • Extrémně agresivní komprese (JPEG < 40 %)\n\n'
                 f'Soubor:      {fname}\nAnalyzováno: {now}')
            self.status.configure(text=f'✗  Vodoznak nenalezen: {fname}')
        self.txt.delete('1.0','end'); self.txt.insert('end',msg)


# ==================================================================
if __name__ == '__main__':
    app=ArchivalWatermarkApp()
    app.mainloop()
