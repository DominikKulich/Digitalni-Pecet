# Památník – Digitální pečeť

> Desktopová aplikace pro neviditelné steganografické označení digitálních archiválií.  
> Vyvinuto pro potřeby **Památníku Terezín**. 

---

## Co aplikace dělá

Zaměstnanci památníku vydávají badatelům digitální kopie archiválií (skeny dokumentů, fotografií, map). Aplikace do každého vydaného souboru **neviditelně vloží identitu badatele** — jméno, adresu, číslo smlouvy. Pokud se sken neoprávněně objeví na internetu nebo jinde, aplikace ho zpětně identifikuje. Ke spuštění stačí stáhnout exe soubor!!

### Funkce

| Záložka | Kdo ji používá | Co dělá |
|---|---|---|
| 🔒 **Zabezpečení** | zaměstnanec při výdeji | Vloží ID do skenů a uloží zabezpečené kopie |
| 🔍 **Kontrola úniku** | správce / IT | Přečte ID z podezřelého souboru |

---

## Jak vodoznak funguje

Aplikace používá metodu **blokového průměru** (*Block-Average Watermarking*):

1. Obrázek se rozdělí na mřížku bloků 32 × 32 px
2. Každý bit ID se zakóduje jako **rozdíl průměrného jasu** dvou sousedních bloků
3. JPEG komprese mění hodnoty jednotlivých pixelů, ale průměr celého bloku zachovává

### Co vodoznak přežije

| Operace | Výsledek |
|---|---|
| Konverze TIFF → JPG | ✅ přežije |
| 5× opakované uložení jako JPEG (q = 80) | ✅ přežije |
| JPEG kvalita 50–95 | ✅ přežije |
| Mírná úprava jasu / kontrastu | ✅ přežije |
| Ořez > 25 % plochy | ⚠️ nemusí přežít |
| Zmenšení na < 50 % rozlišení | ⚠️ nemusí přežít |
| Agresivní komprese (JPEG q < 40) | ❌ nepřežije |

---

## Instalace

### Požadavky
- Python 3.9 nebo novější
- Windows / macOS / Linux

### Závislosti

```bash
pip install customtkinter pillow numpy piexif
```

### Spuštění

```bash
python archival_watermark_v4.py
```

---

## Sestavení EXE (Windows)

1. Ulož `archival_watermark_v4.py`, `icon.ico` a `build.bat` do jedné složky
2. Spusť `build.bat` dvojklikem
3. Výsledek: `dist\Pamatnik_Digitalni_Pecet.exe`

> **Poznámka:** Windows Defender může EXE označit jako podezřelé. Klikni „Další informace" → „Přesto spustit".

---

## Struktura projektu

```
📁 projekt
├── archival_watermark_v4.py   # hlavní aplikace
├── icon.ico                   # ikonka aplikace
├── build.bat                  # skript pro sestavení EXE (Windows)
└── README.md
```

---

## Technické detaily

### Steganografický engine — tři vrstvy ochrany

| Vrstva | Metoda | Odolnost vůči JPEG |
|---|---|---|
| 1. Blokový průměr | rozdíl průměrů bloků 32×32 px | ✅ vysoká |
| 2. LSB záloha | nejméně významný bit červeného kanálu | ❌ pouze PNG/TIFF |
| 3. Metadata | EXIF ImageDescription / TIFF UserComment | ⚠️ závisí na nástroji |

Dekódování zkouší metody v pořadí: **blokový průměr → LSB → TIFF tag → EXIF**.

### Klíčové parametry

```python
BLOCK    = 32   # velikost bloku v pixelech
STRENGTH = 12   # síla vložení (rozdíl průměrů)
MAX_ID   = 128  # maximální délka ID v bajtech
```

### Formáty výstupu

| Vstup | Výstup | Poznámka |
|---|---|---|
| `.tiff` / `.tif` | `.tiff` (LZW) | bezztrátový |
| `.png` | `.png` | bezztrátový |
| `.jpg` / `.jpeg` | `.png` | automatická konverze — JPEG by zničil LSB zálohu |

---

## Omezení

- Vodoznak je **skrytý, ale ne šifrovaný** — kdokoli s touto aplikací ho může přečíst
- Slouží k **interní identifikaci**, ne jako kryptografický důkaz u soudu
- Pro právní účely kombinujte s podepsanou smlouvou badatele a logem výdeje
- Vše probíhá **lokálně** — žádná data se neodesílají na server

---

## Autor

**Dominik Kulich** — [www.dominikkulich.cz](https://www.dominikkulich.cz)

## Licence

MIT License — viz níže.

```
Copyright (c) 2026 Dominik Kulich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
```
