#!/bin/bash
# =============================================================================
#  JALANKAN.command -- pemeriksa kebutuhan + peluncur proyek, satu berkas.
#
#  Versi macOS dari JALANKAN.bat. Isi dan urutannya sengaja dibikin sama
#  persis, supaya kalau ada yang berubah di satu berkas, gampang dicari
#  padanannya di berkas satunya.
#
#  Cara pakai: klik dua kali berkas ini di Finder. Tidak perlu buka Terminal.
#
#  Yang dikerjakan:
#    1. Periksa semua yang dibutuhkan proyek ini
#    2. Pasang sendiri yang kurang  (setelah minta izin)
#    3. Tampilkan menu untuk menjalankan dashboard / pipeline
#
#  === KALAU KLIK DUA KALI TIDAK JALAN ===
#
#  Dua hal yang biasanya jadi sebab, dan dua-duanya cuma sekali di awal:
#
#    1. Izin eksekusi hilang. Buka Terminal di folder proyek, jalankan:
#           chmod +x JALANKAN.command
#
#    2. Proyeknya diunduh sebagai ZIP, bukan lewat git clone. macOS menandai
#       berkas unduhan sebagai karantina dan menolak menjalankannya. Pilih
#       salah satu:
#           klik kanan berkas ini > Open > tombol Open
#       atau di Terminal:
#           xattr -d com.apple.quarantine JALANKAN.command
#
#  Diuji di macOS Tahoe 26.6. Jalan juga di versi sebelumnya; yang dipakai
#  cuma perkakas bawaan macOS (bash, curl) plus uv.
#
#  Kelompok 04 - ISYS8036042 Business Intelligence and Analytics
# =============================================================================

set -u

# .command yang diklik dua kali mulai dari folder home, bukan folder proyek.
cd "$(dirname "$0")" || { echo "Tidak bisa masuk ke folder proyek."; exit 1; }

# Judul jendela Terminal.
printf '\033]0;BIA Kelompok 04 - Analisis Sentimen Pelantikan\007'

VENV_PY=".venv/bin/python"

UV=""
STATUS_UV="BELUM";    INFO_UV=""
STATUS_PY="BELUM";    INFO_PY=""
STATUS_VENV="BELUM";  INFO_VENV=""
STATUS_PAKET="BELUM"; INFO_PAKET=""
STATUS_DATA="BELUM";  INFO_DATA=""
STATUS_LEX="BELUM";   INFO_LEX=""
PERLU_PERBAIKAN=0

jeda() {
    echo
    read -r -p "  Tekan Enter untuk lanjut ... " _
}

# =============================================================================
#  PEMERIKSAAN
# =============================================================================

