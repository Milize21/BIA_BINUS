"""
train_model.py -- TAHAP 2c: latih SVM, bikin confusion matrix, tulis dataset final.

INPUT   : data/processed/tweets_labeled.csv   (hasil labeling.py)
OUTPUT  : data/processed/dataset_final.csv    <-- 7 KOLOM KONTRAK, dibaca dashboard
          data/model/confusion_matrix.png     <-- dipajang di tab "Evaluasi Model"
          data/model/metrics.json             <-- accuracy / precision / recall / F1

    python src/train_model.py           # tulis dataset_final.csv (DIPAKAI DASHBOARD)
    python src/train_model.py --demo    # tulis dataset_demo.csv + demo_*.png/json

=== MODE DEMO TIDAK AKAN PERNAH MENIMPA dataset_final.csv ===
Disengaja. Begitu dataset_final.csv ada, dashboard langsung berhenti memakai
data dummy dan banner peringatannya hilang. Kalau mode uji boleh menulis ke
sana, seluruh pengaman itu jebol dan bisa-bisa data karangan yang dipresentasikan.

=== BACA INI SEBELUM MENULIS ANGKA DI LAPORAN ===
Label dari labeling.py itu hasil lexicon, BUKAN label manusia. Jadi SVM di sini
sedang belajar MENIRU KAMUS. Akurasinya biasanya tinggi (85-95%) dan itu BUKAN
prestasi -- itu cuma bukti SVM berhasil meniru aturan kamus.

  ✅ "Model mencapai akurasi X% dalam mereplikasi pelabelan berbasis lexicon."
  ❌ "Model mendeteksi sentimen publik dengan akurasi X%."

Batas atas kualitasnya ditentukan oleh kualitas lexicon. Angka yang benar-benar
mengukur kualitas sentimen adalah validasi manual 100 tweet (lihat labeling.py).

=== KOLOM `sentimen` DI dataset_final.csv ===
Dipakai label LEXICON untuk SEMUA baris, bukan prediksi SVM. Alasannya: label
lexicon tersedia untuk seluruh data, sementara prediksi SVM cuma sah untuk data
uji (20%). Memakai prediksi SVM pada data yang dia latih sendiri = kebocoran
data, dan dashboard jadi menampilkan angka yang lebih bagus dari kenyataan.
SVM di sini perannya komponen evaluasi/pemodelan, bukan pelabel ulang.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # wajib: tidak ada GUI di sini

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parents[1]
PROC_DIR = ROOT / "data" / "processed"
MODEL_DIR = ROOT / "data" / "model"

KOLOM_KONTRAK = ["tanggal", "periode", "teks_bersih", "sentimen", "likes", "retweet", "username"]
LABEL = ["negatif", "netral", "positif"]
RANDOM_STATE = 42

WARNA = {"negatif": "#D64550", "netral": "#9AA0A6", "positif": "#2E9E5B"}


# ------------------------------------------------------------------ helper

def gambar_confusion_matrix(cm: np.ndarray, path: Path, judul: str) -> None:
    """
    Confusion matrix untuk dipajang di dashboard & appendix laporan.

    Tiap sel menampilkan JUMLAH dan PERSENTASE-PER-BARIS (recall). Persentase
    per baris dipilih, bukan per total, karena pertanyaan yang ingin dijawab
    adalah "dari semua tweet yang sebenarnya negatif, berapa yang tertebak
    benar?" -- dan itu recall.
    """
    per_baris = cm / cm.sum(axis=1, keepdims=True).clip(min=1) * 100

    fig, ax = plt.subplots(figsize=(6.6, 5.6))
    im = ax.imshow(per_baris, cmap="Blues", vmin=0, vmax=100)

    ax.set_xticks(range(len(LABEL)), [l.capitalize() for l in LABEL])
    ax.set_yticks(range(len(LABEL)), [l.capitalize() for l in LABEL])
    ax.set_xlabel("Prediksi model", fontsize=11, labelpad=10)
    ax.set_ylabel("Label lexicon (acuan)", fontsize=11, labelpad=10)
    ax.set_title(judul, fontsize=12, pad=14)

    for i in range(len(LABEL)):
        for j in range(len(LABEL)):
            ax.text(j, i, f"{cm[i, j]:,}\n{per_baris[i, j]:.1f}%",
                    ha="center", va="center", fontsize=11,
                    color="white" if per_baris[i, j] > 55 else "#222")

    cb = fig.colorbar(im, ax=ax, shrink=0.82)
    cb.set_label("% dari baris (recall)", fontsize=10)
    ax.set_xticks(np.arange(-0.5, len(LABEL)), minor=True)
    ax.set_yticks(np.arange(-0.5, len(LABEL)), minor=True)
    ax.grid(which="minor", color="white", linewidth=2)
    ax.tick_params(which="minor", length=0)

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)


def kata_paling_menentukan(vec: TfidfVectorizer, clf: LinearSVC, n: int = 10) -> dict:
    """
    Kata dengan bobot terbesar per kelas menurut SVM.

    Berguna dua hal: (1) bahan interpretasi di laporan -- model ini sebenarnya
    memutuskan berdasarkan kata apa, dan (2) pemeriksaan kewarasan. Kalau kata
    yang mendorong kelas 'positif' ternyata terasa negatif, berarti ada yang
    salah di labeling, bukan di model.
    """
    nama = np.array(vec.get_feature_names_out())
    keluar = {}
    for i, kelas in enumerate(clf.classes_):
        koef = clf.coef_[i] if clf.coef_.shape[0] > 1 else clf.coef_[0]
        urut = np.argsort(koef)[::-1][:n]
        keluar[str(kelas)] = [[str(nama[j]), round(float(koef[j]), 4)] for j in urut]
    return keluar


# ---------------------------------------------------------------------- main

def main() -> None:
    demo = "--demo" in sys.argv
    akhiran = "_demo" if demo else ""

    in_path = PROC_DIR / f"tweets_labeled{akhiran}.csv"
    # Mode demo TIDAK PERNAH menulis dataset_final.csv -- lihat docstring.
    out_dataset = PROC_DIR / ("dataset_demo.csv" if demo else "dataset_final.csv")
    out_cm = MODEL_DIR / ("demo_confusion_matrix.png" if demo else "confusion_matrix.png")
    out_metrics = MODEL_DIR / ("demo_metrics.json" if demo else "metrics.json")

    if not in_path.exists():
        raise SystemExit(
            f"{in_path.name} tidak ketemu.\n"
            f"  Jalankan dulu: python src/labeling.py{' --demo' if demo else ''}"
        )

    print()
    if demo:
        print("  MODE DEMO -- menulis ke dataset_demo.csv / demo_*.png / demo_*.json")
        print("  dataset_final.csv TIDAK disentuh, jadi dashboard tetap pakai dummy.")
        print()

    df = pd.read_csv(in_path)
    df["teks_bersih"] = df["teks_bersih"].fillna("").astype(str)
    print(f"  baca {in_path.name:<30} {len(df):>7,} baris")

    X_teks, y = df["teks_bersih"], df["sentimen"]
    print(f"  distribusi kelas: {y.value_counts().to_dict()}")

    # --- 1. split DULU, baru fit TF-IDF -------------------------------------
    # Urutannya penting: TF-IDF di-fit HANYA pada data latih. Kalau di-fit ke
    # seluruh data sebelum split, informasi dari data uji (kosakata & bobot IDF)
    # bocor ke model, dan skornya jadi lebih bagus dari yang sebenarnya.
    X_latih_teks, X_uji_teks, y_latih, y_uji = train_test_split(
        X_teks, y,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=y,          # WAJIB: kelas netral minoritas, jangan sampai timpang
    )

    vec = TfidfVectorizer(
        ngram_range=(1, 2),  # unigram + bigram: "tidak becus" beda makna dari "becus"
        min_df=2,            # buang kata yang cuma muncul sekali (noise)
        sublinear_tf=True,
    )
    X_latih = vec.fit_transform(X_latih_teks)
    X_uji = vec.transform(X_uji_teks)
    print(f"  fitur TF-IDF: {X_latih.shape[1]:,} "
          f"(latih {X_latih.shape[0]:,} / uji {X_uji.shape[0]:,})")

    # --- 2. latih ------------------------------------------------------------
    t0 = time.time()
    clf = LinearSVC(
        C=1.0,
        class_weight="balanced",  # kelas netral minoritas -- tanpa ini recall-nya anjlok
        random_state=RANDOM_STATE,
        max_iter=5000,
    )
    clf.fit(X_latih, y_latih)
    print(f"  latih LinearSVC selesai dalam {time.time() - t0:.1f} detik")

    # --- 3. evaluasi ---------------------------------------------------------
    y_prediksi = clf.predict(X_uji)

    print()
    print(classification_report(y_uji, y_prediksi, labels=LABEL, digits=3, zero_division=0))

    cm = confusion_matrix(y_uji, y_prediksi, labels=LABEL)
    gambar_confusion_matrix(
        cm, out_cm,
        ("[DEMO] " if demo else "") + "Confusion Matrix — SVM vs label lexicon",
    )

    # Cross-validation: satu split bisa kebetulan bagus/jelek. 5-fold memberi
    # gambaran seberapa stabil hasilnya. Dilaporkan sebagai rata-rata ± simpangan.
    #
    # WAJIB pakai Pipeline, JANGAN memvektorkan seluruh data lalu di-CV.
    # Dua alasan, dua-duanya pernah kejadian di file ini:
    #   1. Kebocoran data. TF-IDF yang di-fit ke seluruh data membuat setiap
    #      fold "mengintip" kosakata & bobot IDF milik fold uji -> skor CV
    #      lebih bagus dari yang sebenarnya. Pipeline mem-fit ulang vectorizer
    #      di dalam tiap fold, sebagaimana mestinya.
    #   2. `vec` di atas sudah di-fit pada DATA LATIH dan `clf` memakai indeks
    #      fitur miliknya. Mem-fit ulang `vec` ke seluruh data akan mengubah
    #      kosakatanya, sehingga clf.coef_ tidak lagi sejajar dengan
    #      get_feature_names_out() -- daftar "kata paling menentukan" berubah
    #      jadi kata acak. (Terukur: hanya 5 dari 11.402 indeks yang masih cocok.)
    print("  Cross-validation 5-fold (macro-F1, vectorizer di-fit ulang tiap fold) ...")
    pipa = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
        LinearSVC(C=1.0, class_weight="balanced", random_state=RANDOM_STATE, max_iter=5000),
    )
    cv = cross_val_score(
        pipa, X_teks, y,
        cv=StratifiedKFold(5, shuffle=True, random_state=RANDOM_STATE),
        scoring="f1_macro",
    )
    print(f"  macro-F1 = {cv.mean():.3f} +/- {cv.std():.3f}   (per fold: "
          + ", ".join(f"{s:.3f}" for s in cv) + ")")

    metrik = {
        "accuracy": float(accuracy_score(y_uji, y_prediksi)),
        "precision": float(precision_score(y_uji, y_prediksi, average="macro", zero_division=0)),
        "recall": float(recall_score(y_uji, y_prediksi, average="macro", zero_division=0)),
        "f1": float(f1_score(y_uji, y_prediksi, average="macro", zero_division=0)),
        "f1_macro_cv_mean": float(cv.mean()),
        "f1_macro_cv_std": float(cv.std()),
        "n_latih": int(X_latih.shape[0]),
        "n_uji": int(X_uji.shape[0]),
        "n_fitur": int(X_latih.shape[1]),
        "per_kelas": classification_report(
            y_uji, y_prediksi, labels=LABEL, output_dict=True, zero_division=0
        ),
        "kata_paling_menentukan": kata_paling_menentukan(vec, clf),
        "catatan": (
            "Label acuan berasal dari lexicon, bukan manusia. Angka di sini "
            "mengukur kemampuan SVM MEREPLIKASI pelabelan lexicon, bukan "
            "kemampuan mendeteksi sentimen. Lihat validasi_manual.csv untuk "
            "angka kualitas sentimen yang sebenarnya."
        ),
        "mode": "demo (data karangan)" if demo else "produksi",
    }
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out_metrics.write_text(json.dumps(metrik, indent=2, ensure_ascii=False), encoding="utf-8")

    # --- 4. kelas paling lemah ----------------------------------------------
    per_kelas = metrik["per_kelas"]
    terlemah = min(LABEL, key=lambda k: per_kelas[k]["recall"])
    print()
    print(f"  Kelas paling lemah: {terlemah.upper()} "
          f"(recall {per_kelas[terlemah]['recall']:.1%}, "
          f"F1 {per_kelas[terlemah]['f1-score']:.1%})")
    if terlemah == "netral":
        print("  Sudah diduga sejak awal (PLAN.md keputusan #6). Bahas jujur di")
        print("  Discussion sebagai limitation -- penyebabnya ada di labeling.py,")
        print("  bukan di SVM: tweet tanpa kata kamus semuanya dilempar ke netral.")

    print()
    print("  Kata paling menentukan menurut model:")
    for kelas, kata in metrik["kata_paling_menentukan"].items():
        print(f"    {kelas:<9}: " + ", ".join(k for k, _ in kata[:8]))

    # --- 5. tulis dataset final (7 kolom kontrak) ---------------------------
    kurang = [k for k in KOLOM_KONTRAK if k not in df.columns]
    if kurang:
        raise SystemExit(f"Kolom kontrak hilang dari {in_path.name}: {', '.join(kurang)}")
    final = df[KOLOM_KONTRAK].sort_values("tanggal")
    final.to_csv(out_dataset, index=False, encoding="utf-8")

    print()
    print(f"OK  {out_dataset.name:<22} {len(final):>7,} baris, 7 kolom kontrak")
    print(f"    {out_cm.name}")
    print(f"    {out_metrics.name}")
    if demo:
        print()
        print("    Ini hasil UJI. dataset_final.csv belum ada, dashboard masih dummy.")
        print("    Untuk hasil sungguhan: scraping -> preprocess -> labeling (InSet)")
        print("    -> train_model.py TANPA --demo.")
    else:
        print()
        print("    Dashboard otomatis pindah ke data asli. Banner merah hilang sendiri.")
        print("    Cek: streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
