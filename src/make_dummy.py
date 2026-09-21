"""
make_dummy.py -- bikin data/processed/dataset_dummy.csv

Data BOHONGAN. Tujuannya supaya Jalur B (tim dashboard) bisa bangun semua chart
TANPA nunggu scraping kelar (PLAN.md bagian 6, "Trik paralel").

=== KENAPA GENERATOR-NYA SERIBET INI ===

Data acak yang rata TIDAK berguna buat bangun dashboard. Kalau tiap hari isinya
kata yang sama dengan proporsi sentimen yang sama, maka:
  - word cloud tiap periode kelihatan identik -> tab word cloud jadi mubazir
  - "kata khas per periode" tidak menemukan apa-apa
  - uji chi-square tidak signifikan -> tab statistik kosong
  - tren cuma garis datar -> "jualan utama" tidak ada yang dijual

Jadi generator ini memodelkan struktur yang memang ada di percakapan asli:

  1. TOPIK yang naik-turun sendiri-sendiri sepanjang waktu.
     "persiapan" ramai sebelum, "seremoni" meledak di hari-H, "kabinet" baru
     meledak SESUDAH, "ekonomi" merangkak naik pelan di akhir. Tiap topik punya
     kosakata sendiri -> word cloud tiap periode otomatis beda isinya.

  2. Tiap topik punya KECENDERUNGAN SENTIMEN sendiri.
     Topik "seremoni" mayoritas positif, topik "kabinet gemuk" mayoritas negatif.
     Jadi pergeseran sentimen antarperiode LAHIR dari pergeseran topik --
     bukan ditempel manual. Ini yang bikin ceritanya masuk akal.

  3. PERSONA AKUN. Media (netral, engagement tinggi), pendukung (positif),
     kritikus (negatif), umum (campur). Bikin analisis "akun paling
     berpengaruh" jadi ada isinya.

  4. Volume harian = jumlah aktivitas semua topik hari itu. Jadi lonjakan
     muncul sendiri di tanggal yang masuk akal, bukan ditanam manual.

Anchor tanggalnya longgar mengikuti linimasa asli (pelantikan 20 Okt 2024,
pengumuman kabinet sehari sesudahnya), TAPI SEMUA ISI TWEET-NYA KARANGAN.
Jangan pernah dipakai di laporan atau screenshot presentasi.

Output tetap 7 KOLOM KONTRAK (PLAN.md bagian 3), tidak lebih tidak kurang.
Cuma pakai stdlib -> bisa jalan walau requirements.txt belum keinstall.

    python src/make_dummy.py              # 12.000 baris, seed 42 (default)
    python src/make_dummy.py 3000 7       # 3.000 baris, seed 7
"""

from __future__ import annotations

import csv
import math
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------- konfigurasi

OUT_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "dataset_dummy.csv"

KOLOM = ["tanggal", "periode", "teks_bersih", "sentimen", "likes", "retweet", "username"]

HARI_H = date(2024, 10, 20)
MULAI = date(2024, 9, 20)     # H-30
SELESAI = date(2024, 11, 19)  # H+30

N_DEFAULT = 12_000

# ==============================================================================
# TOPIK
# ==============================================================================
# Tiap topik punya:
#   puncak : hari ke berapa (relatif 20 Okt) topik ini paling ramai
#   lebar  : seberapa melebar ramainya (hari). Kecil = lonjakan tajam.
#   amp    : setinggi apa puncaknya
#   dasar  : seberapa ramai topik ini di hari biasa (biar tidak nol)
#   bias   : kecenderungan sentimen (positif, netral, negatif) -- total 1.0
#   kata   : kosakata khas topik, sudah dalam bentuk pasca-preprocessing
#
# Prevalensi tiap hari = dasar + amp * exp(-((d - puncak) / lebar)^2)

