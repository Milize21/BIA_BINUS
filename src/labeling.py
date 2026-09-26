"""
labeling.py -- TAHAP 2b: kasih label sentimen pakai lexicon.

INPUT   : data/processed/tweets_clean.csv     (hasil preprocess.py)
          lexicon/positive.tsv, lexicon/negative.tsv
OUTPUT  : data/processed/tweets_labeled.csv   (tweets_clean + kolom `sentimen`)
          data/processed/validasi_manual.csv  (100 tweet acak untuk dilabeli tangan)

    python src/labeling.py            # pakai InSet di lexicon/
    python src/labeling.py --demo     # pakai kamus mini bawaan, tulis ke *_demo.csv

=== KAMUSNYA AMBIL DI MANA ===
Pakai InSet (Indonesia Sentiment Lexicon) -- Fajri Koto & Gemala Y. Rahmaningtyas,
repo: github.com/fajri91/InSet. Taruh positive.tsv & negative.tsv di lexicon/.
Format tiap baris: `kata<TAB>bobot`. Bobot negatif sudah bernilai minus.
Sitasi InSet WAJIB masuk References (APA). JANGAN mengarang kamus sendiri --
hasil labeling yang kamusnya karangan tidak bisa dipertanggungjawabkan.

=== CARA KERJA ===
    skor = jumlah bobot semua kata yang ketemu di kamus
    skor >  THRESHOLD  -> positif
    skor < -THRESHOLD  -> negatif
    selain itu         -> netral

=== YANG PALING PENTING DI FILE INI: ANGKA OOV ===
Perhatikan baik-baik angka "tidak ada kata yang ketemu di kamus" di keluaran.
Tweet yang tidak punya SATU PUN kata kamus otomatis jatuh ke netral -- padahal
bisa saja isinya sangat positif atau sangat negatif, cuma pakai kata yang tidak
terdaftar. Inilah sebab utama kelas netral jadi keranjang sampah, dan inilah
yang sudah diduga sejak awal di PLAN.md keputusan #6.

Kalau angka OOV tinggi (>25%), jangan ditutupi. Tulis apa adanya di Discussion,
dan pertimbangkan: naikkan THRESHOLD, atau tambah kata domain politik yang
memang tidak ada di InSet (dicatat sebagai modifikasi, bukan diam-diam).

=== VALIDASI MANUAL ===
File validasi_manual.csv adalah SATU-SATUNYA cara mengukur kualitas sentimen
yang sebenarnya. Isi kolom `label_manual` bertiga (jangan saling lihat dulu),
baru bandingkan. Angka kecocokannya yang masuk laporan -- bukan akurasi SVM.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LEXICON_DIR = ROOT / "lexicon"
OUT_DIR = ROOT / "data" / "processed"

# Ambang batas. 0 = aturan polos (skor>0 positif). Naikkan kalau kelas netral
# kebanyakan sampah. Nilai yang dipakai WAJIB dicatat di laporan.
THRESHOLD = 0

N_VALIDASI = 100  # berapa tweet yang diambil untuk dilabeli tangan

LABEL = ["positif", "netral", "negatif"]

# ==============================================================================
# KAMUS MINI BAWAAN -- HANYA UNTUK MODE --demo
# ==============================================================================
# INI BUKAN InSet. Isinya segelintir kata, ditulis tangan, TIDAK boleh dipakai
# untuk hasil akhir dan tidak boleh disitasi di laporan.
#
# Gunanya cuma satu: membuktikan pipeline Tahap 2 jalan dari ujung ke ujung
# HARI INI, sebelum InSet sempat di-download. Cakupannya sengaja dibikin
# BOLONG (kira-kira separuh kosakata) supaya angka OOV yang muncul mirip
# kondisi nyata -- kalau kamus demo-nya lengkap, masalah kelas netral justru
# tidak akan kelihatan dan pengujiannya jadi tidak ada artinya.
#
# Mode --demo menulis ke berkas *_demo.csv, jadi tidak mungkin tertukar dengan
# hasil asli.
LEXICON_DEMO = {
    # --- positif ---
    "dukung": 4, "optimis": 4, "bangga": 5, "semangat": 3, "amanah": 4,
    "sukses": 4, "harap": 3, "percaya": 3, "hormat": 3, "apresiasi": 4,
    "lancar": 2, "solid": 3, "tegas": 2, "berani": 3, "mantap": 4,
    "salut": 4, "damai": 3, "satu": 1, "wibawa": 3, "gagah": 2,
    "selamat": 3, "megah": 2, "khidmat": 3,
    # --- negatif ---
    "kecewa": -4, "tolak": -4, "ragu": -3, "khawatir": -3, "pesimis": -4,
    "kritik": -2, "protes": -3, "gagal": -4, "bohong": -5, "boros": -3,
    "mahal": -2, "susah": -3, "muak": -5, "sindir": -2, "korupsi": -5,
    "elit": -1, "basi": -3, "gemuk": -2, "utang": -2, "nepotisme": -4,
    "oligarki": -3, "pemborosan": -3, "defisit": -2,
}


# ------------------------------------------------------------------ helper

def baca_lexicon(demo: bool) -> dict:
    """Baca InSet dari lexicon/, atau kamus mini bawaan kalau mode demo."""
    if demo:
        print("  MODE DEMO -- pakai kamus mini bawaan (BUKAN InSet, jangan disitasi)")
        print(f"  {len(LEXICON_DEMO)} kata "
              f"({sum(1 for v in LEXICON_DEMO.values() if v > 0)} positif, "
              f"{sum(1 for v in LEXICON_DEMO.values() if v < 0)} negatif)")
        return dict(LEXICON_DEMO)

    lex: dict[str, float] = {}
    ketemu = False
    for nama in ("positive.tsv", "negative.tsv"):
        path = LEXICON_DIR / nama
        if not path.exists():
            continue
        ketemu = True
        n = 0
        with path.open(encoding="utf-8") as f:
            for baris in f:
                bagian = baris.rstrip("\n").split("\t")
                if len(bagian) < 2:
                    continue
                kata, bobot = bagian[0].strip().lower(), bagian[1].strip()
                # DIJUMLAH, bukan ditimpa. 1.143 kata InSet ada di KEDUA
                # daftar ("menang" +4 dan -5, "sangat" +3 dan -5). Versi lama
                # memakai `lex[kata] = bobot`, jadi negative.tsv yang dibaca
                # belakangan selalu menang: "menang" jadi -5, bukan -1. Di data
                # asli itu mendorong porsi negatif ke 75% tanpa satu pun
                # peringatan. Bobot bersih = jumlah keduanya, sesuai InSet.
                try:
                    lex[kata] = lex.get(kata, 0.0) + float(bobot)
                    n += 1
                except ValueError:
                    continue
        print(f"  baca {nama:<16} {n:>6,} kata")

    if not ketemu or not lex:
        raise SystemExit(
            "Kamus tidak ketemu di lexicon/.\n\n"
            "  Download InSet: https://github.com/fajri91/InSet\n"
            "  Taruh positive.tsv & negative.tsv di folder lexicon/.\n\n"
            "  Mau menguji pipeline dulu tanpa InSet?  python src/labeling.py --demo"
        )
    return lex


def skor_teks(teks: str, lex: dict) -> tuple:
    """Kembalikan (skor, jumlah kata yang ketemu di kamus)."""
    total, ketemu = 0.0, 0
    for w in str(teks).split():
        b = lex.get(w)
        if b is not None:
            total += b
            ketemu += 1
    return total, ketemu


def beri_label(skor: float) -> str:
    if skor > THRESHOLD:
        return "positif"
    if skor < -THRESHOLD:
        return "negatif"
    return "netral"


def tabel_silang(df: pd.DataFrame, asli: str, tebak: str, judul: str) -> None:
    """Cetak tabel silang + akurasi per kelas. Dipakai untuk mengukur lexicon."""
    ct = pd.crosstab(df[asli], df[tebak]).reindex(index=LABEL, columns=LABEL).fillna(0).astype(int)
    benar = sum(ct.loc[k, k] for k in LABEL)
    print(f"\n  {judul}")
    print("  " + "-" * 62)
    print("  %-12s %10s %10s %10s %9s" % ("asli \\ tebak", *LABEL, "recall"))
    for k in LABEL:
        n = ct.loc[k].sum()
        rec = ct.loc[k, k] / n * 100 if n else 0
        print("  %-12s %10s %10s %10s %8.1f%%" % (k, *[f"{ct.loc[k, c]:,}" for c in LABEL], rec))
    print("  %-12s %10s %10s %10s" % ("precision",
          *[f"{ct[c][c] / ct[c].sum() * 100:.1f}%" if ct[c].sum() else "-" for c in LABEL]))
    print("  " + "-" * 62)
    print(f"  Kecocokan keseluruhan: {benar / len(df) * 100:.1f}%  ({benar:,}/{len(df):,})")


# ---------------------------------------------------------------------- main

def main() -> None:
    demo = "--demo" in sys.argv
    akhiran = "_demo" if demo else ""
    in_path = OUT_DIR / f"tweets_clean{akhiran}.csv"
    out_path = OUT_DIR / f"tweets_labeled{akhiran}.csv"
    val_path = OUT_DIR / f"validasi_manual{akhiran}.csv"

    if not in_path.exists():
        raise SystemExit(
            f"{in_path.name} tidak ketemu.\n"
            f"  Jalankan dulu: python src/preprocess.py{' --demo' if demo else ''}"
        )

    print()
    lex = baca_lexicon(demo)
    df = pd.read_csv(in_path)
    df["teks_bersih"] = df["teks_bersih"].fillna("").astype(str)
    print(f"  baca {in_path.name:<28} {len(df):>7,} baris")

    hasil = df["teks_bersih"].map(lambda t: skor_teks(t, lex))
    df["skor"] = [h[0] for h in hasil]
    df["kata_ketemu"] = [h[1] for h in hasil]
    df["sentimen"] = df["skor"].map(beri_label)

    # ---------------- diagnosa: OOV ----------------
    oov = df["kata_ketemu"].eq(0)
    n_oov = int(oov.sum())
    netral = df["sentimen"].eq("netral")
    oov_dalam_netral = int((oov & netral).sum())

    print()
    print("  HASIL LABELING")
    print("  " + "-" * 62)
    for k in LABEL:
        n = int(df["sentimen"].eq(k).sum())
        print("  %-10s %8s  %5.1f%%" % (k, f"{n:,}", n / len(df) * 100))
    print("  " + "-" * 62)
    print("  Rata-rata kata kamus per tweet: %.2f" % df["kata_ketemu"].mean())

    print()
    print("  !! DIAGNOSA KELAS NETRAL (ini yang masuk Discussion)")
    print("  " + "-" * 62)
    print(f"  Tweet tanpa SATU PUN kata kamus : {n_oov:,} ({n_oov / len(df) * 100:.1f}%)")
    if netral.sum():
        print(f"  Porsi kelas netral yang isinya   : {oov_dalam_netral:,} dari "
              f"{int(netral.sum()):,} ({oov_dalam_netral / netral.sum() * 100:.1f}%)")
        print("  tweet tanpa kata kamus sama sekali")
    print()
    if n_oov / len(df) > 0.25:
        print("  BACA INI: lebih dari seperempat tweet tidak punya kata kamus, jadi")
        print("  dilempar ke netral bukan karena isinya netral, tapi karena kamusnya")
        print("  tidak mengenali kosakatanya. Kelas netral di sini TIDAK BISA diklaim")
        print("  sebagai 'opini netral'. Tulis batasan ini terang-terangan di laporan.")
    else:
        print("  Cakupan kamus lumayan, tapi tetap sebutkan angka ini di Methodology.")

    # ---------------- kalau ada kunci jawaban (mode uji) ----------------
    if "_kunci" in df.columns:
        tabel_silang(df, "_kunci", "sentimen",
                     "UJI: seberapa jauh lexicon memulihkan sentimen sebenarnya?")
        print()
        print("  " + "=" * 62)
        print("  ANGKA DI ATAS TIDAK BOLEH MASUK LAPORAN.")
        print("  " + "=" * 62)
        print("  Ini data uji karangan, dan kamus demo-nya disusun dari kosakata")
        print("  yang sama persis dengan yang dipakai generator. Jadi kamusnya")
        print("  'sudah tahu jawabannya' -- pengujiannya sirkular. Kecocokan")
        print("  setinggi ini MUSTAHIL terjadi di data asli; lexicon Bahasa")
        print("  Indonesia pada tweet politik biasanya jatuh jauh di bawah ini.")
        print()
        print("  Yang DIBUKTIKAN tabel ini cuma satu: pipeline-nya jalan benar")
        print("  dari ujung ke ujung. Bukan bahwa labeling-nya akurat.")
        print()
        print("  Satu-satunya angka yang sah dikutip adalah hasil validasi manual")
        print("  di data asli. Pola kualitatifnya yang perlu diperhatikan:")
        print("  recall kelas NETRAL paling rendah di antara ketiganya -- itu yang")
        print("  akan terulang di data asli, dan biasanya jauh lebih parah.")

    # ---------------- berkas validasi manual ----------------
    contoh = df.sample(min(N_VALIDASI, len(df)), random_state=42)
    validasi = pd.DataFrame({
        "no": range(1, len(contoh) + 1),
        "tanggal": contoh["tanggal"].values,
        "teks_asli": contoh["teks_asli"].values if "teks_asli" in contoh else contoh["teks_bersih"].values,
        "label_lexicon": contoh["sentimen"].values,
        "skor_lexicon": contoh["skor"].values,
        "label_manual_1": "",
        "label_manual_2": "",
        "label_manual_3": "",
    })
    validasi.to_csv(val_path, index=False, encoding="utf-8")

    kolom_simpan = [c for c in df.columns if c not in ("skor", "kata_ketemu")]
    df[kolom_simpan].to_csv(out_path, index=False, encoding="utf-8")

    print()
    print(f"OK  {len(df):,} baris dilabeli -> {out_path}")
    print(f"    {len(validasi)} tweet untuk validasi manual -> {val_path}")
    print()
    print("    TUGAS BERTIGA: buka validasi_manual.csv, isi label_manual_1/2/3")
    print("    (positif/netral/negatif) TANPA melihat kolom label_lexicon dulu.")
    print("    Angka kecocokannya yang masuk laporan -- bukan akurasi SVM.")
    print()
    print(f"    Lanjut:  python src/train_model.py{' --demo' if demo else ''}")


if __name__ == "__main__":
    main()
