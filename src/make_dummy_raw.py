"""
make_dummy_raw.py -- bikin data/raw/dummy_raw_*.csv

Data BOHONGAN, tapi beda tujuan dari make_dummy.py:

    make_dummy.py      -> meniru dataset FINAL  (sudah bersih, 7 kolom kontrak)
                          dipakai Jalur B buat bangun dashboard
    make_dummy_raw.py  -> meniru CSV MENTAH hasil scrape.py (masih kotor)
                          dipakai Jalur A buat bangun & MENGUJI preprocess.py

Triknya sama persis seperti di dashboard: bangun dan uji Tahap 2 sekarang,
supaya begitu hasil scraping asli masuk, pipeline-nya sudah terbukti jalan dan
tinggal ganti input.

=== SAMPAH YANG SENGAJA DIMASUKKAN ===

Preprocessing yang cuma diuji pakai teks rapi itu tidak teruji sama sekali.
Jadi file ini sengaja menanam semua jenis kotoran yang beneran muncul di X:

  - URL (t.co, bit.ly), @mention, #hashtag, emoji
  - HURUF BESAR acak, tanda baca berlebihan ("!!!", "???", "....")
  - kata gaul & singkatan: yg, gak, bgt, aja, dgn, tdk, utk
  - kata berimbuhan: "mendukung", "penolakan", "dilantik" (buat menguji stemmer)
  - stopword bertebaran (kalau tidak dibuang, word cloud jadi sampah)
  - DUPLIKAT PERSIS (orang nge-post ulang) & near-duplicate
  - AKUN BOT/BUZZER: 1 akun nge-post teks nyaris sama puluhan kali
  - TWEET KEPOTONG: berakhir dengan "… Show more" (PLAN.md bagian 10!)
  - likes/retweet KOSONG, dan angka bergaya "1.2K" / "3,456"
  - tanggal DI LUAR rentang (20 Sep - 19 Nov 2024) yang harus dibuang
  - baris dengan teks kosong

Kalau preprocess.py lolos semua ini, dia siap menghadapi data asli.

Kolomnya = bentuk keluaran scrape.py, BUKAN 7 kolom kontrak:
    tanggal, teks, likes, retweet, username
(`periode` dan `sentimen` belum ada -- itu lahir di preprocess.py & labeling.py)

    python src/make_dummy_raw.py            # 15.000 baris mentah, seed 42
    python src/make_dummy_raw.py 5000 7     # 5.000 baris, seed 7
"""

from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# make_dummy.py ada di folder yang sama -- kosakata & struktur topiknya dipakai
# ulang supaya dua dummy ini bercerita tentang peristiwa yang sama.
from make_dummy import (
    HARI_H,
    KATA_SENTIMEN,
    MULAI,
    SELESAI,
    TOPIK,
    bobot_hari,
    buat_jam,
    buat_kolam_akun,
    pilih_sentimen,
    pilih_topik,
)

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Kolom "_kunci" BUKAN hasil scraping -- scrape.py TIDAK akan menghasilkannya.
# Isinya sentimen sebenarnya dari tiap tweet karangan, dipakai HANYA untuk
# mengukur seberapa jauh labeling.py berhasil memulihkan sentimen aslinya.
# Pipeline tidak boleh memakainya sebagai masukan; namanya diawali "_" supaya
# jelas ini artefak pengujian. Di data asli kolom ini tidak ada, dan peran
# penggantinya dipegang validasi manual 100 tweet.
KOLOM = ["tanggal", "teks", "likes", "retweet", "username", "_kunci"]

N_DEFAULT = 15_000

# Satu berkas per keyword, meniru scrape.py yang menarik per kata kunci.
KEYWORDS = ["pelantikan_prabowo", "prabowo_gibran", "pelantikan_presiden"]

# ------------------------------------------------------------------ kotoran

STOPWORD_SISIP = [
    "yang", "dan", "di", "ini", "itu", "dengan", "untuk", "dari", "ke", "pada",
    "adalah", "akan", "juga", "sudah", "sih", "banget", "aja", "nih", "kok",
    "ya", "kalau", "biar", "saya", "kita", "mereka", "tapi", "karena", "jadi",
]