TOPIK = {
    "persiapan": dict(
        puncak=-7, lebar=8.0, amp=3.2, dasar=0.30, bias=(0.46, 0.36, 0.18),
        kata=[
            "persiapan", "gladi bersih", "jadwal acara", "undangan", "pengamanan",
            "rute", "senayan", "mpr", "panitia", "sidang paripurna", "protokol",
            "rekayasa lalu lintas", "geladi", "kesiapan", "pasukan pengamanan",
        ],
    ),
    "seremoni": dict(
        puncak=0, lebar=1.7, amp=11.0, dasar=0.12, bias=(0.72, 0.20, 0.08),
        kata=[
            "pelantikan", "sumpah jabatan", "prosesi", "khidmat", "kirab",
            "istana merdeka", "pidato perdana", "salam komando", "pakaian adat",
            "iring iringan", "serah terima", "detik detik", "penyematan",
            "mengheningkan cipta", "pelantikanpresiden", "prabowogibran",
        ],
    ),
    "tamu_negara": dict(
        puncak=0, lebar=2.4, amp=4.2, dasar=0.05, bias=(0.58, 0.35, 0.07),
        kata=[
            "tamu negara", "delegasi", "kepala negara", "diplomatik", "bilateral",
            "undangan asing", "protokol kenegaraan", "perwakilan", "utusan khusus",
        ],
    ),
    "jokowi": dict(
        puncak=-3, lebar=7.0, amp=2.1, dasar=0.30, bias=(0.44, 0.26, 0.30),
        kata=[
            "jokowi", "purna tugas", "warisan", "sepuluh tahun", "pamit", "solo",
            "transisi", "estafet kepemimpinan", "akhir jabatan", "pendahulu",
        ],
    ),
    "kabinet": dict(
        puncak=1.5, lebar=2.6, amp=8.5, dasar=0.45, bias=(0.30, 0.22, 0.48),
        kata=[
            "kabinet merah putih", "menteri", "wakil menteri", "kabinet gemuk",
            "bagi bagi kursi", "koalisi", "jatah partai", "postur kabinet",
            "susunan menteri", "titipan partai", "kursi kekuasaan", "reshuffle",
        ],
    ),
    "program": dict(
        puncak=11, lebar=9.0, amp=3.1, dasar=0.30, bias=(0.52, 0.22, 0.26),
        kata=[
            "makan bergizi gratis", "swasembada pangan", "program unggulan",
            "seratus hari", "hilirisasi", "kedaulatan energi", "pendidikan gratis",
            "layanan kesehatan", "janji kampanye", "realisasi program",
        ],
    ),
    "ekonomi": dict(
        puncak=22, lebar=13.0, amp=3.4, dasar=0.40, bias=(0.22, 0.22, 0.56),
        kata=[
            "anggaran", "utang negara", "defisit", "pajak", "harga pangan",
            "daya beli", "rupiah", "investasi", "pemborosan", "efisiensi anggaran",
            "beban fiskal", "subsidi", "biaya negara",
        ],
    ),
    "dinasti": dict(
        puncak=-6, lebar=22.0, amp=1.3, dasar=0.55, bias=(0.13, 0.19, 0.68),
        kata=[
            "dinasti politik", "mahkamah konstitusi", "putusan", "batas usia",
            "nepotisme", "oligarki", "demokrasi", "etika politik", "cawe cawe",
            "kemunduran demokrasi",
        ],
    ),
}

# ==============================================================================
# KOSAKATA SENTIMEN (dipakai lintas topik)
# ==============================================================================

KATA_POSITIF = [
    "dukung", "optimis", "bangga", "semangat", "amanah", "sukses", "harap",
    "percaya", "hormat", "apresiasi", "lancar", "solid", "tegas", "berani",
    "mantap", "salut", "doa", "damai", "bersatu", "wibawa", "gagah", "haru",
    "selamat", "sejarah baru", "rakyat sejahtera", "indonesia emas", "kerja nyata",
    "megah", "legowo", "patut ditiru",
]

KATA_NETRAL = [
    "dilantik", "resmi", "berlangsung", "dijadwalkan", "disiarkan", "hadir",
    "menyampaikan", "laporan", "keterangan", "data", "menurut", "tercatat",
    "dokumentasi", "siaran langsung", "konferensi pers", "susunan acara",
    "masa jabatan", "periode", "agenda", "rangkaian",
]

KATA_NEGATIF = [
    "kecewa", "tolak", "ragu", "khawatir", "pesimis", "kritik", "protes",
    "gagal", "bohong", "pencitraan", "omong kosong", "boros", "mahal", "susah",
    "muak", "sindir", "janji manis", "rakyat susah", "tidak becus", "korupsi",
    "elit", "buang buang uang", "kecewa berat", "asal bapak senang", "basi",
]

