"""
preprocess.py -- TAHAP 2a: gabung CSV mentah, bersihkan, hasilkan teks_bersih.

INPUT   : data/raw/*.csv                       (hasil scrape.py)
OUTPUT  : data/processed/tweets_clean.csv
          -> tanggal, periode, teks_bersih, teks_asli, likes, retweet, username
          (`sentimen` belum ada -- itu jatahnya labeling.py)

    python src/preprocess.py            # baca semua data/raw/*.csv
    python src/preprocess.py --demo     # baca data/raw/dummy_raw_*.csv saja,
                                        # tulis ke *_demo.csv (tidak menimpa hasil asli)

=== URUTANNYA DISENGAJA ===

Pembersihan murah dikerjakan DULUAN, yang mahal belakangan:

    1-4  parsing & penyaringan baris   (murah)
    5-7  buang duplikat, bot, kepotong (murah, pakai teks hasil bersih-dasar)
    8-10 normalisasi, stopword, stemming (MAHAL -- stemming Sastrawi lambat)

Kalau dibalik, kita membuang waktu men-stem ribuan tweet yang toh nanti dibuang
karena duplikat. Bedanya besar di data asli.

Deduplikasi juga sengaja dilakukan di atas teks hasil bersih-dasar, bukan teks
mentah: dua tweet bot yang cuma beda hashtag di ekornya tidak akan ketahuan
kembar kalau dibandingkan mentah-mentah.

=== TEKS KEPOTONG (PLAN.md bagian 10) ===

X memendekkan tweet panjang jadi "… Show more". Tweet begini DIBUANG, bukan
dipakai, karena separuh kalimatnya hilang -- sentimennya bisa terbalik dan word
cloud jadi timpang. Jumlah yang dibuang dilaporkan di akhir; kalau angkanya
besar, yang harus diperbaiki adalah scrape.py-nya, bukan di sini.

Penandanya dua: kolom `kepotong` dari scrape.py (dibaca dari DOM, pasti) kalau
kolomnya ada, DAN tebakan dari teks lewat RE_KEPOTONG yang selalu jalan. Lihat
langkah 2 di bersihkan() untuk alasan keduanya dipakai bersama.

=== KOLOM `teks_asli` ===

Kolom ini DIBAWA sampai akhir tapi TIDAK masuk 7 kolom kontrak. Gunanya buat
mengutip tweet asli di laporan dan buat validasi manual 100 tweet di labeling.py
-- tidak mungkin memvalidasi sentimen dari teks yang sudah di-stem.
train_model.py yang nanti membuangnya saat menulis dataset_final.csv.
"""

from __future__ import annotations

import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
from Sastrawi.Stemmer.StemmerFactory import StemmerFactory
from Sastrawi.StopWordRemover.StopWordRemoverFactory import StopWordRemoverFactory

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "processed"

HARI_H = date(2024, 10, 20)
MULAI = date(2024, 9, 20)
SELESAI = date(2024, 11, 19)

KOLOM_MENTAH = ["tanggal", "teks", "likes", "retweet", "username"]

MIN_KATA = 3        # tweet yang tersisa < 3 kata dibuang -- tidak berguna untuk analisis
BOT_MIN_TWEET = 20  # akun dengan tweet >= ini DAN
BOT_MAX_RAGAM = 0.30  # ragam teks <= ini dianggap bot/buzzer

# ------------------------------------------------------------------- regex