# Bentuk gaul -> nanti harus dinormalisasi balik oleh preprocess.py
GAUL = {
    "yang": ["yg", "yang", "yg"],
    "dengan": ["dgn", "dengan"],
    "tidak": ["gak", "ga", "tdk", "nggak"],
    "untuk": ["utk", "untuk"],
    "banget": ["bgt", "banget", "bngt"],
    "saja": ["aja", "saja"],
    "sudah": ["udah", "sdh", "sudah"],
    "bagaimana": ["gmn", "gimana"],
    "orang": ["org", "orang"],
}

# Kata berimbuhan: bentuk dasar -> variasi berimbuhan.
# Ini yang menguji apakah stemmer Sastrawi benar-benar jalan.
IMBUHAN = {
    "dukung": ["mendukung", "dukungan", "didukung", "pendukung"],
    "tolak": ["menolak", "penolakan", "ditolak"],
    "harap": ["berharap", "harapan", "diharapkan"],
    "kritik": ["mengkritik", "kritikan", "dikritik"],
    "kecewa": ["kecewanya", "mengecewakan", "kekecewaan"],
    "pelantikan": ["dilantik", "melantik", "pelantikan"],
    "protes": ["memprotes", "protesnya"],
    "bangga": ["membanggakan", "kebanggaan"],
    "percaya": ["kepercayaan", "mempercayai", "dipercaya"],
    "gagal": ["kegagalan", "menggagalkan"],
    "janji": ["menjanjikan", "perjanjian", "dijanjikan"],
    "boros": ["pemborosan", "memboroskan"],
    "sukses": ["kesuksesan", "menyukseskan"],
    "resmi": ["diresmikan", "peresmian"],
    "pilih": ["memilih", "pilihan", "terpilih"],
}

HASHTAG = [
    "#PelantikanPresiden", "#PrabowoGibran", "#IndonesiaMaju", "#20Oktober",
    "#KabinetMerahPutih", "#PelantikanPresiden2024", "#Prabowo", "#Gibran",
]

EMOJI = ["🇮🇩", "🔥", "😭", "😡", "🙏", "👏", "💪", "😂", "🤔", "❤️", "👎", "✨"]

EKOR_KEPOTONG = ["… Show more", "... Show more", "…", "... baca selengkapnya"]


# -------------------------------------------------------------------- helper

def acak_kapital(rng: random.Random, teks: str) -> str:
    """Tiru cara orang ngetik: kadang normal, kadang KAPITAL, kadang acak."""
    r = rng.random()
    if r < 0.06:
        return teks.upper()
    if r < 0.10:
        return " ".join(w.capitalize() for w in teks.split())
    if r < 0.14:
        return "".join(c.upper() if rng.random() < 0.3 else c for c in teks)
    return teks


def bentuk_kata(rng: random.Random, kata: str) -> str:
    """Kadang dipakai apa adanya, kadang diberi imbuhan, kadang jadi bentuk gaul."""
    dasar = kata.split()[0]
    if dasar in IMBUHAN and rng.random() < 0.45:
        return kata.replace(dasar, rng.choice(IMBUHAN[dasar]), 1)
    return kata


def sisip_stopword(rng: random.Random, kata: list) -> list:
    """Taburkan stopword & kata gaul di antara kata konten, seperti kalimat asli."""
    keluar = []
    for k in kata:
        keluar.append(k)
        if rng.random() < 0.45:
            s = rng.choice(STOPWORD_SISIP)
            keluar.append(rng.choice(GAUL[s]) if s in GAUL else s)
    return keluar


