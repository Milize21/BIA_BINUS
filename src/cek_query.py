"""
cek_query.py -- periksa apakah anggapan di balik query scrape.py masih berlaku.

    python src/cek_query.py
    python src/cek_query.py --hari 2024-10-20

Query di scrape.py bertumpu pada dua anggapan tentang perilaku pencarian X.
Dua-duanya PERNAH SALAH dan dua-duanya gagal secara diam -- X menjawab "No
results", bukan error, jadi panen bisa berjalan berjam-jam dan berakhir dengan
berkas kosong tanpa ada yang curiga.

    1. `lang:id` TIDAK BOLEH dipakai bersama since:/until:. Gabungan itu selalu
       mengembalikan nol, walaupun query yang sama tanpa lang:id berisi.

    2. `until:D` itu INKLUSIF dan mengikuti zona waktu akun, jadi
       since:D until:D = tepat satu hari penuh menurut zona akun tersebut.

X bisa mengubah perilakunya kapan saja tanpa pengumuman. Jalankan skrip ini
kalau panen tiba-tiba nol, atau sebelum panen besar supaya tidak membuang
waktu berjam-jam. Skrip ini TIDAK menulis apa pun ke data/.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scrape import (  # noqa: E402
    SEL_KARTU,
    baca_kartu,
    buat_driver,
    muat_sesi,
    sudah_login,
    tidur,
)
from selenium.webdriver.common.by import By  # noqa: E402

# Kata umum yang pasti ramai di sekitar pelantikan. Sengaja bukan keyword asli
# proyek: yang diuji perilaku OPERATOR-nya, bukan seberapa populer keyword kita.
KATA = "prabowo"


def panen_cepat(driver, query: str, gulir: int = 8) -> dict[str, str]:
    """Kumpulkan {id: tanggal} dari satu query. Secukupnya saja untuk menilai."""
    driver.get(f"https://x.com/search?q={quote(query)}&src=typed_query&f=live")
    tidur(4.0, 6.0)
    lihat: dict[str, str] = {}
    for _ in range(gulir):
        for kartu in driver.find_elements(By.CSS_SELECTOR, SEL_KARTU):
            baris = baca_kartu(kartu, utc=False)
            if baris:
                lihat[baris["id"]] = baris["tanggal"]
        driver.execute_script("window.scrollBy(0, arguments[0]);", random.randint(800, 1200))
        tidur(1.5, 2.8)
    return lihat


def main() -> None:
    p = argparse.ArgumentParser(description="Periksa anggapan query scrape.py.")
    p.add_argument("--hari", default="2024-10-20", help="tanggal uji, YYYY-MM-DD")
    args = p.parse_args()
    try:
        hari = date.fromisoformat(args.hari)
    except ValueError:
        raise SystemExit("Format tanggal harus YYYY-MM-DD")

    driver = buat_driver(headless=True)
    lolos = True
    try:
        if not muat_sesi(driver):
            raise SystemExit("Belum ada sesi. Jalankan: python src/scrape.py --login")
        if not sudah_login(driver):
            raise SystemExit("Sesi kedaluwarsa. Jalankan: python src/scrape.py --login")

        print(f"\n  Menguji dengan kata '{KATA}' pada {hari:%d %b %Y}\n")

        # --- Anggapan 1: lang:id mematikan query bertanggal -----------------
        tanpa = panen_cepat(driver, f"{KATA} since:{hari} until:{hari}")
        dengan = panen_cepat(driver, f"{KATA} lang:id since:{hari} until:{hari}")
        print("  [1] lang:id digabung since:/until:")
        print(f"      tanpa lang:id : {len(tanpa):>4} tweet")
        print(f"      pakai lang:id : {len(dengan):>4} tweet")
        if tanpa and not dengan:
            print("      -> SESUAI. Jangan pakai lang:id. scrape.py sudah benar.\n")
        elif dengan and tanpa:
            lolos = False
            print("      -> BERUBAH! lang:id sekarang berfungsi. Boleh dipertimbangkan")
            print("         lagi di panen_sehari(), tapi ukur dulu apakah hasilnya")
            print("         lebih bersih atau malah lebih sedikit.\n")
        else:
            lolos = False
            print("      -> TIDAK BISA DISIMPULKAN. Dua-duanya nol -- kemungkinan")
            print("         kena limit, atau hari itu memang sepi. Coba --hari lain.\n")

        # --- Anggapan 2: until:D inklusif, satu hari penuh ------------------
        print("  [2] since:D until:D = satu hari penuh?")
        if not tanpa:
            lolos = False
            print("      -> dilewati, panen pertama kosong.\n")
        else:
            per_hari = Counter(t[:10] for t in tanpa.values())
            waktu = sorted(tanpa.values())
            print(f"      {len(tanpa)} tweet: {waktu[0]}  s/d  {waktu[-1]}")
            for h, n in sorted(per_hari.items()):
                tanda = "  <- diminta" if h == f"{hari}" else "  <- DI LUAR"
                print(f"        {h}: {n:>4}{tanda}")
            asing = {h for h in per_hari if h != f"{hari}"}
            if asing:
                lolos = False
                print("      -> BERUBAH! Ada tanggal di luar yang diminta. Batas")
                print("         harinya bergeser -- periksa zona waktu akun.\n")
            else:
                print("      -> SESUAI. Batas harinya rapi.\n")

        print("  " + "-" * 62)
        if lolos:
            print("  SEMUA ANGGAPAN MASIH BERLAKU. scrape.py aman dijalankan.")
        else:
            print("  ADA YANG BERUBAH. Baca catatan di panen_sehari() sebelum panen")
            print("  besar -- kalau diabaikan, hasilnya berkas kosong atau timpang.")
        print("  " + "-" * 62 + "\n")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