RE_URL = re.compile(r"https?://\S+|www\.\S+|\b\w+\.(?:com|co|id|ly|me)/\S*", re.I)
RE_MENTION = re.compile(r"@\w+")
RE_HASHTAG = re.compile(r"#(\w+)")          # '#' dibuang, KATANYA dipertahankan
RE_BUKAN_HURUF = re.compile(r"[^a-z\s]")    # emoji, angka, tanda baca sekaligus
RE_SPASI = re.compile(r"\s+")
# Penanda tweet kepotong. Sengaja TIDAK menangkap teks yang cuma berakhir
# "...." dari tanda baca berlebihan -- itu gaya ngetik orang, bukan potongan.
# Aturannya: "…" (satu karakter elipsis, penanda milik X) dihitung berdiri
# sendiri; titik-titik biasa hanya dihitung kalau diikuti "show more".
# Diuji pada data mentah: aturan longgar salah tangkap 511 dari 1.085 tweet.
RE_KEPOTONG = re.compile(
    r"(?:…\s*(?:show\s*more|baca\s*selengkapnya)?"
    r"|\.{2,}\s*(?:show\s*more|baca\s*selengkapnya))\s*$",
    re.I,
)
RE_ANGKA_X = re.compile(r"^([\d.,]+)\s*([km])?$", re.I)

# Kamus normalisasi kata gaul -> baku. Dikerjakan SEBELUM stopword removal,
# supaya "yg"/"gak" bisa dikenali sebagai stopword dan ikut terbuang.
GAUL = {
    "yg": "yang", "dgn": "dengan", "dg": "dengan", "utk": "untuk", "tdk": "tidak",
    "gak": "tidak", "ga": "tidak", "nggak": "tidak", "ngga": "tidak", "gk": "tidak",
    "bgt": "banget", "bngt": "banget", "aja": "saja", "udah": "sudah",
    "sdh": "sudah", "blm": "belum", "blom": "belum", "krn": "karena",
    "karna": "karena", "gmn": "bagaimana", "gimana": "bagaimana", "org": "orang",
    "jd": "jadi", "sm": "sama", "tp": "tapi", "klo": "kalau", "kalo": "kalau",
    "gue": "saya", "gw": "saya", "gua": "saya", "lu": "kamu", "lo": "kamu",
    "elu": "kamu", "kalian": "kamu", "bkn": "bukan", "dr": "dari", "dlm": "dalam",
    "pd": "pada", "sy": "saya", "kpd": "kepada", "spt": "seperti",
    "sprt": "seperti", "hrs": "harus", "bs": "bisa", "bsa": "bisa",
    "skrg": "sekarang", "skrng": "sekarang", "bnyk": "banyak", "byk": "banyak",
    "smua": "semua", "sm2": "sama sama", "trs": "terus", "gt": "begitu",
    "gitu": "begitu", "gini": "begini", "emg": "memang", "emang": "memang",
    "knp": "kenapa", "napa": "kenapa", "sih": "", "nih": "", "deh": "",
    "kok": "", "dong": "", "yaa": "ya", "yah": "ya", "wkwk": "", "wkwkwk": "",
    "hrg": "harga", "pmrintah": "pemerintah", "pemrintah": "pemerintah",
    "prabowo": "prabowo", "jkw": "jokowi", "presdn": "presiden",
}


# ------------------------------------------------------------------ helper

def tentukan_periode(t: date) -> str:
    """Satu-satunya definisi periode. Samakan dengan make_dummy.py & PLAN.md bagian 3."""
    if t < HARI_H:
        return "sebelum"
    if t == HARI_H:
        return "hari-h"
    return "sesudah"


def parse_angka(nilai) -> int:
    """
    X menampilkan '1.2K' / '3,456' / kosong. Ubah jadi integer.

    '1.2K' -> 1200, '3,456' -> 3456, '' / 'NaN' -> 0.
    """
    if pd.isna(nilai):
        return 0
    s = str(nilai).strip().replace(" ", "")
    if not s:
        return 0
    m = RE_ANGKA_X.match(s)
    if not m:
        return 0
    angka, satuan = m.group(1), (m.group(2) or "").lower()
    try:
        if satuan in ("k", "m"):
            x = float(angka.replace(",", ""))
            return int(x * (1_000 if satuan == "k" else 1_000_000))
        return int(float(angka.replace(",", "")))
    except ValueError:
        return 0