periksa_uv() {
    # uv dipakai karena bisa sekalian memasang Python-nya sendiri, jadi tidak
    # perlu instalasi Python manual lebih dulu.
    UV="$(command -v uv 2>/dev/null || true)"
    [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
    [ -z "$UV" ] && [ -x "/opt/homebrew/bin/uv" ] && UV="/opt/homebrew/bin/uv"
    [ -z "$UV" ] && [ -x "/usr/local/bin/uv" ] && UV="/usr/local/bin/uv"

    if [ -z "$UV" ]; then
        STATUS_UV="BELUM"
        INFO_UV="akan dipasang otomatis"
        PERLU_PERBAIKAN=1
        return
    fi
    INFO_UV="versi $("$UV" --version 2>/dev/null | awk '{print $2}')"
    STATUS_UV="OK"
}

periksa_python() {
    # CATATAN: jangan memanggil "python3" bawaan macOS untuk memeriksa apa pun.
    # Kalau Xcode Command Line Tools belum terpasang, perintah itu justru
    # memunculkan kotak dialog instalasi -- persis seperti stub Microsoft Store
    # di Windows. Semua Python di proyek ini datang dari uv, bukan dari sistem.
    if [ -x "$VENV_PY" ]; then
        INFO_PY="$("$VENV_PY" --version 2>&1 | awk '{print $2}') dari .venv"
        STATUS_PY="OK"
        return
    fi
    if [ -n "$UV" ] && "$UV" python list --only-installed 2>/dev/null | grep -q "3\.12"; then
        STATUS_PY="OK"
        INFO_PY="3.12 tersedia lewat uv"
        return
    fi
    STATUS_PY="BELUM"
    INFO_PY="akan dipasang lewat uv"
    PERLU_PERBAIKAN=1
}

periksa_venv() {
    if [ -x "$VENV_PY" ]; then
        STATUS_VENV="OK"
        INFO_VENV=".venv"
        return
    fi
    STATUS_VENV="BELUM"
    INFO_VENV="akan dibuat otomatis"
    PERLU_PERBAIKAN=1
}

periksa_paket() {
    if [ ! -x "$VENV_PY" ]; then
        STATUS_PAKET="BELUM"
        INFO_PAKET="menunggu virtualenv"
        PERLU_PERBAIKAN=1
        return
    fi
    if ! "$VENV_PY" -c "import streamlit,plotly,pandas,numpy,wordcloud,sklearn,selenium,matplotlib,scipy,Sastrawi,openpyxl" >/dev/null 2>&1; then
        STATUS_PAKET="BELUM"
        INFO_PAKET="ada yang kurang atau rusak"
        PERLU_PERBAIKAN=1
        return
    fi
    STATUS_PAKET="OK"
    INFO_PAKET="10 paket inti terpasang"
}

periksa_data() {
    if [ ! -f "data/processed/dataset_dummy.csv" ]; then
        STATUS_DATA="BELUM"
        INFO_DATA="akan dibuat otomatis"
        PERLU_PERBAIKAN=1
        return
    fi
    STATUS_DATA="OK"
    if [ -f "data/processed/dataset_final.csv" ]; then
        INFO_DATA="dummy + DATA ASLI sudah ada"
    else
        INFO_DATA="dummy siap, data asli belum"
    fi
}

periksa_lexicon() {
    # InSet TIDAK ikut di-commit dan TIDAK boleh dikarang. Hanya dibutuhkan
    # untuk labeling data asli; pipeline mode uji memakai kamus mini bawaan.
    if [ -f "lexicon/positive.tsv" ] && [ -f "lexicon/negative.tsv" ]; then
        STATUS_LEX="OK"
        INFO_LEX="InSet terpasang"
        return
    fi
    # Sengaja TIDAK menaikkan PERLU_PERBAIKAN: ini bukan penghalang untuk
    # menjalankan dashboard maupun pipeline mode uji.
    STATUS_LEX="BELUM"
    INFO_LEX="perlu untuk data asli, unduh manual"
}

periksa_semua() {
    PERLU_PERBAIKAN=0
    clear
    echo
    echo "  ============================================================"
    echo "    BIA Kelompok 04 - Analisis Sentimen Pelantikan"
    echo "    Pemeriksaan kebutuhan"
    echo "  ============================================================"
    echo

    periksa_uv
    periksa_python
    periksa_venv
    periksa_paket
    periksa_data
    periksa_lexicon

    printf "  [1/6] uv ................ %-6s %s\n" "$STATUS_UV"    "$INFO_UV"
    printf "  [2/6] Python ............ %-6s %s\n" "$STATUS_PY"    "$INFO_PY"
    printf "  [3/6] Virtualenv ........ %-6s %s\n" "$STATUS_VENV"  "$INFO_VENV"
    printf "  [4/6] Paket Python ...... %-6s %s\n" "$STATUS_PAKET" "$INFO_PAKET"
    printf "  [5/6] Data dummy ........ %-6s %s\n" "$STATUS_DATA"  "$INFO_DATA"
    printf "  [6/6] Kamus InSet ....... %-6s %s\n" "$STATUS_LEX"   "$INFO_LEX"
    echo
    echo "  ------------------------------------------------------------"

    if [ "$PERLU_PERBAIKAN" -eq 0 ]; then
        echo
        echo "  Semua siap. Proyek bisa dijalankan."
        echo
        return 0
    fi

    echo
    echo "  Ada yang belum siap. Semua bisa dipasang otomatis."
    echo "  Butuh koneksi internet, sekitar 2-4 menit untuk pertama kali."
    echo
    read -r -p "  Pasang sekarang? [Y/N] " IZIN
    case "$IZIN" in
        [Yy]*) perbaiki ;;
        *)
            echo
            echo "  Dibatalkan. Proyek belum bisa dijalankan."
            jeda
            exit 1
            ;;
    esac
}

# =============================================================================
#  PERBAIKAN
# =============================================================================

gagal_pasang() {
    echo
    echo "  ------------------------------------------------------------"
    echo "  GAGAL. Pesan kesalahan ada di atas."
    echo
    echo "  Yang biasanya jadi penyebab:"
    echo "    - tidak ada koneksi internet"
    echo "    - folder proyek ada di dalam iCloud Drive yang sedang menyinkron"
    echo "    - folder proyek ada di Desktop/Documents dan macOS belum diberi"
    echo "      izin akses berkas untuk Terminal"
    echo
    jeda
    exit 1
}

perbaiki() {
    echo
    echo "  ============================================================"
    echo "    Memasang kebutuhan"
    echo "  ============================================================"
    echo

    if [ -z "$UV" ]; then
        echo "  - Memasang uv ..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        [ -x "$HOME/.local/bin/uv" ] && UV="$HOME/.local/bin/uv"
        [ -z "$UV" ] && UV="$(command -v uv 2>/dev/null || true)"
        if [ -z "$UV" ]; then
            echo
            echo "  GAGAL memasang uv. Periksa koneksi internet, lalu coba lagi."
            echo "  Alternatif: pasang lewat Homebrew  ->  brew install uv"
            echo
            jeda
            exit 1
        fi
        echo "  uv terpasang."
        echo
    fi

    echo "  - Memastikan Python 3.12 tersedia ..."
    "$UV" python install 3.12 || gagal_pasang

    if [ -x "$VENV_PY" ]; then
        echo "  - Virtualenv .venv sudah ada, dilewati."
    else
        echo
        echo "  - Membuat virtualenv .venv ..."
        "$UV" venv --python 3.12 --seed || gagal_pasang
    fi

    echo
    echo "  - Memasang paket dari requirements.txt ..."
    echo "      Sabar, ini bagian paling lama."
    "$UV" pip install -r requirements.txt || gagal_pasang

    if [ -f "data/processed/dataset_dummy.csv" ]; then
        echo "  - Data dummy sudah ada, dilewati."
    else
        echo
        echo "  - Membuat data dummy ..."
        "$VENV_PY" src/make_dummy.py || gagal_pasang
    fi

    echo
    echo "  ------------------------------------------------------------"
    echo "  Selesai. Memeriksa ulang ..."
    echo
    sleep 2
    periksa_semua
}

