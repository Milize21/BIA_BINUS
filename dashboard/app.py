"""
app.py -- TAHAP 4: dashboard Streamlit.

PLAN.md bagian 6 langkah 1-7 terpasang. Sisa langkah 8 (screenshot + deploy),
dan itu baru boleh dikerjakan setelah dataset_final.csv masuk.

Jalankan:
    streamlit run dashboard/app.py

Dashboard ini HANYA MEMBACA file. Tidak ada scraping/training di sini
(PLAN.md bagian 4) -- supaya buka dashboard-nya instan pas presentasi.

=== SOAL DUMMY vs FINAL ===
load_data() otomatis milih dataset_final.csv kalau sudah ada, dan jatuh ke
dataset_dummy.csv kalau belum. Tidak perlu ganti nama file pas merge. Selama
masih dummy ada banner merah di paling atas -- JANGAN dihapus, itu satu-satunya
pengaman supaya tidak ada yang presentasi pakai data bohongan.

=== SEMUA ANGKA DITURUNKAN DARI 7 KOLOM KONTRAK ===
Tidak ada kolom tambahan yang diminta ke Jalur A. Kolom bantu (jam, hari,
hari_minggu, jml_kata, amplifikasi) semuanya dihitung di load_data() dari 7
kolom yang sudah disepakati di PLAN.md bagian 3.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy.stats import chi2_contingency
from wordcloud import WordCloud

# --------------------------------------------------------------------- setup

ROOT = Path(__file__).resolve().parents[1]
PATH_FINAL = ROOT / "data" / "processed" / "dataset_final.csv"
PATH_DUMMY = ROOT / "data" / "processed" / "dataset_dummy.csv"
PATH_CM = ROOT / "data" / "model" / "confusion_matrix.png"
PATH_METRICS = ROOT / "data" / "model" / "metrics.json"

# Kontrak dataset -- PLAN.md bagian 3. Jangan diubah sepihak.
KOLOM_KONTRAK = ["tanggal", "periode", "teks_bersih", "sentimen", "likes", "retweet", "username"]
URUTAN_PERIODE = ["sebelum", "hari-h", "sesudah"]
URUTAN_SENTIMEN = ["positif", "netral", "negatif"]

LABEL_PERIODE = {
    "sebelum": "Sebelum (H-30)",
    "hari-h": "Hari-H (20 Okt)",
    "sesudah": "Sesudah (H+30)",
}
HARI_MINGGU = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

# Warna sentimen. Satu definisi dipakai SEMUA chart biar konsisten
# -- termasuk pas di-screenshot buat laporan.
WARNA_SENTIMEN = {"positif": "#2E9E5B", "netral": "#9AA0A6", "negatif": "#D64550"}
WARNA_PERIODE = {"sebelum": "#7B8794", "hari-h": "#1F6FEB", "sesudah": "#B45309"}

TANGGAL_HARI_H = "2024-10-20"

# Jaring pengaman word cloud. teks_bersih SEHARUSNYA sudah bebas stopword dari
# preprocess.py, tapi kalau ada yang bocor, jangan sampai word cloud didominasi
# kata sambung. Ini pengaman, BUKAN pengganti stopword removal di preprocess.py.
STOPWORD_CADANGAN = {
    "yang", "dan", "di", "ini", "itu", "dengan", "untuk", "dari", "ke", "pada",
    "adalah", "akan", "tidak", "ada", "juga", "sudah", "saya", "kita", "mereka",
    "nya", "nih", "sih", "aja", "gak", "ga", "kalo", "kalau", "biar", "kok",
    "https", "http", "co", "amp", "rt",
}

st.set_page_config(
    page_title="Sentimen Pelantikan Prabowo-Gibran",
    page_icon="🇮🇩",
    layout="wide",
)


# ---------------------------------------------------------------- muat data

@st.cache_data
def load_data() -> tuple[pd.DataFrame, bool]:
    """Baca dataset. Pilih final kalau ada, kalau tidak pakai dummy."""
    pakai_dummy = not PATH_FINAL.exists()
    path = PATH_DUMMY if pakai_dummy else PATH_FINAL

    if not path.exists():
        st.error(
            f"Dataset tidak ketemu: `{path.relative_to(ROOT)}`\n\n"
            "Bikin dulu data dummy-nya:  `python src/make_dummy.py`"
        )
        st.stop()

    df = pd.read_csv(path)

    # Cek kontrak 7 kolom -- jaring pengaman pas merge dummy -> final.
    kurang = [k for k in KOLOM_KONTRAK if k not in df.columns]
    if kurang:
        st.error(
            f"`{path.name}` melanggar KONTRAK DATASET (PLAN.md bagian 3).\n\n"
            f"Kolom yang hilang: `{'`, `'.join(kurang)}`\n\n"
            f"Kolom yang ada: `{'`, `'.join(df.columns)}`"
        )
        st.stop()

    df["tanggal"] = pd.to_datetime(df["tanggal"])
    df["likes"] = pd.to_numeric(df["likes"], errors="coerce").fillna(0).astype(int)
    df["retweet"] = pd.to_numeric(df["retweet"], errors="coerce").fillna(0).astype(int)
    df["teks_bersih"] = df["teks_bersih"].fillna("").astype(str)
    df["periode"] = pd.Categorical(df["periode"], categories=URUTAN_PERIODE, ordered=True)
    df["sentimen"] = pd.Categorical(df["sentimen"], categories=URUTAN_SENTIMEN, ordered=True)

    # Kolom bantu -- SEMUA diturunkan dari 7 kolom kontrak, tidak minta data baru.
    df["hari"] = df["tanggal"].dt.normalize()
    df["jam"] = df["tanggal"].dt.hour
    df["hari_minggu"] = df["tanggal"].dt.dayofweek
    df["jml_kata"] = df["teks_bersih"].str.split().str.len()
    df["engagement"] = df["likes"] + df["retweet"]
    # Rasio amplifikasi: seberapa jauh sebuah tweet MENYEBAR relatif terhadap
    # seberapa disukai. Tinggi = orang meneruskan, bukan sekadar menyukai.
    df["amplifikasi"] = df["retweet"] / df["likes"].where(df["likes"] > 0)
    return df, pakai_dummy


def tokenisasi(teks: str) -> list[str]:
    return [w for w in teks.split() if len(w) > 2 and w not in STOPWORD_CADANGAN]


@st.cache_data
def hitung_frekuensi(teks_gabungan: str) -> dict[str, int]:
    """
    Hitung frekuensi kata SEKALI, lalu dipakai bareng oleh word cloud dan bar
    "15 kata teratas".

    Penting: word cloud dan bar WAJIB berangkat dari hitungan yang sama. Kalau
    word cloud dibiarkan memakai tokenizer bawaannya sendiri (lewat .generate()),
    dua visual ini bisa menampilkan kata yang berbeda untuk data yang sama --
    dan itu memalukan kalau ketahuan pas presentasi.
    """
    return dict(Counter(tokenisasi(teks_gabungan)))


@st.cache_data
def buat_wordcloud(freq: dict[str, int], warna: str):
    """
    Word cloud dari frekuensi yang sudah dihitung, dikembalikan sebagai gambar PIL.

    Dua keputusan demi kecepatan (diukur, bukan ditebak):
      - generate_from_frequencies(), bukan generate() -> tokenisasi tidak diulang
      - .to_image() lalu st.image(), bukan lewat matplotlib -> ~4x lebih cepat
    Ukuran 1000x430 dengan max_words=90 dipilih karena 1200x520/120 makan
    ~1.8x waktu render tanpa terlihat lebih bagus di layar presentasi.
    """
    if not freq:
        return None
    wc = WordCloud(
        width=1000, height=430, background_color="white", colormap=warna,
        max_words=90,
        random_state=42,  # supaya screenshot buat laporan selalu sama
    ).generate_from_frequencies(freq)
    return wc.to_image()


@st.cache_data
def kata_khas(
    teks_kelompok: str, teks_pembanding: str, min_total: int = 20, top_n: int = 12
) -> list[tuple[str, float, int]]:
    """
    Kata yang paling MEMBEDAKAN satu kelompok dari pembandingnya.

    Metode: log rasio frekuensi relatif dengan pemulusan Laplace.

        skor(kata) = ln( p_kelompok(kata) / p_pembanding(kata) )

    Kenapa bukan sekadar "kata paling sering"? Karena kata tersering hampir
    selalu sama di semua kelompok ("pelantikan", "prabowo") -- tidak
    memberitahu apa-apa. Yang menarik justru kata yang porsinya MELONJAK di
    satu kelompok. Pemulusan +0.5 dipakai supaya kata yang muncul di satu sisi
    saja tidak menghasilkan pembagian nol.

    `min_total` menyaring kata langka: tanpa itu, kata yang cuma muncul 2 kali
    bisa mendapat skor tertinggi hanya karena kebetulan.
    """
    c1 = Counter(tokenisasi(teks_kelompok))
    c2 = Counter(tokenisasi(teks_pembanding))
    n1, n2 = sum(c1.values()), sum(c2.values())
    if not n1 or not n2:
        return []

    kosakata = [w for w in set(c1) | set(c2) if c1[w] + c2[w] >= min_total]
    if not kosakata:
        return []

    a, v = 0.5, len(kosakata)
    skor = [
        (
            w,
            math.log(((c1[w] + a) / (n1 + a * v)) / ((c2[w] + a) / (n2 + a * v))),
            c1[w],
        )
        for w in kosakata
    ]
    skor.sort(key=lambda x: -x[1])
    return skor[:top_n]


def nss(seri: pd.Series) -> float:
    """Net Sentiment Score = %positif - %negatif. Satu angka, gampang dibaca."""
    if len(seri) == 0:
        return 0.0
    p = seri.value_counts(normalize=True)
    return float((p.get("positif", 0) - p.get("negatif", 0)) * 100)


df, pakai_dummy = load_data()

# ------------------------------------------------------------------- header

st.title("Analisis Sentimen Pelantikan Prabowo-Gibran")
st.caption(
    "Pergerakan sentimen publik di X: sebelum (H-30) → Hari-H (20 Okt 2024) → sesudah (H+30) · "
    "Kelompok 04 — ISYS8036042 Business Intelligence and Analytics"
)

if pakai_dummy:
    st.error(
        "**⚠️ DATA DUMMY — BUKAN DATA ASLI.** Angka di halaman ini dikarang oleh "
        "`src/make_dummy.py` supaya dashboard bisa dibangun sambil nunggu scraping. "
        "Banner ini hilang sendiri begitu `data/processed/dataset_final.csv` ada.",
        icon="🚨",
    )

# ------------------------------------------------------ SIDEBAR: filter

with st.sidebar:
    st.header("Filter")
    pilihan = st.selectbox(
        "Periode",
        options=["semua"] + URUTAN_PERIODE,
        format_func=lambda p: "Semua periode" if p == "semua" else LABEL_PERIODE[p],
        help="Menyaring tab Analisis Teks & Viralitas. Tab Ringkasan, Distribusi "
             "dan Tren sengaja TIDAK ikut tersaring — ketiganya justru bertugas "
             "MEMBANDINGKAN antarperiode, jadi kalau difilter ke satu periode "
             "isinya malah hilang.",
    )

    min_engagement = st.slider(
        "Minimal engagement (likes + retweet)",
        0, 200, 0, step=5,
        help="Menyaring tweet sepi. Berguna untuk melihat hanya percakapan yang "
             "benar-benar menyebar. 0 = tampilkan semua.",
    )

    st.divider()
    st.caption(
        f"**Sumber data**  \n`{(PATH_DUMMY if pakai_dummy else PATH_FINAL).name}`  \n"
        f"{len(df):,} tweet · {df['username'].nunique():,} akun  \n"
        f"{df['tanggal'].min():%d %b %Y} – {df['tanggal'].max():%d %b %Y}"
    )

dff = df if pilihan == "semua" else df[df["periode"] == pilihan]
if min_engagement:
    dff = dff[dff["engagement"] >= min_engagement]

if dff.empty:
    st.warning("Tidak ada tweet yang lolos filter. Longgarkan filter di sidebar.")
    st.stop()

judul_periode = "Semua periode" if pilihan == "semua" else LABEL_PERIODE[pilihan]

# ------------------------------------------------------------------ KPI

porsi = dff["sentimen"].value_counts(normalize=True)
nss_dff = nss(dff["sentimen"])
nss_global = nss(df["sentimen"])

k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Tweet", f"{len(dff):,}", f"{len(dff) / len(df) * 100:.0f}% dari total")
k2.metric(
    "Net Sentiment", f"{nss_dff:+.1f}",
    None if pilihan == "semua" and not min_engagement else f"{nss_dff - nss_global:+.1f} vs keseluruhan",
    help="Net Sentiment Score = %positif − %negatif. Di atas 0 berarti "
         "dukungan melebihi penolakan.",
)
k3.metric("Positif", f"{porsi.get('positif', 0) * 100:.1f}%")
k4.metric("Netral", f"{porsi.get('netral', 0) * 100:.1f}%")
k5.metric("Negatif", f"{porsi.get('negatif', 0) * 100:.1f}%")
k6.metric("Median likes", f"{int(dff['likes'].median()):,}")

st.divider()

tab_ring, tab_dist, tab_tren, tab_teks, tab_viral, tab_eval = st.tabs([
    "📌 Ringkasan", "📊 Distribusi", "📈 Tren Waktu",
    "☁️ Analisis Teks", "🔥 Viralitas & Akun", "🎯 Evaluasi Model",
])

# ====================================================== TAB 1 — RINGKASAN
with tab_ring:
    st.markdown("#### Tiga periode, satu angka")
    st.caption(
        "**Net Sentiment Score = %positif − %negatif.** Satu angka yang bisa "
        "dibandingkan langsung antarperiode. Tab ini sengaja tidak ikut filter "
        "sidebar — tugasnya membandingkan ketiganya."
    )

    ringkas = (
        df.groupby("periode", observed=False)
        .agg(tweet=("sentimen", "size"), akun=("username", "nunique"),
             median_likes=("likes", "median"))
        .reindex(URUTAN_PERIODE)
    )
    ringkas["nss"] = [nss(df.loc[df["periode"] == p, "sentimen"]) for p in URUTAN_PERIODE]

    kolom = st.columns(3)
    for kol, p in zip(kolom, URUTAN_PERIODE):
        baris = ringkas.loc[p]
        sebelumnya = URUTAN_PERIODE[URUTAN_PERIODE.index(p) - 1] if p != "sebelum" else None
        delta = None if sebelumnya is None else f"{baris['nss'] - ringkas.loc[sebelumnya, 'nss']:+.1f} poin"
        with kol:
            st.markdown(f"**{LABEL_PERIODE[p]}**")
            st.metric("Net Sentiment", f"{baris['nss']:+.1f}", delta)
            st.caption(
                f"{int(baris['tweet']):,} tweet · {int(baris['akun']):,} akun · "
                f"median {int(baris['median_likes']):,} likes"
            )

    # narasi otomatis -- dihitung dari data, bukan ditulis tangan
    d1 = ringkas.loc["hari-h", "nss"] - ringkas.loc["sebelum", "nss"]
    d2 = ringkas.loc["sesudah", "nss"] - ringkas.loc["hari-h", "nss"]
    puncak = df.groupby("hari", observed=False).size().idxmax()
    n_puncak = int(df.groupby("hari", observed=False).size().max())
    arah = "kembali turun" if d2 < 0 else "terus naik"

    st.info(
        f"**Bacaan singkat.** Net Sentiment naik **{d1:+.1f} poin** dari periode "
        f"sebelum ke Hari-H, lalu **{arah} {d2:+.1f} poin** di periode sesudah — "
        f"berakhir di **{ringkas.loc['sesudah', 'nss']:+.1f}**. Puncak percakapan "
        f"terjadi **{puncak:%d %B %Y}** dengan **{n_puncak:,} tweet**. "
        f"Pola ini konsisten dengan lonjakan perhatian seremonial yang tidak "
        f"bertahan lama setelah agenda pemerintahan mulai dibahas.",
        icon="🧭",
    )

    st.divider()
    st.markdown("#### Pergeseran tiap kelas sentimen")

    gerak = (
        pd.crosstab(df["periode"], df["sentimen"], normalize="index")
        .reindex(URUTAN_PERIODE)[URUTAN_SENTIMEN] * 100
    ).reset_index().melt(id_vars="periode", var_name="sentimen", value_name="persen")
    gerak["label"] = gerak["periode"].map(LABEL_PERIODE)

    fig_slope = px.line(
        gerak, x="label", y="persen", color="sentimen", markers=True,
        category_orders={"label": [LABEL_PERIODE[p] for p in URUTAN_PERIODE],
                         "sentimen": URUTAN_SENTIMEN},
        color_discrete_map=WARNA_SENTIMEN,
    )
    fig_slope.update_traces(line=dict(width=3), marker=dict(size=11))
    fig_slope.update_layout(
        xaxis_title=None, yaxis_title="% dari tweet periode itu",
        legend_title="Sentimen", height=380, margin=dict(t=20, b=10),
    )
    fig_slope.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig_slope, width="stretch")

    tabel = (pd.crosstab(df["periode"], df["sentimen"], normalize="index")
             .reindex(URUTAN_PERIODE)[URUTAN_SENTIMEN] * 100).round(1)
    tabel.index = [LABEL_PERIODE[p] for p in tabel.index]
    tabel["Net Sentiment"] = (tabel["positif"] - tabel["negatif"]).round(1)
    tabel["Jumlah tweet"] = ringkas["tweet"].values
    st.dataframe(
        tabel, width="stretch",
        column_config={
            c: st.column_config.NumberColumn(c.capitalize(), format="%.1f%%")
            for c in URUTAN_SENTIMEN
        } | {
            "Net Sentiment": st.column_config.NumberColumn("Net Sentiment", format="%+.1f"),
            "Jumlah tweet": st.column_config.NumberColumn("Jumlah tweet", format="%d"),
        },
    )

# ===================================================== TAB 2 — DISTRIBUSI
with tab_dist:
    st.markdown("#### Distribusi sentimen per periode")

    mode = st.radio(
        "Tampilkan sebagai", ["Persentase", "Jumlah"],
        horizontal=True, label_visibility="collapsed",
        help="Pakai Persentase kalau mau MEMBANDINGKAN antarperiode — jumlah "
             "tweet per periode beda jauh (Hari-H cuma 1 hari), jadi "
             "membandingkan angka mentah bisa menyesatkan.",
    )

    dist = df.groupby(["periode", "sentimen"], observed=False).size().reset_index(name="jumlah")
    dist["persentase"] = (
        dist["jumlah"] / dist.groupby("periode", observed=False)["jumlah"].transform("sum") * 100
    )
    dist["label_periode"] = dist["periode"].map(LABEL_PERIODE)

    pakai_persen = mode == "Persentase"
    fig1 = px.bar(
        dist, x="label_periode", y="persentase" if pakai_persen else "jumlah",
        color="sentimen", barmode="stack" if pakai_persen else "group",
        category_orders={"label_periode": [LABEL_PERIODE[p] for p in URUTAN_PERIODE],
                         "sentimen": URUTAN_SENTIMEN},
        color_discrete_map=WARNA_SENTIMEN,
        text_auto=".1f" if pakai_persen else True,
        custom_data=["jumlah", "persentase"],
    )
    fig1.update_traces(
        hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{customdata[0]:,} tweet "
                      "(%{customdata[1]:.1f}%)<extra></extra>"
    )
    fig1.update_layout(
        xaxis_title=None, yaxis_title="% dari periode" if pakai_persen else "Jumlah tweet",
        legend_title="Sentimen", height=420, margin=dict(t=20, b=10),
    )
    if pakai_persen:
        fig1.update_yaxes(range=[0, 100], ticksuffix="%")
    st.plotly_chart(fig1, width="stretch")

    st.divider()
    st.markdown("#### Apakah pergeserannya nyata secara statistik?")

    ct = pd.crosstab(df["periode"], df["sentimen"]).reindex(URUTAN_PERIODE)[URUTAN_SENTIMEN]
    chi2, pval, dof, harapan = chi2_contingency(ct)
    n_total = int(ct.values.sum())
    cramers_v = math.sqrt(chi2 / (n_total * (min(ct.shape) - 1)))

    if cramers_v < 0.1:
        kuat, saran = "lemah", "perbedaannya ada tapi tipis"
    elif cramers_v < 0.3:
        kuat, saran = "sedang", "perbedaannya cukup terasa"
    else:
        kuat, saran = "kuat", "perbedaannya besar"

    s1, s2, s3 = st.columns(3)
    s1.metric("Chi-square (χ²)", f"{chi2:,.1f}", f"dof = {dof}")
    s2.metric("p-value", f"{pval:.2e}", "signifikan" if pval < 0.05 else "tidak signifikan")
    s3.metric("Cramér's V", f"{cramers_v:.3f}", f"efek {kuat}")

    st.markdown(
        f"""