KATA_SENTIMEN = {
    "positif": KATA_POSITIF,
    "netral": KATA_NETRAL,
    "negatif": KATA_NEGATIF,
}

# ==============================================================================
# PERSONA AKUN
# ==============================================================================
# porsi     : berapa persen dari kolam akun
# cerewet   : rata-rata berapa kali akun ini nge-tweet (pengali bobot)
# jangkauan : pengali engagement (media & influencer jauh lebih tinggi)
# condong   : pengali sentimen (positif, netral, negatif)

PERSONA = {
    "media":     dict(porsi=0.04, cerewet=6.0, jangkauan=7.0, condong=(0.7, 3.2, 0.8)),
    "pendukung": dict(porsi=0.30, cerewet=2.2, jangkauan=1.0, condong=(2.6, 0.7, 0.3)),
    "kritikus":  dict(porsi=0.22, cerewet=2.4, jangkauan=1.5, condong=(0.3, 0.7, 2.8)),
    "umum":      dict(porsi=0.44, cerewet=1.0, jangkauan=0.8, condong=(1.0, 1.0, 1.0)),
}

DEPAN_USERNAME = [
    "andi", "budi", "citra", "dewi", "eko", "fitri", "galih", "hesti", "indra",
    "joko", "kirana", "lukman", "maya", "nanda", "oki", "putri", "rizky", "sari",
    "tono", "umar", "vina", "wahyu", "yuda", "zahra", "bagas", "intan", "raka",
    "sinta", "dimas", "laras", "arif", "nisa", "bayu", "tari", "gilang", "ayu",
]
BELAKANG_USERNAME = [
    "", "", "", "_id", "24", "wati", "putra", "88", "_rl", "1990", "_ind",
    "2024", "_jkt", "xyz", "77", "_real", "ku", "nesia",
]
NAMA_MEDIA = [
    "warta", "kabar", "info", "berita", "lensa", "suara", "detik", "pos",
    "harian", "media", "redaksi", "jurnal",
]
EKOR_MEDIA = ["nusantara", "indo", "hariini", "terkini", "id", "update", "now", "24jam"]


# -------------------------------------------------------------------- helper

def tentukan_periode(t: date) -> str:
    """Sesuai PLAN.md bagian 3: sebelum / hari-h / sesudah."""
    if t < HARI_H:
        return "sebelum"
    if t == HARI_H:
        return "hari-h"
    return "sesudah"


def prevalensi_topik(nama: str, d: int) -> float:
    """Seberapa ramai satu topik di hari ke-d (relatif terhadap 20 Okt)."""
    t = TOPIK[nama]
    return t["dasar"] + t["amp"] * math.exp(-(((d - t["puncak"]) / t["lebar"]) ** 2))


def bobot_hari(t: date) -> float:
    """
    Volume harian = total aktivitas semua topik.

    Tidak ada lonjakan yang ditanam manual: 20 Okt ramai karena topik "seremoni"
    dan "tamu_negara" sama-sama memuncak di situ, dan 21-22 Okt tetap ramai
    karena topik "kabinet" baru menyusul sesudahnya.
    """
    d = (t - HARI_H).days
    total = sum(prevalensi_topik(k, d) for k in TOPIK)
    # akhir pekan sedikit lebih sepi -- kecuali hari-H yang jelas tidak peduli
    if d != 0 and t.weekday() >= 5:
        total *= 0.88
    return total


def pilih_topik(rng: random.Random, d: int) -> str:
    nama = list(TOPIK)
    return rng.choices(nama, weights=[prevalensi_topik(k, d) for k in nama], k=1)[0]


def geser_periode(d: int) -> tuple:
    """
    Pengali sentimen global -- "mood" nasional di luar pengaruh topik.

    Naik menjelang & saat pelantikan (euforia), lalu luruh sesudahnya.
    Ini DIKALIKAN dengan kecenderungan sentimen topik, jadi pergeseran akhirnya
    adalah gabungan "topiknya berubah" + "moodnya berubah".
    """
    if d == 0:
        return (1.35, 0.95, 0.60)
    if d < 0:
        dekat = max(0.0, 1.0 + d / 30.0)          # 0.0 di H-30 -> 1.0 di hari-H
        return (0.95 + 0.30 * dekat, 1.0, 1.10 - 0.25 * dekat)
    jauh = min(1.0, d / 30.0)                     # 0.0 di H+0 -> 1.0 di H+30
    return (1.20 - 0.45 * jauh, 1.0, 0.75 + 0.55 * jauh)