# =============================================================================
#  MENJALANKAN
# =============================================================================

jalan_dashboard() {
    echo "  ============================================================"
    echo "    Menjalankan dashboard"
    echo "  ============================================================"
    echo
    echo "  Browser akan terbuka sendiri di http://localhost:8501"
    echo "  Tekan CTRL+C di jendela ini untuk menghentikan."
    echo
    if [ ! -f "data/processed/dataset_final.csv" ]; then
        echo "  CATATAN: data asli belum ada, dashboard memakai DATA DUMMY."
        echo "  Akan ada banner merah di atas halaman. Itu memang disengaja."
        echo
    fi
    # --server.headless=false supaya browser terbuka sendiri. Berkas
    # .streamlit/config.toml menyetel headless=true untuk pemakaian dari
    # terminal; di sini sengaja ditimpa karena berkasnya diklik dua kali.
    "$VENV_PY" -m streamlit run dashboard/app.py --server.headless=false
    echo
    echo "  Dashboard berhenti."
    jeda
}

gagal_pipeline() {
    echo
    echo "  Pipeline berhenti karena ada kesalahan. Lihat pesan di atas."
    jeda
}

jalan_pipeline() {
    echo "  ============================================================"
    echo "    Pipeline Tahap 2 - MODE UJI"
    echo "  ============================================================"
    echo
    echo "  Menjalankan: data mentah kotor -> bersihkan -> labeli -> latih SVM"
    echo
    echo "  AMAN: semua keluaran berakhiran _demo. dataset_final.csv tidak"
    echo "  akan tersentuh, jadi dashboard tetap memakai data dummy."
    echo
    echo "  Lama sekitar 15 detik."
    jeda
    echo
    echo "  --- 1/4  membuat data mentah yang sengaja kotor ---"
    "$VENV_PY" src/make_dummy_raw.py || { gagal_pipeline; return; }
    echo
    echo "  --- 2/4  preprocessing ---"
    "$VENV_PY" src/preprocess.py --demo || { gagal_pipeline; return; }
    echo
    echo "  --- 3/4  labeling berbasis lexicon ---"
    "$VENV_PY" src/labeling.py --demo || { gagal_pipeline; return; }
    echo
    echo "  --- 4/4  melatih SVM + confusion matrix ---"
    "$VENV_PY" src/train_model.py --demo || { gagal_pipeline; return; }
    echo
    echo "  ------------------------------------------------------------"
    echo "  Pipeline selesai. Hasilnya di data/processed/ dan data/model/"
    echo
    echo "  INGAT: angka dari mode uji TIDAK BOLEH masuk laporan."
    echo "  Kamus mini bawaan disusun dari kosakata yang sama dengan"
    echo "  generator datanya, jadi pengujiannya sirkular."
    jeda
}

buat_dummy() {
    echo "  Membuat ulang data dummy ..."
    echo
    "$VENV_PY" src/make_dummy.py
    jeda
}

pasang_paket() {
    echo "  Memasang ulang semua paket ..."
    echo
    if [ -z "$UV" ]; then
        echo "  uv tidak ditemukan. Jalankan pemeriksaan dulu."
        jeda
        return
    fi
    "$UV" pip install --reinstall -r requirements.txt
    jeda
}

# =============================================================================
#  MENU
# =============================================================================

periksa_semua

while true; do
    echo "  ============================================================"
    echo "    MENU"
    echo "  ============================================================"
    echo
    echo "    [1]  Jalankan DASHBOARD          <-- yang paling sering dipakai"
    echo "    [2]  Jalankan pipeline Tahap 2   mode uji, aman"
    echo "    [3]  Buat ulang data dummy"
    echo "    [4]  Pasang ulang semua paket"
    echo "    [5]  Periksa ulang kebutuhan"
    echo "    [0]  Keluar"
    echo
    PILIH=""
    read -r -p "  Pilih [0-5]: " PILIH
    echo
    case "$PILIH" in
        1) jalan_dashboard; periksa_semua ;;
        2) jalan_pipeline;  periksa_semua ;;
        3) buat_dummy;      periksa_semua ;;
        4) pasang_paket;    periksa_semua ;;
        5) periksa_semua ;;
        0) exit 0 ;;
        *) echo "  Pilihan tidak dikenal."; echo ;;
    esac
done