def bersih_dasar(teks: str) -> str:
    """
    Pembersihan murah: casefolding + buang URL/mention/simbol.

    Hashtag: '#' dibuang tapi KATANYA dipertahankan -- '#PelantikanPresiden'
    jadi 'pelantikanpresiden'. Hashtag sering justru kata kunci paling padat
    makna, sayang kalau ikut dibuang.
    """
    t = str(teks).lower()
    t = RE_URL.sub(" ", t)
    t = RE_MENTION.sub(" ", t)
    t = RE_HASHTAG.sub(r"\1", t)
    t = RE_BUKAN_HURUF.sub(" ", t)
    return RE_SPASI.sub(" ", t).strip()


def normalisasi_gaul(teks: str) -> str:
    return " ".join(GAUL.get(w, w) for w in teks.split()).strip()


def buat_pembersih_lanjut(pakai_stemming: bool = True):
    """
    Siapkan stopword remover + (opsional) stemmer Sastrawi.

    Stemming di-cache PER KATA. Tanpa ini, kata seperti 'pelantikan' di-stem
    ulang puluhan ribu kali. Di data asli bedanya bisa belasan menit.

    === KENAPA STEMMING BISA DIMATIKAN (--no-stem) ===

    Stemming menyatukan 'mendukung/dukungan/didukung/pendukung' jadi 'dukung'.
    Bagus untuk model (fitur lebih sedikit, generalisasi lebih baik) dan memang
    praktik standar di paper sentimen Bahasa Indonesia.

    Tapi ada harganya di WORD CLOUD: 'pelantikan' jadi 'lantik', 'warisan' jadi
    'waris', 'jabatan' jadi 'jabat'. Masih terbaca, tapi kurang enak dipandang
    di slide.

    Default: MENYALA, karena itu yang lazim dan paling gampang dipertahankan di
    laporan. Kalau tim memutuskan sebaliknya, catat keputusannya di PLAN.md --
    jangan diam-diam, karena pilihan ini kelihatan langsung di word cloud.
    """
    stopword = set(StopWordRemoverFactory().get_stop_words())
    stemmer = StemmerFactory().create_stemmer() if pakai_stemming else None
    cache: dict[str, str] = {}

    def proses(teks: str) -> str:
        keluar = []
        for w in teks.split():
            if w in stopword or len(w) <= 2:
                continue
            if stemmer is None:
                keluar.append(w)
                continue
            akar = cache.get(w)
            if akar is None:
                akar = stemmer.stem(w)
                cache[w] = akar
            if akar and akar not in stopword and len(akar) > 2:
                keluar.append(akar)
        return " ".join(keluar)

    return proses, cache


def baca_mentah(demo: bool) -> pd.DataFrame:
    pola = "dummy_raw_*.csv" if demo else "*.csv"
    berkas = sorted(RAW_DIR.glob(pola))
    if not berkas:
        raise SystemExit(
            f"Tidak ada berkas '{pola}' di {RAW_DIR}.\n"
            + ("Bikin dulu: python src/make_dummy_raw.py" if demo
               else "Jalankan scrape.py dulu, atau pakai --demo untuk data uji.")
        )

    bagian = []
    for b in berkas:
        d = pd.read_csv(b, dtype=str)
        kurang = [k for k in KOLOM_MENTAH if k not in d.columns]
        if kurang:
            raise SystemExit(
                f"{b.name} tidak punya kolom: {', '.join(kurang)}\n"
                f"Kolom yang ada: {', '.join(d.columns)}\n"
                f"scrape.py wajib menghasilkan: {', '.join(KOLOM_MENTAH)}"
            )
        d["_sumber"] = b.name
        bagian.append(d)
        print(f"  baca {b.name:<44} {len(d):>7,} baris")
    return pd.concat(bagian, ignore_index=True)


# ---------------------------------------------------------------------- main

