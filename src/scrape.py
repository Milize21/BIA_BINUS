"""
scrape.py -- TAHAP 1: ambil tweet dari X pakai Selenium.

STATUS: kerangka. Ini pekerjaan Jalur A (PLAN.md bagian 7).

INPUT   : keyword + rentang tanggal (20 Sep - 19 Nov 2024)
OUTPUT  : data/raw/tweets_<keyword>_<tanggal>.csv  (CSV MENTAH, bukan 7 kolom kontrak)

Kolom mentah yang minimal harus kekumpul -- nanti dipakai preprocess.py:
    tanggal, teks, likes, retweet, username

Yang harus diwaspadai (PLAN.md bagian 10):
  * TEKS JANGAN KEPOTONG. X memendekkan tweet panjang jadi "Show more".
    Kalau kepotong, word cloud & hasil labeling jadi timpang.
    -> klik "Show more" dulu, atau ambil dari elemen lengkapnya.
  * Scroll pelan + jeda acak. Terlalu cepat = kena rate limit / akun kena blok.
  * Simpan berkala (append per batch), jangan tunggu selesai baru nulis file.
    Scraping X gampang putus di tengah jalan.
  * Pakai advanced search X dengan filter tanggal per hari/minggu, jangan
    sekali tarik 2 bulan -- hasilnya bakal dipotong sama X.

Contoh query advanced search:
    pelantikan prabowo until:2024-10-21 since:2024-10-20 lang:id

Selenium 4.6+ sudah punya Selenium Manager -> driver ke-download otomatis,
tidak perlu webdriver-manager.

FALLBACK SAH (PLAN.md bagian 10): kalau scraping mentok, rubrik mengizinkan
pakai dataset publik / simulasi. Catat keputusannya di PLAN.md, jangan diam-diam.
"""

from __future__ import annotations

from pathlib import Path

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

KEYWORDS = [
    "pelantikan prabowo",
    "prabowo gibran",
    "pelantikan presiden",
    "#PelantikanPresiden",
]


def main() -> None:
    raise NotImplementedError(
        "scrape.py belum diimplementasi -- ini jatah Jalur A (PLAN.md bagian 7). "
        "Sementara itu Jalur B sudah bisa jalan pakai data/processed/dataset_dummy.csv."
    )


if __name__ == "__main__":
    main()