**Cara membacanya.** Uji chi-square menjawab: *apakah komposisi sentimen benar-benar
berbeda antarperiode, atau bisa saja kebetulan?* Di sini p-value = `{pval:.2e}`
{"< 0.05, jadi perbedaannya **bukan kebetulan**." if pval < 0.05 else "≥ 0.05, jadi perbedaannya **belum tentu nyata**."}

**Tapi jangan berhenti di p-value.** Dengan n = {n_total:,}, hampir semua
perbedaan sekecil apa pun akan keluar "signifikan" — itu sifat uji statistik
pada sampel besar, bukan tanda temuan yang besar. Karena itu dibaca juga
**Cramér's V = {cramers_v:.3f}**, yang mengukur *seberapa besar* perbedaannya:
tergolong **{kuat}** ({saran}).

> Menyebut keduanya — bukan cuma p-value — adalah bagian dari kriteria
> *Understanding of Analytical Theory* (30% rubrik). Banyak laporan berhenti di
> "p < 0.05" dan melewatkan bahwa efeknya ternyata kecil.
        """
    )

    with st.expander("Lihat tabel kontingensi & frekuensi harapan"):
        ka, kb = st.columns(2)
        with ka:
            st.caption("**Teramati** (jumlah asli)")
            tampil = ct.copy()
            tampil.index = [LABEL_PERIODE[p] for p in tampil.index]
            st.dataframe(tampil, width="stretch")
        with kb:
            st.caption("**Harapan** (kalau sentimen TIDAK dipengaruhi periode)")
            exp = pd.DataFrame(harapan, index=[LABEL_PERIODE[p] for p in ct.index],
                               columns=ct.columns).round(1)
            st.dataframe(exp, width="stretch")
        st.caption(
            "Selisih antara dua tabel inilah yang diringkas jadi angka χ². "
            "Makin jauh Teramati dari Harapan, makin besar χ²-nya."
        )

# ===================================================== TAB 3 — TREN WAKTU
with tab_tren:
    st.markdown("#### Volume & komposisi sentimen harian")
    st.caption("Tab ini selalu menampilkan rentang penuh H-30 → H+30, tidak ikut filter sidebar.")

    harian = df.groupby(["hari", "sentimen"], observed=False).size().reset_index(name="jumlah")
    fig2 = px.area(
        harian, x="hari", y="jumlah", color="sentimen",
        category_orders={"sentimen": URUTAN_SENTIMEN},
        color_discrete_map=WARNA_SENTIMEN,
    )
    fig2.update_traces(line=dict(width=0.5), hovertemplate="%{y:,} tweet<extra>%{fullData.name}</extra>")
    fig2.add_vline(x=TANGGAL_HARI_H, line_width=2, line_dash="dash", line_color="#333")
    fig2.add_annotation(
        x=TANGGAL_HARI_H, yref="paper", y=1.03, text="<b>20 Okt — Pelantikan</b>",
        showarrow=False, font=dict(size=12, color="#333"), xanchor="center",
    )
    if pilihan != "semua":
        batas = df.loc[df["periode"] == pilihan, "hari"]
        fig2.add_vrect(
            # pd.Timedelta(1, "D") -- BUKAN pd.Timedelta(days=1). Bentuk kedua
            # kena DeprecationWarning di pandas 2.3 + numpy 2.5, dan nanti error.
            x0=batas.min(), x1=batas.max() + pd.Timedelta(1, "D"),
            fillcolor="#1f77b4", opacity=0.08, line_width=0, layer="below",
        )
    fig2.update_layout(
        xaxis_title=None, yaxis_title="Tweet per hari", legend_title="Sentimen",
        height=420, margin=dict(t=40, b=10), hovermode="x unified",
    )
    st.plotly_chart(fig2, width="stretch")

    st.markdown("#### Net Sentiment harian")

    prop = (
        df.assign(pos=df["sentimen"].eq("positif"), neg=df["sentimen"].eq("negatif"))
        .groupby("hari", observed=False)
        .agg(pos=("pos", "mean"), neg=("neg", "mean"), n=("pos", "size"))
        .reset_index()
    )
    prop["nss"] = (prop["pos"] - prop["neg"]) * 100
    prop["rata2_7hari"] = prop["nss"].rolling(7, center=True, min_periods=3).mean()

    fig3 = px.scatter(
        prop, x="hari", y="nss", size="n", size_max=20, custom_data=["n"], opacity=0.40,
        color_discrete_sequence=["#1F6FEB"],
    )
    fig3.update_traces(
        hovertemplate="%{x|%d %b}<br>Net Sentiment %{y:+.1f} · %{customdata[0]:,} tweet<extra></extra>"
    )
    fig3.add_scatter(
        x=prop["hari"], y=prop["rata2_7hari"], mode="lines",
        line=dict(width=3, color="#1F6FEB"), name="Rata-rata 7 hari", hoverinfo="skip",
    )
    fig3.add_hline(y=0, line_dash="dot", line_color="#666")
    fig3.add_vline(x=TANGGAL_HARI_H, line_width=2, line_dash="dash", line_color="#333")
    fig3.update_layout(
        xaxis_title=None, yaxis_title="Net Sentiment (%pos − %neg)",
        showlegend=False, height=340, margin=dict(t=20, b=10),
    )
    st.plotly_chart(fig3, width="stretch")
    st.caption(
        "Ukuran titik = jumlah tweet hari itu. **Hari sepi bikin angka gampang "
        "melonjak**, jadi baca garis rata-rata 7 harinya. Garis nol = titik "
        "tempat dukungan dan penolakan seimbang."
    )

    st.divider()
    ha, hb = st.columns([3, 2])

    with ha:
        st.markdown("#### Kapan orang nge-tweet?")
        panas = (
            df.groupby(["hari_minggu", "jam"], observed=False).size()
            .reset_index(name="jumlah")
            .pivot(index="hari_minggu", columns="jam", values="jumlah")
            .reindex(range(7)).reindex(columns=range(24)).fillna(0)
        )
        fig4 = px.imshow(
            panas.values, labels=dict(x="Jam (WIB)", y="", color="Tweet"),
            x=[f"{j:02d}" for j in range(24)], y=HARI_MINGGU,
            color_continuous_scale="Blues", aspect="auto",
        )
        fig4.update_layout(height=340, margin=dict(t=10, b=10), coloraxis_showscale=True)
        st.plotly_chart(fig4, width="stretch")
        st.caption(
            "Berguna untuk **menjadwalkan pemantauan**: jam berapa percakapan "
            "paling ramai, dan apakah polanya berubah di akhir pekan."
        )

    with hb:
        st.markdown("#### 10 hari paling ramai")
        top_hari = (
            df.groupby("hari", observed=False)
            .agg(tweet=("sentimen", "size"))
            .nlargest(10, "tweet").reset_index()
        )
        top_hari["nss"] = [nss(df.loc[df["hari"] == h, "sentimen"]) for h in top_hari["hari"]]
        st.dataframe(
            top_hari, width="stretch", hide_index=True, height=340,
            column_config={
                "hari": st.column_config.DateColumn("Tanggal", format="DD MMM YYYY"),
                "tweet": st.column_config.NumberColumn("Tweet", format="%d"),
                "nss": st.column_config.NumberColumn("Net Sentiment", format="%+.1f"),
            },
        )
        st.caption("Tanggal-tanggal ini yang layak ditelusuri: apa yang terjadi hari itu?")

# =================================================== TAB 4 — ANALISIS TEKS
with tab_teks:
    st.markdown("#### Kata yang paling sering muncul")
    st.caption(
        f"Dihitung dari kolom `teks_bersih` · {judul_periode} · {len(dff):,} tweet. "
        "Kata di sini **bukan hasil scraping**, tapi hasil hitung (PLAN.md bagian 10)."
    )

    sub_pos, sub_neg, sub_net = st.tabs(["Positif", "Negatif", "Netral"])
    warna_map = {"positif": "Greens", "negatif": "Reds", "netral": "Greys"}

    for sub, sent in zip((sub_pos, sub_neg, sub_net), ("positif", "negatif", "netral")):
        with sub:
            teks = " ".join(dff.loc[dff["sentimen"] == sent, "teks_bersih"])
            n = int((dff["sentimen"] == sent).sum())
            if not teks.strip():
                st.info(f"Tidak ada tweet **{sent}** yang lolos filter.")
                continue

            freq = hitung_frekuensi(teks)   # satu hitungan, dipakai dua visual
            kiri, kanan = st.columns([2, 1])
            with kiri:
                gambar = buat_wordcloud(freq, warna_map[sent])
                if gambar is not None:
                    st.image(gambar, width="stretch")
            with kanan:
                st.markdown(f"**15 kata teratas** · {n:,} tweet")
                fig5 = px.bar(
                    pd.DataFrame(Counter(freq).most_common(15), columns=["kata", "frekuensi"]),
                    x="frekuensi", y="kata", orientation="h",
                    color_discrete_sequence=[WARNA_SENTIMEN[sent]],
                )
                fig5.update_layout(
                    yaxis=dict(autorange="reversed", title=None), xaxis_title=None,
                    height=440, margin=dict(t=10, b=10, l=10, r=10),
                )
                st.plotly_chart(fig5, width="stretch")

    st.caption(
        "Word cloud enak dilihat tapi susah dikutip angkanya — **pakai bar "
        "'15 kata teratas' untuk laporan**, word cloud untuk slide."
    )

    st.divider()
    st.markdown("#### Kata khas tiap periode — *apa yang berubah dari percakapannya?*")
    st.caption(
        "Bukan kata tersering (itu hampir sama di semua periode), tapi kata yang "
        "**porsinya melonjak** di satu periode dibanding periode lain. Inilah yang "
        "menunjukkan isu apa yang naik dan turun. Tidak ikut filter sidebar."
    )

    kols = st.columns(3)
    for kol, p in zip(kols, URUTAN_PERIODE):
        with kol:
            st.markdown(f"**{LABEL_PERIODE[p]}**")
            ini = " ".join(df.loc[df["periode"] == p, "teks_bersih"])
            lain = " ".join(df.loc[df["periode"] != p, "teks_bersih"])
            hasil = kata_khas(ini, lain)
            if not hasil:
                st.info("Tidak cukup data.")
                continue
            kk = pd.DataFrame(hasil, columns=["kata", "skor", "frekuensi"])
            fig6 = px.bar(
                kk, x="skor", y="kata", orientation="h", custom_data=["frekuensi"],
                color_discrete_sequence=[WARNA_PERIODE[p]],
            )
            fig6.update_traces(
                hovertemplate="<b>%{y}</b><br>skor kekhasan %{x:.2f}<br>"
                              "muncul %{customdata[0]:,} kali<extra></extra>"
            )
            fig6.update_layout(
                yaxis=dict(autorange="reversed", title=None),
                xaxis_title="lebih khas →", height=400, margin=dict(t=10, b=10, l=10, r=10),
            )
            st.plotly_chart(fig6, width="stretch")

    with st.expander("Bagaimana skor kekhasan dihitung?"):
        st.markdown(
            """