def buat_teks_kotor(rng: random.Random, topik: str, sentimen: str) -> str:
    """Rangkai satu tweet MENTAH, lengkap dengan semua sampahnya."""
    kolam_topik = TOPIK[topik]["kata"]
    isi = rng.sample(kolam_topik, k=min(len(kolam_topik), rng.randint(1, 3)))
    isi += rng.sample(KATA_SENTIMEN[sentimen], k=rng.randint(3, 7))
    rng.shuffle(isi)

    isi = [bentuk_kata(rng, k) for k in isi]
    kata = sisip_stopword(rng, isi)
    teks = " ".join(kata)

    # tanda baca berlebihan
    if rng.random() < 0.35:
        teks += rng.choice(["!!!", "!!", "???", "....", "..", "!?"])
    else:
        teks += rng.choice([".", "", "", ""])

    # angka nyasar (tahun, jumlah menteri, persentase)
    if rng.random() < 0.18:
        teks += " " + rng.choice(["2024", "109", "20 Oktober", "5 tahun", "80%"])

    bagian = [teks]

    # @mention di depan (balasan)
    if rng.random() < 0.22:
        bagian.insert(0, "@" + rng.choice([
            "prabowo", "gibran_rakabuming", "jokowi", "kompascom", "detikcom",
            "tvOneNews", "CNNIndonesia", "narasinewsroom",
        ]))

    # hashtag
    if rng.random() < 0.30:
        bagian.append(" ".join(rng.sample(HASHTAG, k=rng.randint(1, 3))))

    # URL
    if rng.random() < 0.20:
        bagian.append(rng.choice([
            "https://t.co/" + "".join(rng.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=10)),
            "http://bit.ly/" + "".join(rng.choices("abcdefghijklmnopqrstuvwxyz", k=7)),
        ]))

    # emoji
    if rng.random() < 0.28:
        bagian.append("".join(rng.choices(EMOJI, k=rng.randint(1, 3))))

    hasil = " ".join(bagian)
    hasil = acak_kapital(rng, hasil)

    # TWEET KEPOTONG -- jebakan utama di PLAN.md bagian 10
    if rng.random() < 0.05:
        potong = rng.randint(40, max(45, len(hasil) - 10))
        hasil = hasil[:potong].rstrip() + rng.choice(EKOR_KEPOTONG)

    return hasil


def format_angka(rng: random.Random, n: int) -> str:
    """
    X menampilkan angka sebagai '1.2K' / '3,456'. Scraper yang asal ambil teks
    akan membawa format ini apa adanya -- preprocess.py harus tahan.
    """
    r = rng.random()
    if r < 0.05:
        return ""                                   # kolom kosong
    if n >= 1000 and r < 0.55:
        return f"{n / 1000:.1f}K"
    if n >= 1000 and r < 0.75:
        return f"{n:,}"
    return str(n)


def engagement_kasar(rng: random.Random, sentimen: str) -> tuple:
    mu = {"positif": 2.6, "netral": 2.1, "negatif": 2.95}[sentimen]
    likes = int(rng.lognormvariate(mu, 1.3))
    if rng.random() < 0.01:
        likes *= rng.randint(10, 55)
    retweet = int(likes * rng.uniform(0.10, 0.32) + rng.random() * 3)
    return likes, retweet


# ---------------------------------------------------------------------- main

