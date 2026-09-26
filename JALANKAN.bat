@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title BIA Kelompok 04 - Analisis Sentimen Pelantikan Prabowo-Gibran

REM ===========================================================================
REM  JALANKAN.bat -- pemeriksa kebutuhan + peluncur proyek, satu file.
REM
REM  Cara pakai: klik dua kali file ini. Tidak perlu buka terminal.
REM
REM  Yang dikerjakan:
REM    1. Periksa semua yang dibutuhkan proyek ini
REM    2. Pasang sendiri yang kurang  (setelah minta izin)
REM    3. Tampilkan menu untuk menjalankan dashboard / pipeline
REM
REM  Kelompok 04 - ISYS8036042 Business Intelligence and Analytics
REM ===========================================================================

set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "UV="
set "PY_DASAR="
set "STATUS_UV=BELUM"
set "STATUS_PY=BELUM"
set "STATUS_VENV=BELUM"
set "STATUS_PAKET=BELUM"
set "STATUS_DATA=BELUM"
set "STATUS_LEX=BELUM"
set "INFO_UV="
set "INFO_PY="
set "INFO_VENV="
set "INFO_PAKET="
set "INFO_DATA="
set "INFO_LEX="
set "PERLU_PERBAIKAN=0"

REM ===========================================================================
:MULAI
cls
echo.
echo  ============================================================
echo    BIA Kelompok 04 - Analisis Sentimen Pelantikan
echo    Pemeriksaan kebutuhan
echo  ============================================================
echo.

call :PERIKSA_UV
call :PERIKSA_PYTHON
call :PERIKSA_VENV
call :PERIKSA_PAKET
call :PERIKSA_DATA
call :PERIKSA_LEXICON

echo   [1/6] uv ................ !STATUS_UV!	!INFO_UV!
echo   [2/6] Python ............ !STATUS_PY!	!INFO_PY!
echo   [3/6] Virtualenv ........ !STATUS_VENV!	!INFO_VENV!
echo   [4/6] Paket Python ...... !STATUS_PAKET!	!INFO_PAKET!
echo   [5/6] Data dummy ........ !STATUS_DATA!	!INFO_DATA!
echo   [6/6] Kamus InSet ....... !STATUS_LEX!	!INFO_LEX!
echo.
echo  ------------------------------------------------------------

if "!PERLU_PERBAIKAN!"=="0" goto SIAP

echo.
echo   Ada yang belum siap. Semua bisa dipasang otomatis.
echo   Butuh koneksi internet, sekitar 2-4 menit untuk pertama kali.
echo.
set /p "IZIN=  Pasang sekarang? [Y/N] "
if /i "!IZIN!"=="Y" goto PERBAIKI
echo.
echo   Dibatalkan. Proyek belum bisa dijalankan.
echo.
pause
exit /b 1

REM ===========================================================================
:SIAP
echo.
echo   Semua siap. Proyek bisa dijalankan.
echo.
goto MENU

REM ===========================================================================
:MENU
echo  ============================================================
echo    MENU
echo  ============================================================
echo.
echo    [1]  Jalankan DASHBOARD          ^<-- yang paling sering dipakai
echo    [2]  Jalankan pipeline Tahap 2   mode uji, aman
echo    [3]  Buat ulang data dummy
echo    [4]  Pasang ulang semua paket
echo    [5]  Periksa ulang kebutuhan
echo    [0]  Keluar
echo.
set "PILIH="
set /p "PILIH=  Pilih [0-5]: "
echo.
if "!PILIH!"=="1" goto JALAN_DASHBOARD
if "!PILIH!"=="2" goto JALAN_PIPELINE
if "!PILIH!"=="3" goto BUAT_DUMMY
if "!PILIH!"=="4" goto PASANG_PAKET
if "!PILIH!"=="5" goto MULAI
if "!PILIH!"=="0" exit /b 0
echo   Pilihan tidak dikenal.
echo.
goto MENU

REM ===========================================================================
REM  PEMERIKSAAN
REM ===========================================================================

:PERIKSA_UV
REM uv dipakai karena bisa sekalian memasang Python-nya sendiri, jadi tidak
REM perlu instalasi Python manual lebih dulu.
for /f "delims=" %%i in ('where uv 2^>nul') do set "UV=%%i"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV (
    set "STATUS_UV=BELUM"
    set "INFO_UV=akan dipasang otomatis"
    set "PERLU_PERBAIKAN=1"
    goto :eof
)
for /f "tokens=2" %%v in ('"!UV!" --version 2^>nul') do set "INFO_UV=versi %%v"
set "STATUS_UV=OK   "
goto :eof