Untuk tiap kata dihitung **log rasio frekuensi relatif** antara satu periode
dan gabungan periode lainnya:

$$\\text{skor}(w) = \\ln \\frac{p_{\\text{periode ini}}(w)}{p_{\\text{periode lain}}(w)}$$

- Skor **0** → porsi katanya sama saja, tidak khas.
- Skor **+0.7** → kira-kira dua kali lebih sering (porsi, bukan jumlah).
- Ditambah pemulusan Laplace (+0.5) supaya kata yang cuma muncul di satu sisi
  tidak menyebabkan pembagian nol.
- Kata dengan total kemunculan < 20 dibuang, supaya kata langka tidak
  mendominasi hanya karena kebetulan.

Pakai porsi, bukan jumlah mentah — kalau tidak, periode dengan tweet terbanyak
akan selalu menang di semua kata.
            """
        )

    st.divider()
    st.markdown("#### Kata pembeda: positif vs negatif")
    st.caption(
        "Kata yang paling membedakan tweet positif dari tweet negatif. Berguna "
        "untuk **memeriksa hasil labeling** — kalau kata di sisi positif terasa "
        "negatif, berarti lexicon-nya bermasalah."
    )

    t_pos = " ".join(dff.loc[dff["sentimen"] == "positif", "teks_bersih"])
    t_neg = " ".join(dff.loc[dff["sentimen"] == "negatif", "teks_bersih"])
    banding = (
        [(w, s) for w, s, _ in kata_khas(t_pos, t_neg, top_n=10)]
        + [(w, -s) for w, s, _ in kata_khas(t_neg, t_pos, top_n=10)]
    )
    if banding:
        bdf = pd.DataFrame(banding, columns=["kata", "skor"]).sort_values("skor")
        bdf["sisi"] = bdf["skor"].apply(lambda s: "positif" if s > 0 else "negatif")
        fig7 = px.bar(
            bdf, x="skor", y="kata", orientation="h", color="sisi",
            color_discrete_map={"positif": WARNA_SENTIMEN["positif"],
                                "negatif": WARNA_SENTIMEN["negatif"]},
        )
        fig7.add_vline(x=0, line_width=1, line_color="#333")
        fig7.update_layout(
            yaxis_title=None, xaxis_title="← lebih khas negatif    |    lebih khas positif →",
            height=520, margin=dict(t=10, b=10), legend_title="Lebih sering di",
        )
        st.plotly_chart(fig7, width="stretch")
    else:
        st.info("Tidak cukup data untuk membandingkan.")

# ================================================ TAB 5 — VIRALITAS & AKUN
with tab_viral:
    st.markdown("#### Viralitas: likes vs retweet")

    skala = st.radio(
        "Skala sumbu", ["Logaritmik", "Linear"], horizontal=True, label_visibility="collapsed",
        help="Logaritmik bikin sebaran kebaca, tapi MEMBUANG tweet bernilai 0. "
             "Linear menampilkan semua tweet, tapi mayoritas menggumpal di pojok "
             "kiri bawah. Pakai dua-duanya.",
    )
    pakai_log = skala == "Logaritmik"

    if pakai_log:
        hilang = int(((dff["likes"] == 0) | (dff["retweet"] == 0)).sum())
        if hilang:
            st.warning(
                f"**{hilang:,} dari {len(dff):,} tweet ({hilang / len(dff) * 100:.1f}%) "
                f"tidak tergambar** — nilai 0 tidak punya posisi di skala logaritmik. "
                f"Ini tweet yang tidak dapat engagement sama sekali. Ganti ke "
                f"**Linear** untuk melihat semuanya, dan sebut angka ini di laporan.",
                icon="📉",
            )

    contoh = dff if len(dff) <= 6000 else dff.sample(6000, random_state=42)
    if len(contoh) < len(dff):
        st.caption(f"Menggambar contoh acak {len(contoh):,} dari {len(dff):,} tweet agar chart tetap responsif.")

    fig8 = px.scatter(
        contoh, x="likes", y="retweet", color="sentimen",
        size=contoh["engagement"].clip(lower=1), size_max=42, opacity=0.55,
        category_orders={"sentimen": URUTAN_SENTIMEN}, color_discrete_map=WARNA_SENTIMEN,
        hover_name="username", custom_data=["teks_bersih", "tanggal", "likes", "retweet"],
        log_x=pakai_log, log_y=pakai_log,
    )
    fig8.update_traces(
        hovertemplate=(
            "<b>@%{hovertext}</b> · %{customdata[1]|%d %b %Y}<br>"
            "%{customdata[2]:,} likes · %{customdata[3]:,} retweet<br>"
            "<i>%{customdata[0]}</i><extra></extra>"
        )
    )
    akhiran = " (skala log)" if pakai_log else ""
    fig8.update_layout(
        xaxis_title=f"Likes{akhiran}", yaxis_title=f"Retweet{akhiran}",
        legend_title="Sentimen", height=540, margin=dict(t=20, b=10),
    )
    st.plotly_chart(fig8, width="stretch")

    st.divider()
    va, vb = st.columns(2)

    with va:
        st.markdown("#### Sebaran engagement")
        fig9 = px.histogram(
            dff[dff["engagement"] > 0], x="engagement", color="sentimen", nbins=50,
            log_x=True, barmode="overlay", opacity=0.55,
            category_orders={"sentimen": URUTAN_SENTIMEN}, color_discrete_map=WARNA_SENTIMEN,
        )
        fig9.update_layout(
            xaxis_title="Engagement (likes + retweet, skala log)", yaxis_title="Jumlah tweet",
            legend_title="Sentimen", height=380, margin=dict(t=10, b=10),
        )
        st.plotly_chart(fig9, width="stretch")
        st.caption(
            "Bentuknya **ekor panjang**: mayoritas tweet nyaris tidak diperhatikan, "
            "segelintir meledak. Karena itu **median lebih jujur daripada rata-rata** "
            "untuk data ini — sebutkan di Methodology."
        )

    with vb:
        st.markdown("#### Sentimen mana yang menyebar lebih jauh?")
        fig10 = px.box(
            dff[dff["engagement"] > 0], x="sentimen", y="engagement", color="sentimen",
            log_y=True, category_orders={"sentimen": URUTAN_SENTIMEN},
            color_discrete_map=WARNA_SENTIMEN, points=False,
        )
        fig10.update_layout(
            xaxis_title=None, yaxis_title="Engagement (skala log)", showlegend=False,
            height=380, margin=dict(t=10, b=10),
        )
        st.plotly_chart(fig10, width="stretch")

        med = dff.groupby("sentimen", observed=False)["engagement"].median()
        if med.get("negatif", 0) and med.get("positif", 0):
            rasio = med["negatif"] / med["positif"]
            st.caption(
                f"Median engagement tweet negatif **{rasio:.2f}×** tweet positif. "
                + ("Kritik menyebar lebih jauh daripada dukungan — temuan yang layak "
                   "masuk Discussion." if rasio > 1.1 else
                   "Tidak ada selisih mencolok antar kelas sentimen.")
            )

    st.divider()
    st.markdown("#### Akun paling berpengaruh")
    st.caption(
        "Diurutkan berdasarkan **total engagement**, bukan jumlah tweet — akun yang "
        "nge-spam 200 kali tanpa ada yang peduli tidak berpengaruh."
    )

    akun = (
        dff.groupby("username", observed=False)
        .agg(tweet=("sentimen", "size"), total_engagement=("engagement", "sum"),
             median_likes=("likes", "median"))
        .nlargest(15, "total_engagement").reset_index()
    )
    akun["nss"] = [nss(dff.loc[dff["username"] == u, "sentimen"]) for u in akun["username"]]

    fig11 = px.bar(
        akun.sort_values("total_engagement"), x="total_engagement", y="username",
        orientation="h", color="nss", color_continuous_scale=["#D64550", "#9AA0A6", "#2E9E5B"],
        range_color=[-100, 100], custom_data=["tweet", "nss"],
    )
    fig11.update_traces(
        hovertemplate="<b>@%{y}</b><br>%{x:,} total engagement<br>"
                      "%{customdata[0]:,} tweet · Net Sentiment %{customdata[1]:+.1f}<extra></extra>"
    )
    fig11.update_layout(
        yaxis_title=None, xaxis_title="Total engagement",
        coloraxis_colorbar=dict(title="Net<br>Sentiment"),
        height=520, margin=dict(t=10, b=10),
    )
    st.plotly_chart(fig11, width="stretch")
    st.caption(
        "Warna batang = kecenderungan sentimen akun itu. Kalau akun paling "
        "berpengaruh ternyata condong ke satu kutub, sebutkan di Discussion — "
        "artinya percakapan mungkin digerakkan segelintir pihak, bukan opini merata."
    )

    st.markdown("##### 10 tweet paling viral")
    top10 = dff.nlargest(10, "engagement")[
        ["tanggal", "sentimen", "likes", "retweet", "username", "teks_bersih"]
    ]
    st.dataframe(
        top10, width="stretch", hide_index=True,
        column_config={
            "tanggal": st.column_config.DatetimeColumn("Tanggal", format="DD MMM YYYY HH:mm"),
            "likes": st.column_config.NumberColumn("Likes", format="%d"),
            "retweet": st.column_config.NumberColumn("Retweet", format="%d"),
            "teks_bersih": st.column_config.TextColumn("Teks (sudah dibersihkan)", width="large"),
        },
    )

# ================================================== TAB 6 — EVALUASI MODEL
with tab_eval:
    st.markdown("#### Evaluasi model SVM")

    if PATH_CM.exists() or PATH_METRICS.exists():
        kiri, kanan = st.columns([3, 2])
        with kiri:
            if PATH_CM.exists():
                st.image(str(PATH_CM), caption="Confusion matrix — output src/train_model.py")
            else:
                st.info("`confusion_matrix.png` belum ada.")
        with kanan:
            if PATH_METRICS.exists():
                m = json.loads(PATH_METRICS.read_text(encoding="utf-8"))
                for nama in ("accuracy", "precision", "recall", "f1"):
                    if nama in m:
                        nilai = m[nama]
                        st.metric(
                            nama.capitalize(),
                            f"{nilai:.1%}" if isinstance(nilai, float) and nilai <= 1 else str(nilai),
                        )
                sisa = {k: v for k, v in m.items() if k not in ("accuracy", "precision", "recall", "f1")}
                if sisa:
                    st.json(sisa, expanded=False)
            else:
                st.info("`metrics.json` belum ada.")
    else:
        st.warning(
            "**Belum ada hasil evaluasi.** Tab ini terisi otomatis begitu "
            "`src/train_model.py` menghasilkan `data/model/confusion_matrix.png` "
            "dan `data/model/metrics.json` (PLAN.md bagian 4, tahap 2c).",
            icon="⏳",
        )

    st.divider()
    st.markdown(
        """