def generate(n_baris: int = N_DEFAULT, seed: int = 42) -> list:
    rng = random.Random(seed)

    tanggal = []
    t = MULAI
    while t <= SELESAI:
        tanggal.append(t)
        t += timedelta(days=1)
    bobot_tanggal = [bobot_hari(x) for x in tanggal]

    akun, persona_akun, bobot_akun = buat_kolam_akun(rng, n_baris)
    indeks = list(range(len(akun)))

    baris = []
    for t in rng.choices(tanggal, weights=bobot_tanggal, k=n_baris):
        d = (t - HARI_H).days
        i = rng.choices(indeks, weights=bobot_akun, k=1)[0]
        persona = persona_akun[i]
        topik = pilih_topik(rng, d)
        sentimen = pilih_sentimen(rng, topik, d, persona)
        likes, retweet = engagement_kasar(rng, sentimen)

        baris.append({
            "tanggal": buat_jam(rng, t, topik).strftime("%Y-%m-%d %H:%M:%S"),
            "teks": buat_teks_kotor(rng, topik, sentimen),
            "likes": format_angka(rng, likes),
            "retweet": format_angka(rng, retweet),
            "username": akun[i],
            "_kunci": sentimen,
        })

    # ------------------------------------------------------------------
    # Tanam kotoran tingkat-baris. Semua ini HARUS hilang setelah preprocess.
    # ------------------------------------------------------------------
    jumlah_sampah = {}

    # 1. duplikat persis -- orang nge-post ulang tweet yang sama
    n_dup = max(1, int(len(baris) * 0.04))
    for r in rng.sample(baris, k=n_dup):
        baris.append(dict(r))
    jumlah_sampah["duplikat persis"] = n_dup

    # 2. akun bot/buzzer -- 1 akun membanjiri teks nyaris sama
    n_bot = 6
    total_bot = 0
    for b in range(n_bot):
        nama_bot = f"buzzer_relawan{b + 1}"
        topik_bot = rng.choice(list(TOPIK))
        sent_bot = rng.choice(["positif", "negatif"])
        teks_bot = buat_teks_kotor(rng, topik_bot, sent_bot)
        for _ in range(rng.randint(25, 60)):
            hari_bot = rng.choice(tanggal)
            baris.append({
                "tanggal": buat_jam(rng, hari_bot, topik_bot).strftime("%Y-%m-%d %H:%M:%S"),
                # near-duplicate: teks sama, cuma ganti hashtag di belakang
                "teks": teks_bot + " " + rng.choice(HASHTAG),
                "likes": str(rng.randint(0, 4)),
                "retweet": str(rng.randint(0, 2)),
                "username": nama_bot,
                "_kunci": sent_bot,
            })
            total_bot += 1
    jumlah_sampah[f"tweet dari {n_bot} akun bot"] = total_bot

    # 3. tanggal di luar rentang -- harus dibuang preprocess
    n_luar = max(1, int(len(baris) * 0.01))
    for _ in range(n_luar):
        jauh = rng.choice([date(2024, 8, 15), date(2024, 9, 1), date(2024, 12, 25),
                           date(2025, 1, 10)])
        topik_x = rng.choice(list(TOPIK))
        baris.append({
            "tanggal": buat_jam(rng, jauh, topik_x).strftime("%Y-%m-%d %H:%M:%S"),
            "teks": buat_teks_kotor(rng, topik_x, "netral"),
            "likes": str(rng.randint(0, 50)),
            "retweet": str(rng.randint(0, 10)),
            "username": rng.choice(akun),
            "_kunci": "netral",
        })
    jumlah_sampah["tanggal di luar rentang"] = n_luar

    # 4. baris rusak -- teks kosong / cuma URL / cuma emoji
    n_rusak = max(1, int(len(baris) * 0.006))
    for _ in range(n_rusak):
        baris.append({
            "tanggal": buat_jam(rng, rng.choice(tanggal), "seremoni").strftime("%Y-%m-%d %H:%M:%S"),
            "teks": rng.choice(["", "   ", "https://t.co/abcd1234", "🔥🔥🔥", "..."]),
            "likes": "", "retweet": "",
            "username": rng.choice(akun),
            "_kunci": "netral",
        })
    jumlah_sampah["baris rusak (teks kosong/URL saja)"] = n_rusak

    rng.shuffle(baris)
    baris.sort(key=lambda r: r["tanggal"])
    return baris, jumlah_sampah


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42

    baris, sampah = generate(n, seed)
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    # Sebar ke beberapa berkas, meniru scrape.py yang menarik per kata kunci.
    rng = random.Random(seed)
    potongan = {k: [] for k in KEYWORDS}
    for r in baris:
        potongan[rng.choice(KEYWORDS)].append(r)

    for kw, isi in potongan.items():
        path = RAW_DIR / f"dummy_raw_{kw}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=KOLOM)
            w.writeheader()
            w.writerows(isi)
        print("  {:<44} {:>6,} baris".format(str(path.relative_to(RAW_DIR.parents[1])), len(isi)))

    print()
    print("OK  {:,} baris mentah -> {}".format(len(baris), RAW_DIR))
    print("    Kotoran yang ditanam (semua HARUS hilang setelah preprocess.py):")
    for k, v in sampah.items():
        print("      - {:<38} {:>6,}".format(k, v))
    print()
    print("    Lanjut:  python src/preprocess.py --demo")


if __name__ == "__main__":
    main()