:PERIKSA_PYTHON
REM CATATAN PENTING: "python" yang ada di PATH Windows sering cuma jalan pintas
REM ke Microsoft Store, bukan Python beneran. Kalau dijalankan, dia malah buka
REM halaman Store. Jadi jalan pintas itu harus dikenali dan diabaikan.
if exist "%VENV_PY%" (
    for /f "tokens=2" %%v in ('"%VENV_PY%" --version 2^>^&1') do set "INFO_PY=%%v dari .venv"
    set "STATUS_PY=OK   "
    goto :eof
)
REM ADA312 wajib dikosongkan dulu. Pemeriksaan ini bisa dipanggil berkali-kali
REM lewat menu [5], dan variabel batch bertahan antar panggilan -- kalau tidak
REM dikosongkan, hasil pemeriksaan pertama akan menempel selamanya.
set "ADA312="
if defined UV (
    for /f "delims=" %%p in ('"!UV!" python list --only-installed 2^>nul ^| findstr /i "3.12"') do set "ADA312=1"
    if defined ADA312 (
        set "STATUS_PY=OK   "
        set "INFO_PY=3.12 tersedia lewat uv"
        goto :eof
    )
)
set "PY_STUB="
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo %%i | findstr /i "WindowsApps" >nul && set "PY_STUB=1"
)
set "STATUS_PY=BELUM"
if defined PY_STUB (
    set "INFO_PY=yang ada cuma stub Microsoft Store"
) else (
    set "INFO_PY=akan dipasang lewat uv"
)
set "PERLU_PERBAIKAN=1"
goto :eof

:PERIKSA_VENV
if exist "%VENV_PY%" (
    set "STATUS_VENV=OK   "
    set "INFO_VENV=.venv"
    goto :eof
)
set "STATUS_VENV=BELUM"
set "INFO_VENV=akan dibuat otomatis"
set "PERLU_PERBAIKAN=1"
goto :eof

:PERIKSA_PAKET
if not exist "%VENV_PY%" (
    set "STATUS_PAKET=BELUM"
    set "INFO_PAKET=menunggu virtualenv"
    set "PERLU_PERBAIKAN=1"
    goto :eof
)
"%VENV_PY%" -c "import streamlit,plotly,pandas,numpy,wordcloud,sklearn,selenium,matplotlib,scipy,Sastrawi,openpyxl" >nul 2>&1
if errorlevel 1 (
    set "STATUS_PAKET=BELUM"
    set "INFO_PAKET=ada yang kurang atau rusak"
    set "PERLU_PERBAIKAN=1"
    goto :eof
)
set "STATUS_PAKET=OK   "
set "INFO_PAKET=10 paket inti terpasang"
goto :eof

:PERIKSA_DATA
if not exist "data\processed\dataset_dummy.csv" (
    set "STATUS_DATA=BELUM"
    set "INFO_DATA=akan dibuat otomatis"
    set "PERLU_PERBAIKAN=1"
    goto :eof
)
set "STATUS_DATA=OK   "
if exist "data\processed\dataset_final.csv" (
    set "INFO_DATA=dummy + DATA ASLI sudah ada"
) else (
    set "INFO_DATA=dummy siap, data asli belum"
)
goto :eof

:PERIKSA_LEXICON
REM InSet TIDAK ikut di-commit dan TIDAK boleh dikarang. Hanya dibutuhkan untuk
REM labeling data asli; pipeline mode uji memakai kamus mini bawaan.
if exist "lexicon\positive.tsv" if exist "lexicon\negative.tsv" (
    set "STATUS_LEX=OK   "
    set "INFO_LEX=InSet terpasang"
    goto :eof
)
REM Sengaja TIDAK menaikkan PERLU_PERBAIKAN: ini bukan penghalang untuk
REM menjalankan dashboard maupun pipeline mode uji.
set "STATUS_LEX=BELUM"
set "INFO_LEX=perlu untuk data asli, unduh manual"
goto :eof

REM ===========================================================================
REM  PERBAIKAN
REM ===========================================================================

:PERBAIKI
echo.
echo  ============================================================
echo    Memasang kebutuhan
echo  ============================================================
echo.

if not defined UV (
    echo   - Memasang uv ...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
    if not defined UV (
        echo.
        echo   GAGAL memasang uv. Periksa koneksi internet, lalu coba lagi.
        echo   Alternatif: pasang Python 3.12 manual dari python.org
        echo   dan centang "Add Python to PATH" saat memasang.
        echo.
        pause
        exit /b 1
    )
    echo   uv terpasang.
    echo.
)

echo   - Memastikan Python 3.12 tersedia ...
"!UV!" python install 3.12
if errorlevel 1 goto GAGAL_PASANG