def pilih_sentimen(rng: random.Random, topik: str, d: int, persona: str) -> str:
    """Gabungan tiga pengaruh: kecenderungan topik x mood periode x watak akun."""
    bias = TOPIK[topik]["bias"]
    mood = geser_periode(d)
    watak = PERSONA[persona]["condong"]
    bobot = [b * m * w for b, m, w in zip(bias, mood, watak)]
    return rng.choices(["positif", "netral", "negatif"], weights=bobot, k=1)[0]


def buat_teks(rng: random.Random, topik: str, sentimen: str) -> str:
    """
    Rangkai teks_bersih: kata topik + kata sentimen, panjang bervariasi.

    Bentuknya meniru hasil AKHIR preprocessing (PLAN.md tahap 2a) -- lowercase,
    tanpa URL/mention/tanda baca, stopword sudah dibuang, jadi isinya kata
    konten saja.
    """
    kolam_topik = TOPIK[topik]["kata"]
    kata = rng.sample(kolam_topik, k=min(len(kolam_topik), rng.randint(2, 4)))
    kata += rng.sample(KATA_SENTIMEN[sentimen], k=rng.randint(3, 8))

    # Sesekali nyerempet topik lain -- percakapan asli memang tidak rapi.
    if rng.random() < 0.30:
        lain = rng.choice([k for k in TOPIK if k != topik])
        kata.append(rng.choice(TOPIK[lain]["kata"]))

    # Bocoran kata dari kelas sentimen lain. INI DISENGAJA: bikin kelas netral
    # memang susah dipisahkan, sesuai limitation yang mau dibahas jujur di
    # laporan (PLAN.md bagian 10).
    if rng.random() < 0.22:
        lain = rng.choice([k for k in KATA_SENTIMEN if k != sentimen])
        kata.append(rng.choice(KATA_SENTIMEN[lain]))

    rng.shuffle(kata)
    return " ".join(kata)


def buat_jam(rng: random.Random, t: date, topik: str) -> datetime:
    """
    Jam posting. Di hari-H menumpuk di sekitar prosesi (pagi-siang WIB);
    topik "kabinet" condong malam (pengumuman kabinet memang malam hari).
    """
    if t == HARI_H and topik in ("seremoni", "tamu_negara"):
        jam = min(23, max(0, int(rng.gauss(11, 2.0))))
    elif topik == "kabinet" and rng.random() < 0.45:
        jam = min(23, max(0, int(rng.gauss(20, 2.5))))
    else:
        jam = rng.choices(
            range(24),
            # pola harian: sepi dini hari, ramai pagi & malam
            weights=[2, 1, 1, 1, 2, 4, 7, 9, 10, 10, 9, 8,
                     8, 8, 8, 8, 9, 10, 12, 14, 14, 12, 8, 4],
            k=1,
        )[0]
    return datetime(t.year, t.month, t.day, jam, rng.randrange(60), rng.randrange(60))


def buat_engagement(rng: random.Random, sentimen: str, persona: str, d: int) -> tuple:
    """
    likes & retweet. Lognormal -> mayoritas kecil, segelintir viral.

    Dipengaruhi: jangkauan akun (media jauh lebih tinggi), sentimen (tweet
    negatif lebih gampang nyebar), dan kedekatan ke hari-H (momentum).
    Retweet selalu lebih sedikit dari likes, seperti di X.
    """
    mu = {"positif": 2.6, "netral": 2.1, "negatif": 2.95}[sentimen]
    mu += math.log(PERSONA[persona]["jangkauan"])
    mu += 0.45 * math.exp(-abs(d) / 6.0)                   # momentum sekitar hari-H

    likes = int(rng.lognormvariate(mu, 1.3))
    if rng.random() < 0.010:                               # ~1% tweet viral
        likes *= rng.randint(10, 55)
    likes = min(likes, 400_000)

    # Rasio amplifikasi: tweet negatif cenderung lebih banyak di-retweet
    # relatif terhadap likes-nya (outrage nyebar lebih jauh).
    rasio = rng.uniform(0.10, 0.30) * (1.25 if sentimen == "negatif" else 1.0)
    retweet = int(likes * rasio + rng.random() * 3)
    return likes, retweet