##### Cara membaca angka di tab ini (tolong jangan salah klaim)

Label sentimen dihasilkan oleh **lexicon**, bukan oleh manusia. Artinya SVM di
sini sedang belajar **meniru kamus** — bukan belajar memahami sentimen. Akurasi
tinggi (85–95%) itu **bukan prestasi**, itu cuma bukti SVM berhasil meniru
aturan kamus.

Jadi di laporan:

- ✅ *"Model mencapai akurasi X% dalam mereplikasi pelabelan berbasis lexicon."*
- ❌ *"Model mendeteksi sentimen publik dengan akurasi X%."*

Angka yang benar-benar mengukur kualitas sentimen adalah **validasi manual**:
ambil acak ~100 tweet, label bertiga, bandingkan dengan label lexicon
(PLAN.md bagian 4 & 10). Angka itu yang masuk Discussion.

Baris/kolom **netral** di confusion matrix kemungkinan besar paling berantakan.
Itu memang sudah diduga sejak awal (PLAN.md keputusan #6) — bahas jujur sebagai
*limitation*, jangan ditutupi. Justru di situ poin *Understanding of Analytical
Theory* (30% rubrik) didapat.

##### Distribusi kelas (penting untuk membaca confusion matrix)
        """
    )
    kelas = df["sentimen"].value_counts().reindex(URUTAN_SENTIMEN)
    kk1, kk2, kk3 = st.columns(3)
    for kol, s in zip((kk1, kk2, kk3), URUTAN_SENTIMEN):
        kol.metric(s.capitalize(), f"{int(kelas[s]):,}", f"{kelas[s] / len(df) * 100:.1f}%")
    terkecil = kelas.idxmin()
    st.caption(
        f"Kelas terkecil adalah **{terkecil}** ({kelas[terkecil] / len(df) * 100:.1f}%). "
        "Kelas minoritas hampir selalu punya recall paling rendah — pakai "
        "`class_weight=\"balanced\"` di LinearSVC dan `stratify=y` saat split, "
        "lalu laporkan **macro-F1**, bukan cuma accuracy. Accuracy bisa terlihat "
        "bagus hanya karena kelas mayoritas tertebak benar."
    )

# ------------------------------------------------------------------- lampiran

st.divider()
with st.expander(f"Lihat data mentah ({len(dff):,} baris)"):
    st.dataframe(dff[KOLOM_KONTRAK], width="stretch", height=420, hide_index=True)
    st.download_button(
        "Unduh sebagai CSV",
        dff[KOLOM_KONTRAK].to_csv(index=False).encode("utf-8"),
        file_name=f"sentimen_{pilihan}.csv",
        mime="text/csv",
    )
