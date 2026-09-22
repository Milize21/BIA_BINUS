# Analisis Sentimen Pelantikan Prabowo-Gibran

Dashboard analitik untuk membaca **pergerakan sentimen publik di X** seputar pelantikan Presiden & Wakil Presiden RI, 20 Oktober 2024 — dari H-30, Hari-H, sampai H+30.

> **Group Project AOL — ISYS8036042 Business Intelligence and Analytics (MMSI)**
> Kelompok 04 · Bintang Eko Ramadhan · Kevin Naufaldi · Stefanus Aloysius Gonzaga

Fokusnya bukan sekadar menghitung positif/negatif, tapi **perubahannya**: apakah dukungan yang melonjak di hari pelantikan bertahan, atau menguap begitu agenda pemerintahan mulai dibahas.

**Untuk siapa:** pengamat pemerintahan dan media/jurnalis yang perlu membaca opini publik dengan cepat, tanpa menunggu survei tradisional yang lama dan mahal.

---

## Cara menjalankan

### Klik dua kali

| Sistem | Berkas |
|---|---|
| Windows | `JALANKAN.bat` |
| macOS | `JALANKAN.command` |

Keduanya mengerjakan hal yang sama: memeriksa enam kebutuhan, memasang sendiri yang kurang, lalu menampilkan menu untuk menjalankan dashboard atau pipeline. **Tidak perlu memasang Python lebih dulu** — kalau belum ada, dipasang otomatis lewat [uv](https://docs.astral.sh/uv/).

Di macOS, kalau klik dua kali tidak menghasilkan apa-apa, biasanya satu dari dua hal ini — dua-duanya cuma sekali di awal:

```bash
chmod +x JALANKAN.command                      # izin eksekusi hilang
xattr -d com.apple.quarantine JALANKAN.command # proyek diunduh sebagai ZIP
```

Yang kedua hanya terjadi kalau proyeknya diunduh sebagai ZIP. Kalau di-`git clone`, macOS tidak menandainya karantina.

### Manual (Linux / yang suka terminal)

```bash
uv python install 3.12
uv venv --python 3.12 --seed
uv pip install -r requirements.txt

python src/make_dummy.py              # data contoh untuk dashboard
streamlit run dashboard/app.py
```

Dashboard terbuka di `http://localhost:8501`.

---

## Status

| Bagian | Status |
|---|---|
| Dashboard Streamlit — 6 tab, 16 chart | **selesai** |
| Tahap 2: preprocessing, labeling, SVM | **selesai & teruji ujung-ke-ujung** |
| `src/scrape.py` — pengambilan data dari X | **belum** — satu-satunya penghambat |
| Kamus InSet di `lexicon/` | **perlu diunduh manual**, lihat di bawah |

### Dashboard masih memakai data contoh

Selama `data/processed/dataset_final.csv` belum ada, dashboard memakai **data karangan** dari `src/make_dummy.py` dan menampilkan **banner merah besar** di paling atas halaman.

Banner itu hilang sendiri begitu data asli masuk — tidak ada berkas yang perlu diganti namanya. Jangan dihapus: itu satu-satunya pengaman supaya tidak ada yang mempresentasikan data bohongan.

---

## Isi dashboard

| Tab | Isi |
|---|---|
| Ringkasan | Net Sentiment Score per periode, narasi otomatis dari data, slope chart pergeseran |
| Distribusi | Bar per periode + uji **chi-square, p-value, Cramér's V**, tabel kontingensi vs frekuensi harapan |
| Tren Waktu | Area bertumpuk harian, Net Sentiment + rata-rata 7 hari, heatmap jam × hari |
| Analisis Teks | Word cloud & 15 kata teratas per sentimen, **kata khas tiap periode**, kata pembeda positif vs negatif |
| Viralitas & Akun | Bubble likes×retweet, sebaran engagement, sentimen mana yang menyebar lebih jauh, akun paling berpengaruh |
| Evaluasi Model | Confusion matrix + metrik, terisi otomatis begitu model dilatih |

---

## Alur data

```
[1] SCRAPING          [2] OLAH                          [3] FINAL            [4] DASHBOARD
    X (Selenium)  ->  bersihkan -> labeli -> latih  ->  dataset_final.csv -> Streamlit
    CSV mentah        preprocess  labeling  train       7 kolom kontrak      baca berkas saja
```

Tahap 1–3 berjalan **offline, sekali jalan**. Dashboard hanya **membaca** berkas — tidak ada scraping atau pelatihan model saat halaman dibuka, supaya cepat dibuka waktu presentasi.

### Menguji Tahap 2 tanpa data asli

```bash
python src/make_dummy_raw.py        # CSV mentah yang sengaja dibikin KOTOR
python src/preprocess.py  --demo
python src/labeling.py    --demo
python src/train_model.py --demo
```

Rantai penuh sekitar 15 detik. Data mentahnya ditanami URL, @mention, emoji, slang, kata berimbuhan, duplikat, akun buzzer, dan tweet kepotong `… Show more` — karena preprocessing yang cuma diuji pakai teks rapi itu tidak teruji sama sekali.

Semua keluaran mode uji berakhiran `_demo`, dan **tidak akan pernah menulis `dataset_final.csv`**.

> **Angka dari mode uji tidak boleh masuk laporan.** Kamus mini bawaannya disusun dari kosakata yang sama dengan generator datanya, jadi pengujiannya sirkular. Yang dibuktikan cuma satu: pipeline-nya jalan benar.

---

## Kamus InSet

Labeling data asli memakai **InSet (Indonesia Sentiment Lexicon)** — Koto & Rahmaningtyas. Unduh dari [github.com/fajri91/InSet](https://github.com/fajri91/InSet), taruh `positive.tsv` dan `negative.tsv` di folder `lexicon/`.

Kamusnya sengaja tidak ikut di-commit, dan **tidak boleh dikarang sendiri** — hasil labeling yang kamusnya karangan tidak bisa dipertanggungjawabkan, dan sitasi InSet wajib masuk References.

---

## Struktur

```
JALANKAN.bat               <- pemeriksa kebutuhan + peluncur (Windows)
JALANKAN.command           <- padanannya untuk macOS
requirements.txt
dashboard/app.py           <- Streamlit
src/
  scrape.py                <- tahap 1 (belum jadi)
  preprocess.py            <- tahap 2a: bersihkan + preprocessing teks
  labeling.py              <- tahap 2b: labeling berbasis lexicon
  train_model.py           <- tahap 2c: SVM + confusion matrix
  make_dummy.py            <- data contoh untuk dashboard
  make_dummy_raw.py        <- data mentah kotor untuk menguji tahap 2
data/{raw,processed,model}/
lexicon/                   <- InSet, unduh sendiri
```

Dokumen perencanaan internal kelompok — keputusan, pembagian kerja, dan pemetaan ke rubrik — disimpan terpisah dan tidak ikut dipublikasikan di sini.

Penjelasan tiap tahap ada di **docstring masing-masing berkas** di `src/`: alur masuk-keluar, alasan urutannya begitu, dan jebakan yang harus diwaspadai. Baca itu dulu sebelum menyentuh kodenya.

---

## Tumpukan teknologi

Python 3.12 · Streamlit · Plotly · pandas · scikit-learn · Sastrawi · WordCloud · Selenium · uv