def buat_kolam_akun(rng: random.Random, n: int) -> tuple:
    """
    Kolam akun + persona + bobot kecerewetan.

    Distribusi Zipf digabung dengan persona: sedikit akun media yang sangat
    cerewet & berjangkauan luas, banyak akun umum yang cuma nge-tweet sekali.
    """
    jumlah = max(120, int(n * 0.28))
    akun, persona_akun, bobot, dipakai = [], [], [], set()

    daftar_persona = []
    for nama, cfg in PERSONA.items():
        daftar_persona += [nama] * max(1, round(jumlah * cfg["porsi"]))
    rng.shuffle(daftar_persona)

    for i in range(jumlah):
        p = daftar_persona[i % len(daftar_persona)]
        for _ in range(60):
            if p == "media":
                nama = rng.choice(NAMA_MEDIA) + rng.choice(EKOR_MEDIA)
            else:
                nama = rng.choice(DEPAN_USERNAME) + rng.choice(BELAKANG_USERNAME)
                if rng.random() < 0.35:
                    nama += str(rng.randrange(10, 9999))
            if nama not in dipakai:
                break
        if nama in dipakai:
            continue
        dipakai.add(nama)
        akun.append(nama)
        persona_akun.append(p)
        # Zipf x kecerewetan persona
        bobot.append(PERSONA[p]["cerewet"] / (len(akun) ** 0.55))

    return akun, persona_akun, bobot


# ---------------------------------------------------------------------- main

def generate(n_baris: int = N_DEFAULT, seed: int = 42) -> list:
    rng = random.Random(seed)

    tanggal = []
    t = MULAI
    while t <= SELESAI:
        tanggal.append(t)
        t += timedelta(days=1)

    bobot_tanggal = [bobot_hari(t) for t in tanggal]
    akun, persona_akun, bobot_akun = buat_kolam_akun(rng, n_baris)
    indeks_akun = list(range(len(akun)))

    baris = []
    for t in rng.choices(tanggal, weights=bobot_tanggal, k=n_baris):
        d = (t - HARI_H).days
        i = rng.choices(indeks_akun, weights=bobot_akun, k=1)[0]
        persona = persona_akun[i]

        topik = pilih_topik(rng, d)
        sentimen = pilih_sentimen(rng, topik, d, persona)
        likes, retweet = buat_engagement(rng, sentimen, persona, d)

        baris.append({
            "tanggal": buat_jam(rng, t, topik).strftime("%Y-%m-%d %H:%M:%S"),
            "periode": tentukan_periode(t),
            "teks_bersih": buat_teks(rng, topik, sentimen),
            "sentimen": sentimen,
            "likes": likes,
            "retweet": retweet,
            "username": akun[i],
        })

    baris.sort(key=lambda r: r["tanggal"])
    return baris


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else N_DEFAULT
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42

    baris = generate(n, seed)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KOLOM)
        w.writeheader()
        w.writerows(baris)

    # ringkasan, biar kelihatan datanya masuk akal tanpa buka file
    per_periode, per_sentimen, per_hari = {}, {}, {}
    for r in baris:
        per_periode[r["periode"]] = per_periode.get(r["periode"], 0) + 1
        per_sentimen[r["sentimen"]] = per_sentimen.get(r["sentimen"], 0) + 1
        h = r["tanggal"][:10]
        per_hari[h] = per_hari.get(h, 0) + 1

    ramai = sorted(per_hari.items(), key=lambda kv: -kv[1])[:5]
    print("OK  {:,} baris -> {}".format(len(baris), OUT_PATH))
    print("    periode   : {}".format(per_periode))
    print("    sentimen  : {}".format(per_sentimen))
    print("    akun unik : {:,}".format(len(set(r["username"] for r in baris))))
    print("    5 hari teramai:")
    for h, c in ramai:
        print("      {}  {:5,}".format(h, c))


if __name__ == "__main__":
    main()