if exist "%VENV_PY%" echo   - Virtualenv .venv sudah ada, dilewati.
if not exist "%VENV_PY%" (
    echo.
    echo   - Membuat virtualenv .venv ...
    "!UV!" venv --python 3.12 --seed
    if errorlevel 1 goto GAGAL_PASANG
)

echo.
echo   - Memasang paket dari requirements.txt ...
echo       Sabar, ini bagian paling lama.
"!UV!" pip install -r requirements.txt
if errorlevel 1 goto GAGAL_PASANG

if exist "data\processed\dataset_dummy.csv" echo   - Data dummy sudah ada, dilewati.
if not exist "data\processed\dataset_dummy.csv" (
    echo.
    echo   - Membuat data dummy ...
    "%VENV_PY%" src\make_dummy.py
    if errorlevel 1 goto GAGAL_PASANG
)

echo.
echo  ------------------------------------------------------------
echo   Selesai. Memeriksa ulang ...
echo.
timeout /t 2 /nobreak >nul
set "PERLU_PERBAIKAN=0"
goto MULAI

:GAGAL_PASANG
echo.
echo  ------------------------------------------------------------
echo   GAGAL. Pesan kesalahan ada di atas.
echo.
echo   Yang biasanya jadi penyebab:
echo     - tidak ada koneksi internet
echo     - antivirus memblokir unduhan
echo     - folder proyek ada di dalam OneDrive yang sedang menyinkron
echo.
pause
exit /b 1

REM ===========================================================================
REM  MENJALANKAN
REM ===========================================================================

:JALAN_DASHBOARD
echo  ============================================================
echo    Menjalankan dashboard
echo  ============================================================
echo.
echo   Browser akan terbuka sendiri di http://localhost:8501
echo   Tekan CTRL+C di jendela ini untuk menghentikan.
echo.
if not exist "data\processed\dataset_final.csv" (
    echo   CATATAN: data asli belum ada, dashboard memakai DATA DUMMY.
    echo   Akan ada banner merah di atas halaman. Itu memang disengaja.
    echo.
)
REM --server.headless=false supaya browser terbuka sendiri. Berkas
REM .streamlit\config.toml menyetel headless=true untuk pemakaian dari
REM terminal; di sini sengaja ditimpa karena filenya diklik dua kali.
"%VENV_PY%" -m streamlit run dashboard\app.py --server.headless=false
echo.
echo   Dashboard berhenti.
echo.
pause
goto MULAI

:JALAN_PIPELINE
echo  ============================================================
echo    Pipeline Tahap 2 - MODE UJI
echo  ============================================================
echo.
echo   Menjalankan: data mentah kotor -^> bersihkan -^> labeli -^> latih SVM
echo.
echo   AMAN: semua keluaran berakhiran _demo. dataset_final.csv tidak
echo   akan tersentuh, jadi dashboard tetap memakai data dummy.
echo.
echo   Lama sekitar 15 detik.
echo.
pause
echo.
echo  --- 1/4  membuat data mentah yang sengaja kotor ---
"%VENV_PY%" src\make_dummy_raw.py
if errorlevel 1 goto GAGAL_PIPELINE
echo.
echo  --- 2/4  preprocessing ---
"%VENV_PY%" src\preprocess.py --demo
if errorlevel 1 goto GAGAL_PIPELINE
echo.
echo  --- 3/4  labeling berbasis lexicon ---
"%VENV_PY%" src\labeling.py --demo
if errorlevel 1 goto GAGAL_PIPELINE
echo.
echo  --- 4/4  melatih SVM + confusion matrix ---
"%VENV_PY%" src\train_model.py --demo
if errorlevel 1 goto GAGAL_PIPELINE
echo.
echo  ------------------------------------------------------------
echo   Pipeline selesai. Hasilnya di data\processed\ dan data\model\
echo.
echo   INGAT: angka dari mode uji TIDAK BOLEH masuk laporan.
echo   Kamus mini bawaan disusun dari kosakata yang sama dengan
echo   generator datanya, jadi pengujiannya sirkular.
echo.
pause
goto MULAI

:GAGAL_PIPELINE
echo.
echo   Pipeline berhenti karena ada kesalahan. Lihat pesan di atas.
echo.
pause
goto MULAI

:BUAT_DUMMY
echo   Membuat ulang data dummy ...
echo.
"%VENV_PY%" src\make_dummy.py
echo.
pause
goto MULAI

:PASANG_PAKET
echo   Memasang ulang semua paket ...
echo.
if not defined UV (
    echo   uv tidak ditemukan. Jalankan pemeriksaan dulu.
    pause
    goto MULAI
)
"!UV!" pip install --reinstall -r requirements.txt
echo.
pause
goto MULAI