def main() -> None:
    demo = "--demo" in sys.argv
    pakai_stemming = "--no-stem" not in sys.argv
    akhiran = "_demo" if demo else ""
    out_path = OUT_DIR / f"tweets_clean{akhiran}.csv"

    if demo:
        print("MODE DEMO -- baca data/raw/dummy_raw_*.csv, tulis ke tweets_clean_demo.csv")
    print()

    t0 = time.time()
    df = baca_mentah(demo)
    jejak = [("baris mentah dibaca", len(df), "")]

    # --- 1. teks kosong -------------------------------------------------
    n = len(df)
    df = df[df["teks"].notna() & (df["teks"].astype(str).str.strip() != "")]
    jejak.append(("teks kosong dibuang", n - len(df), ""))

    # --- 2. tweet kepotong ("… Show more") ------------------------------
    #
    # Dua penanda, dipakai berbarengan karena masing-masing punya lubang:
    #
    #   kolom `kepotong`  dari scrape.py, dibaca langsung dari DOM (ada atau
    #                     tidaknya tombol "Show more"). Ini penanda yang PASTI,
    #                     tapi cuma ada di CSV hasil scrape.py.
    #   RE_KEPOTONG       menebak dari teksnya. Satu-satunya yang bisa dipakai
    #                     untuk data dummy dan CSV dari sumber lain.
    #
    # Regex sendirian tidak cukup: kalau "…" ternyata berada di elemen tombol
    # dan bukan di dalam teks tweet, teks yang terpotong akan lolos seolah utuh
    # -- persis kesalahan yang paling mahal di sini, karena separuh kalimat yang
    # hilang bisa membalik sentimennya tanpa ada yang sadar.
    n = len(df)
    kepotong = df["teks"].astype(str).str.contains(RE_KEPOTONG, regex=True)
    if "kepotong" in df.columns:
        kepotong |= df["kepotong"].astype(str).str.strip() == "1"
    df = df[~kepotong]
    jejak.append(("tweet kepotong dibuang", n - len(df), "PLAN.md bagian 10"))

    # --- 3. tanggal ------------------------------------------------------
    df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")
    n = len(df)
    df = df[df["tanggal"].notna()]
    jejak.append(("tanggal tidak terbaca dibuang", n - len(df), ""))

    n = len(df)
    dalam = (df["tanggal"].dt.date >= MULAI) & (df["tanggal"].dt.date <= SELESAI)
    df = df[dalam]
    jejak.append(("tanggal di luar rentang dibuang", n - len(df),
                  f"{MULAI:%d %b} - {SELESAI:%d %b %Y}"))

    # --- 4. angka --------------------------------------------------------
    df["likes"] = df["likes"].map(parse_angka)
    df["retweet"] = df["retweet"].map(parse_angka)

    # --- 5. bersih dasar (dipakai untuk dedup & deteksi bot) -------------
    df["_dasar"] = df["teks"].map(bersih_dasar)
    n = len(df)
    df = df[df["_dasar"].str.split().str.len() >= MIN_KATA]
    jejak.append((f"teks < {MIN_KATA} kata dibuang", n - len(df), "URL/emoji saja"))

    # --- 6. akun bot / buzzer -- WAJIB SEBELUM DEDUPLIKASI --------------
    #
    # Urutan di sini pernah salah dan pelajarannya mahal: kalau deduplikasi
    # jalan duluan, tiap akun buzzer menyusut jadi segelintir baris unik,
    # jumlahnya jatuh di bawah ambang, dan filter bot menangkap NOL akun --
    # padahal buzzernya ada. Tanda tangan seorang buzzer justru terletak pada
    # BANYAKNYA posting yang nyaris sama; dedup menghapus bukti itu.
    statistik = df.groupby("username")["_dasar"].agg(["size", "nunique"])
    statistik["ragam"] = statistik["nunique"] / statistik["size"]
    bot = statistik[(statistik["size"] >= BOT_MIN_TWEET) & (statistik["ragam"] <= BOT_MAX_RAGAM)]
    n = len(df)
    df = df[~df["username"].isin(bot.index)]
    jejak.append((f"tweet dari {len(bot)} akun bot/buzzer", n - len(df),
                  f">={BOT_MIN_TWEET} tweet, ragam<={BOT_MAX_RAGAM:.0%}"))
    if len(bot):
        print(f"\n  Akun ditandai bot: {', '.join(list(bot.index)[:8])}"
              + (" ..." if len(bot) > 8 else ""))

    # --- 7. duplikat -----------------------------------------------------
    n = len(df)
    df = df.drop_duplicates(subset=["username", "_dasar"])
    jejak.append(("duplikat (akun + teks sama)", n - len(df), "repost sendiri"))

    n = len(df)
    df = df.drop_duplicates(subset=["_dasar"])
    jejak.append(("duplikat teks lintas akun", n - len(df), "copy-paste"))

    # --- 8-10. normalisasi -> stopword -> stemming (MAHAL) ---------------
    langkah = "stopword" + (" + stemming" if pakai_stemming else " (stemming DIMATIKAN)")
    print(f"\n  Normalisasi + {langkah} atas {len(df):,} tweet ...")
    t1 = time.time()
    proses_lanjut, cache = buat_pembersih_lanjut(pakai_stemming)
    df["teks_bersih"] = df["_dasar"].map(normalisasi_gaul).map(proses_lanjut)
    print(f"  selesai dalam {time.time() - t1:.1f} detik "
          + (f"({len(cache):,} kata unik di-stem, sisanya ambil dari cache)"
             if pakai_stemming else "(tanpa stemming)"))

    n = len(df)
    df = df[df["teks_bersih"].str.split().str.len() >= MIN_KATA]
    jejak.append((f"< {MIN_KATA} kata setelah stopword+stemming", n - len(df),
                  "isinya stopword semua"))

    if pakai_stemming:
        print("\n  CATATAN: stemming menyala, jadi word cloud nanti menampilkan kata")
        print("  DASAR -- 'pelantikan' jadi 'lantik', 'jabatan' jadi 'jabat'. Kalau")
        print("  tim mau bentuk aslinya di word cloud, jalankan dengan --no-stem")
        print("  dan catat keputusannya di PLAN.md.")

    # --- selesai ---------------------------------------------------------
    df["periode"] = df["tanggal"].dt.date.map(tentukan_periode)
    kolom = ["tanggal", "periode", "teks_bersih", "teks", "likes", "retweet", "username"]
    # "_kunci" hanya ada di data uji (make_dummy_raw.py) -- diteruskan apa adanya
    # supaya labeling.py bisa mengukur dirinya sendiri. Di data asli kolom ini
    # tidak pernah ada, jadi baris ini tidak berpengaruh apa-apa.
    if "_kunci" in df.columns:
        kolom.append("_kunci")
    hasil = df[kolom].rename(columns={"teks": "teks_asli"}).sort_values("tanggal")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    hasil.to_csv(out_path, index=False, encoding="utf-8")

    # --- jejak pembersihan (salin ini ke bagian Methodology laporan) -----
    print()
    print("  JEJAK PEMBERSIHAN")
    print("  " + "-" * 76)
    print("  | %-42s | %8s | %-16s |" % ("Tahap", "Baris", "Catatan"))
    print("  |%s|%s|%s|" % ("-" * 44, "-" * 10, "-" * 18))
    for nama, jumlah, catatan in jejak:
        tanda = "" if nama.startswith("baris mentah") else "-"
        print("  | %-42s | %8s | %-16s |" % (nama, f"{tanda}{jumlah:,}", catatan[:16]))
    print("  |%s|%s|%s|" % ("-" * 44, "-" * 10, "-" * 18))
    print("  | %-42s | %8s | %-16s |" % ("SISA (tweets_clean)", f"{len(hasil):,}", ""))
    print("  " + "-" * 76)

    awal = jejak[0][1]
    print(f"\nOK  {awal:,} -> {len(hasil):,} baris "
          f"({len(hasil) / awal * 100:.1f}% bertahan) dalam {time.time() - t0:.1f} detik")
    print(f"    -> {out_path}")
    print(f"\n    Lanjut:  python src/labeling.py{' --demo' if demo else ''}")


if __name__ == "__main__":
    main()
