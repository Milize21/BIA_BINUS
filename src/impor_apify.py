"""
impor_apify.py -- TAHAP 1 (jalur kedua): ubah ekspor Apify (.xlsx) jadi CSV mentah.

INPUT   : berkas .xlsx hasil actor Apify "twitter-x-data-tweet-scraper"
OUTPUT  : data/raw/tweets_apify_<tanggal-jalan>.csv
          -> kolom SAMA PERSIS dengan keluaran scrape.py, jadi preprocess.py
             membacanya tanpa perlu tahu datanya dari mana.

    python src/impor_apify.py ../Data_Scraper_X/dataTwitter.xlsx
    python src/impor_apify.py dataTwitter.xlsx --utc     # jangan konversi ke WIB

=== KENAPA LEWAT CSV MENTAH, BUKAN LANGSUNG KE DASHBOARD ===

Data Apify tetap harus melewati preprocess -> labeling -> train_model yang
sama dengan panen Selenium. Kalau disuntik langsung ke dataset_final.csv,
tweet-nya tidak ikut dedup, filter bot, maupun labeling lexicon -- dan dua
sumber data akan diperlakukan beda tanpa ada yang sadar.

Nama berkasnya sengaja diawali "tweets_apify_": glob preprocess.py diurutkan
abjad, jadi Apify terbaca DULUAN dan menang saat dedup teks lintas sumber.
Itu disengaja -- teks Apify utuh (tidak pernah kepotong "Show more") dan
angka likes/retweet-nya integer asli, bukan "1.2K" hasil baca layar.

=== WAKTU ===

`createdAt` dari Apify selalu UTC ("Thu Sep 19 18:26:53 +0000 2024").
Dikonversi ke WIB supaya sama dengan scrape.py -- kalau tidak, tweet jam
00:00-06:59 WIB masuk ke hari sebelumnya dan heatmap jam x hari bergeser 7 jam.
"""

from __future__ import annotations

import argparse
import html
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"

# Samakan dengan scrape.py -- preprocess.py mengandalkan kolom ini.
KOLOM = ["tanggal", "teks", "likes", "retweet", "username", "id", "url", "kepotong"]
KOLOM_APIFY = ["id", "url", "text", "likeCount", "retweetCount", "createdAt", "author"]


def ambil_username(author) -> str:
    """
    Kolom `author` di ekspor Excel berbentuk repr dict Python, bukan JSON:
    "{'type': 'user', 'userName': 'BeritakanID_com', ...}". Tidak di-eval --
    cukup cari kuncinya, supaya isi sel yang aneh tidak pernah dijalankan.
    """
    s = str(author)
    kunci = "'userName': '"
    i = s.find(kunci)
    if i < 0:
        return ""
    i += len(kunci)
    return s[i:s.find("'", i)]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    p.add_argument("xlsx", type=Path, help="berkas .xlsx ekspor Apify")
    p.add_argument("--utc", action="store_true", help="simpan waktu UTC, jangan konversi ke WIB")
    args = p.parse_args()

    if not args.xlsx.exists():
        raise SystemExit(f"Berkas tidak ada: {args.xlsx}")

    print(f"  baca {args.xlsx.name} ...")
    d = pd.read_excel(args.xlsx)
    kurang = [k for k in KOLOM_APIFY if k not in d.columns]
    if kurang:
        raise SystemExit(
            f"{args.xlsx.name} bukan ekspor Apify yang dikenali -- kolom hilang: "
            f"{', '.join(kurang)}"
        )

    saat = pd.to_datetime(d["createdAt"], format="%a %b %d %H:%M:%S %z %Y", errors="coerce")
    if not args.utc:
        saat = saat.dt.tz_convert("Asia/Jakarta")

    hasil = pd.DataFrame({
        "tanggal": saat.dt.strftime("%Y-%m-%d %H:%M:%S"),
        # Apify mengembalikan teks apa adanya dari API X, termasuk entitas HTML
        # ("&amp;", "&gt;"). Tanpa unescape, "amp" dan "gt" ikut jadi kata.
        "teks": d["text"].fillna("").astype(str).map(html.unescape),
        "likes": d["likeCount"],
        "retweet": d["retweetCount"],
        "username": d["author"].map(ambil_username),
        "id": d["id"].astype(str),
        "url": d["url"],
        # Teks dari API selalu utuh (note tweet ikut penuh), tidak ada "Show more".
        "kepotong": 0,
    })

    n_tanggal = int(saat.isna().sum())
    n_user = int((hasil["username"] == "").sum())
    hasil = hasil[saat.notna()].drop_duplicates(subset="id").sort_values("tanggal")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    out = RAW_DIR / f"tweets_apify_{date.today():%Y%m%d}.csv"
    hasil.to_csv(out, index=False, encoding="utf-8")

    tgl = pd.to_datetime(hasil["tanggal"])
    print(f"  {len(hasil):,} tweet -> {out.relative_to(ROOT)}")
    print(f"  rentang {tgl.min():%d %b %Y %H:%M} - {tgl.max():%d %b %Y %H:%M} "
          f"({'UTC' if args.utc else 'WIB'})")
    if n_tanggal:
        print(f"  PERINGATAN: {n_tanggal:,} baris dibuang, createdAt tidak terbaca")
    if n_user:
        print(f"  PERINGATAN: {n_user:,} baris tanpa username (kolom author tidak dikenali)")


if __name__ == "__main__":
    main()
