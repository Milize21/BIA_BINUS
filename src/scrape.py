"""
scrape.py -- TAHAP 1: ambil tweet dari X pakai Selenium.

INPUT   : keyword + rentang tanggal (20 Sep - 19 Nov 2024)
OUTPUT  : data/raw/tweets_<slug>_<tanggal-jalan>.csv   (CSV MENTAH, 5 kolom
          kontrak + 3 kolom bantu yang diabaikan preprocess.py)

    python src/scrape.py --login             # sekali saja, di awal
    python src/scrape.py                     # semua keyword, seluruh rentang
    python src/scrape.py --keyword "pelantikan prabowo"
    python src/scrape.py --mulai 2024-10-18 --selesai 2024-10-22
    python src/scrape.py --lengkapi          # susul teks tweet yang kepotong

=== KENAPA HARUS LOGIN, DAN KENAPA CARANYA BEGINI ===

X menolak menampilkan hasil pencarian ke pengunjung yang belum login. Jadi
scraping tanpa sesi login akan menghasilkan halaman kosong -- bukan error,
cuma nol tweet, dan itu menyesatkan.

Skrip ini TIDAK PERNAH meminta atau menyimpan password. Yang dilakukan:
`--login` membuka jendela browser biasa, kamu login sendiri seperti biasa
(termasuk 2FA kalau ada), dan begitu kamu sampai beranda skripnya TAHU SENDIRI
lalu menyimpan COOKIE sesinya ke .x_session.json. Tidak ada yang perlu ditekan
di terminal. Jalan berikutnya cookie itu dipakai ulang.

    .x_session.json itu setara kunci akun. Sudah masuk .gitignore.
    JANGAN di-commit, jangan dikirim ke grup, jangan ditaruh di Drive.

Pakai akun yang kamu siap kehilangan aksesnya. Scraping melanggar ToS X, dan
konsekuensi paling mungkin adalah akun kena limit atau suspend -- bukan
sesuatu yang layak dipertaruhkan dengan akun utama.

=== SATU HARI SATU QUERY ===

Rentangnya dipecah per hari, bukan sekali tarik dua bulan. Alasannya bukan
kerapian: X memotong hasil pencarian rentang panjang secara sepihak, dan yang
terpotong tidak diberi tahu. Query harian membuat tiap hari punya plafon
sendiri, jadi Hari-H yang ramai tidak menenggelamkan hari-hari sepi.

Konsekuensinya ada 61 query per keyword. Itu lama. Memang begitu.

=== TEKS KEPOTONG ===

X memendekkan tweet panjang jadi "... Show more", dan di timeline pencarian
teks penuhnya memang tidak ada di DOM -- harus buka halaman tweet-nya.

Dua pilihan, dua-duanya sah:

  DEFAULT       : tweet kepotong tetap diambil apa adanya dan ditandai di
                  kolom `kepotong`. preprocess.py nanti MEMBUANGNYA dan
                  melaporkan jumlahnya. Aman, cepat, jujur.

  --lengkapi    : setelah satu hari selesai digulir, tiap tweet kepotong
                  dibuka halamannya satu per satu untuk mengambil teks penuh.
                  Hasilnya lebih utuh, tapi jumlah permintaan ke X berlipat
                  dan risiko kena limit naik tajam.

Kalau angka kepotong di akhir laporan besar (>10%), barulah --lengkapi layak
dipertimbangkan. Jangan dinyalakan dari awal.

=== ZONA WAKTU: INI MASUK LAPORAN ===

X memberi waktu tweet dalam UTC. Dashboard punya heatmap "jam x hari", dan
heatmap dalam UTC akan salah baca sekitar 7 jam untuk percakapan Indonesia --
puncak jam 20.00 WIB akan tampil di jam 13.00.

Maka tanggal DIKONVERSI KE WIB (UTC+7) sebelum ditulis. Kalau tim memutuskan
sebaliknya, pakai --utc, dan catat keputusannya -- ini kelihatan langsung di
heatmap dan wajib disebut di Methodology.

`since:`/`until:` TIDAK dihitung dalam UTC. Keduanya mengikuti zona waktu AKUN
yang dipakai login, dan `until:D` bersifat inklusif -- seluruh hari D ikut.
Diukur langsung: "since:2024-10-20 until:2024-10-20" mengembalikan tweet 20 Okt
00:00 sampai 23:59 WIB, tepat satu hari WIB penuh.

Konsekuensinya yang harus diingat: hasil panen bergantung pada SETELAN ZONA
WAKTU AKUN. Kalau anggota tim lain memanen dengan akun yang zonanya bukan WIB,
batas harinya bergeser dan angkanya tidak akan sama persis. Kalau panennya
dibagi ke beberapa orang, samakan dulu setelan zona waktu akunnya, dan sebut
di Methodology bahwa panen dilakukan dengan akun ber-zona WIB.

Untuk memastikan sendiri kapan pun ragu: python src/cek_query.py

=== SOPAN SANTUN, DAN KENAPA BUKAN SEKADAR BASA-BASI ===

Jeda acak, gulir bertahap, dan jeda antarhari bukan hiasan. Pola permintaan
yang terlalu rapi dan cepat adalah yang paling gampang dikenali sebagai bot,
dan begitu akunnya kena limit, seluruh scraping berhenti -- bukan cuma
melambat. Menaikkan --cepat berarti menukar kestabilan dengan waktu.

=== KALAU MENTOK ===

Scraping X memang bisa gagal total karena hal di luar kendali kita. Kalau
setelah dicoba sungguhan tetap tidak jalan, rubrik mengizinkan memakai
dataset publik atau simulasi. Catat keputusannya, jangan diam-diam.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        NoSuchElementException,
        StaleElementReferenceException,
        TimeoutException,
        WebDriverException,
    )
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:
    raise SystemExit(
        "Selenium belum terpasang.\n"
        "  Jalankan JALANKAN.bat / JALANKAN.command, atau:\n"
        "  uv pip install -r requirements.txt"
    )

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
SESI = ROOT / ".x_session.json"

# Samakan dengan preprocess.py. Di luar rentang ini preprocess akan membuangnya.
MULAI = date(2024, 9, 20)
SELESAI = date(2024, 11, 19)

# Lima kolom pertama WAJIB -- itu kontrak yang diperiksa preprocess.py.
# Tiga sisanya kolom bantu: dipakai skrip ini untuk dedup dan resume, dan
# diabaikan preprocess.py tanpa perlu diapa-apakan.
KOLOM = ["tanggal", "teks", "likes", "retweet", "username", "id", "url", "kepotong"]

KEYWORDS = [
    "pelantikan prabowo",
    "prabowo gibran",
    "pelantikan presiden",
    "#PelantikanPresiden",
]

WIB = timezone(timedelta(hours=7))

# --------------------------------------------------------------- selektor DOM
#
# SEMUA selektor dikumpulkan di sini, bukan disebar di dalam fungsi. X mengubah
# markup-nya beberapa kali setahun, dan kalau itu terjadi yang perlu diperbaiki
# cuma blok ini. Kalau panen tiba-tiba nol padahal halamannya terlihat normal,
# tersangka pertama adalah bagian ini -- buka DevTools, cocokkan, perbaiki di
# sini saja.

SEL_KARTU = 'article[data-testid="tweet"]'
SEL_TEKS = '[data-testid="tweetText"]'
SEL_SHOWMORE = '[data-testid="tweet-text-show-more-link"]'
SEL_LIKE = '[data-testid="like"], [data-testid="unlike"]'
SEL_RT = '[data-testid="retweet"], [data-testid="unretweet"]'
SEL_WAKTU = "time"

# Halaman pijakan untuk memasang cookie: pasti 200, berkas teks kecil tanpa JS,
# dan paling ringan buat server X. Alasan lengkapnya di muat_sesi().
URL_PIJAKAN = "https://x.com/robots.txt"

# Tanpa dua ini sesi login tidak ada artinya: auth_token identitasnya, ct0 token
# CSRF yang diminta X di tiap permintaan.
COOKIE_WAJIB = ("auth_token", "ct0")

# Bukti bahwa sesi BENAR-BENAR login. Semuanya cuma muncul kalau sudah masuk;
# di halaman pengunjung yang ada hanya BottomBar dan tombol-tombol "Lanjutkan
# dengan Google/Apple". Satu saja ketemu sudah cukup -- X tidak selalu
# menampilkan keempatnya, tergantung lebar jendela.
SEL_BUKTI_LOGIN = (
    '[data-testid="SideNav_AccountSwitcher_Button"],'
    '[data-testid="AppTabBar_Home_Link"],'
    '[data-testid="SideNav_NewTweet_Button"],'
    '[data-testid="primaryColumn"]'
)

# Penanda halaman gagal / kena limit. Dicek sebagai teks halaman apa adanya,
# sengaja dua bahasa karena antarmuka X ikut bahasa akun.
TANDA_MENTOK = (
    "Something went wrong",
    "Terjadi kesalahan",
    "Rate limit exceeded",
    "Try again",
    "Coba lagi",
)

RE_ID_STATUS = re.compile(r"/status/(\d+)")
RE_SPASI = re.compile(r"\s+")


# ------------------------------------------------------------------- utilitas

def slug(teks: str) -> str:
    """Nama berkas yang aman: '#PelantikanPresiden' -> 'pelantikanpresiden'."""
    return re.sub(r"[^a-z0-9]+", "_", teks.lower()).strip("_")


def tidur(kecil: float, besar: float) -> None:
    time.sleep(random.uniform(kecil, besar))


def rentang_hari(mulai: date, selesai: date):
    h = mulai
    while h <= selesai:
        yield h
        h += timedelta(days=1)


def teks_satu_baris(t: str) -> str:
    """
    Ratakan tweet multi-baris jadi satu baris.

    CSV sebenarnya sanggup menyimpan newline di dalam sel, tapi berkasnya jadi
    tidak bisa dibaca sekilas dan gampang rusak kalau ada yang iseng membukanya
    di Excel lalu menyimpan ulang. preprocess.py toh merapikan spasi juga.
    """
    return RE_SPASI.sub(" ", t.replace("\n", " ")).strip()


# ---------------------------------------------------------------------- sesi

def buat_driver(headless: bool) -> webdriver.Chrome:
    """
    Chrome lewat Selenium Manager -- driver-nya terunduh sendiri.

    Selenium 4.6+ sudah punya Selenium Manager, jadi tidak perlu
    webdriver-manager dan tidak perlu mencocokkan versi chromedriver manual.
    """
    opsi = Options()
    if headless:
        opsi.add_argument("--headless=new")
    opsi.add_argument("--window-size=1280,1000")
    opsi.add_argument("--lang=id-ID")
    # Menyembunyikan penanda otomasi yang paling kentara. Ini bukan penyamaran
    # sungguhan -- X tetap bisa mengenali, dan memang tidak diusahakan.
    opsi.add_argument("--disable-blink-features=AutomationControlled")
    opsi.add_experimental_option("excludeSwitches", ["enable-automation"])
    opsi.add_experimental_option("useAutomationExtension", False)
    try:
        return webdriver.Chrome(options=opsi)
    except WebDriverException as e:
        raise SystemExit(
            f"Gagal menjalankan Chrome: {e}\n\n"
            "  Pastikan Google Chrome terpasang. Selenium mengunduh driver-nya\n"
            "  sendiri, tapi browser-nya tetap harus ada."
        )


def simpan_sesi(driver) -> None:
    SESI.write_text(json.dumps(driver.get_cookies(), indent=2), encoding="utf-8")
    print(f"\nOK  Cookie sesi disimpan -> {SESI.name}")
    print("    JANGAN di-commit dan jangan dibagikan. Itu setara kunci akun.")


def muat_sesi(driver) -> bool:
    """
    Pasang cookie yang tersimpan. False kalau berkasnya belum ada.

    JANGAN ganti URL_PIJAKAN jadi "https://x.com/". Root-nya membalas HTTP 403
    ke browser otomatis, dan halaman error punya origin `null` -- akibatnya
    SEMUA add_cookie ditolak InvalidCookieDomainException padahal cookie-nya
    sendiri sehat dan belum kedaluwarsa. Gejalanya menyesatkan: yang terbaca
    seolah sesinya kedaluwarsa, jadi orang mengulang --login berkali-kali dan
    tetap gagal. Cookie hanya bisa dipasang kalau browser sedang berada di
    origin yang sama DAN halamannya benar-benar termuat.
    """
    if not SESI.exists():
        return False
    driver.get(URL_PIJAKAN)
    tidur(1.5, 2.5)

    terpasang, rusak = set(), []
    for c in json.loads(SESI.read_text(encoding="utf-8")):
        c.pop("sameSite", None)  # nilai dari Chrome kadang ditolak saat dipasang
        try:
            driver.add_cookie(c)
            terpasang.add(c.get("name"))
        except WebDriverException as e:
            rusak.append(type(e).__name__)

    # Dulu bagian ini cuma mencetak "(N cookie dilewati, biasanya tidak apa-apa)"
    # -- kalimat yang tetap terdengar menenangkan walaupun yang gagal SEMUANYA.
    # Sekarang yang diperiksa cookie yang menentukan, dan kalau ia tidak
    # terpasang skripnya berhenti, bukan lanjut memanen halaman kosong.
    hilang = [n for n in COOKIE_WAJIB if n not in terpasang]
    if hilang:
        raise SystemExit(
            "Cookie penting gagal dipasang: {}{}\n"
            "  {} dari {} cookie ditolak browser.\n\n"
            "  Kalau SEMUA ditolak, biasanya halaman pijakan tidak termuat --\n"
            "  coba buka {} di browser biasa.\n"
            "  Kalau cuma sebagian, sesinya kemungkinan sudah kedaluwarsa:\n"
            "    python src/scrape.py --login".format(
                ", ".join(hilang),
                f" ({rusak[0]})" if rusak else "",
                len(rusak),
                len(rusak) + len(terpasang),
                URL_PIJAKAN,
            )
        )
    if rusak:
        print(f"  ({len(rusak)} cookie sampingan dilewati, yang wajib aman)")
    return True


def sudah_login(driver) -> bool:
    """
    Pastikan sesi benar-benar login, bukan sekadar 'tidak dilempar ke /login'.

    JANGAN diubah jadi pemeriksaan URL saja. Pengunjung yang belum login TIDAK
    dilempar ke /login: X diam-diam menyajikan halaman depan di https://x.com/
    lengkap dengan formulir masuk, dan URL-nya bersih dari kata 'login'. Cara
    lama ("/login" not in current_url) karena itu selalu menjawab True, panen
    jalan terus, dan hasilnya 0 tweet untuk seluruh 244 query tanpa satu pun
    pesan error -- persis kegagalan diam yang paling mahal di proyek ini.

    Maka yang dicari BUKTI POSITIF: elemen yang cuma ada kalau sudah masuk.
    Kalau tidak ketemu, jawabannya False. Salah menuduh 'belum login' cuma
    memaksa --login sekali lagi; salah meluluskan berarti berjam-jam panen
    kosong yang baru ketahuan di akhir.
    """
    driver.get("https://x.com/home")
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, SEL_BUKTI_LOGIN))
        )
        return True
    except TimeoutException:
        return False


def tunggu_login(driver, batas_menit: float) -> bool:
    """
    Tunggu sampai login terdeteksi sendiri. True kalau berhasil.

    SENGAJA TIDAK PAKAI input(). Dulu fungsi ini menyuruh menekan Enter, dan itu
    mematikan skripnya di terminal mana pun yang stdin-nya tidak tersambung --
    dijalankan dari editor, dari skrip lain, dari agen -- langsung EOFError
    sebelum sempat menyimpan apa pun.

    JUGA TIDAK memanggil sudah_login(), walaupun pertanyaannya sama persis.
    Fungsi itu PINDAH HALAMAN ke /home untuk memeriksa, dan kalau dipanggil
    sementara kamu masih mengetik, formulir loginnya hilang di tengah jalan --
    termasuk kode 2FA yang sudah separuh dimasukkan. Di sini halamannya
    dibiarkan apa adanya, cuma diintip apakah penandanya sudah muncul.
    """
    batas = time.time() + batas_menit * 60
    lapor_berikutnya = time.time() + 30
    while time.time() < batas:
        try:
            if driver.find_elements(By.CSS_SELECTOR, SEL_BUKTI_LOGIN):
                return True
        except WebDriverException:
            print("\n  Jendela Chrome-nya ditutup. Cookie TIDAK disimpan.")
            return False
        if time.time() >= lapor_berikutnya:
            print(f"    ... masih menunggu ({(batas - time.time()) / 60:.0f} menit lagi)")
            lapor_berikutnya = time.time() + 30
        time.sleep(2)
    return False


def login_manual(batas_menit: float) -> None:
    """Buka browser, biarkan pengguna login sendiri, lalu simpan cookie."""
    print()
    print("  ============================================================")
    print("    LOGIN KE X")
    print("  ============================================================")
    print()
    print("  Jendela Chrome akan terbuka. Login seperti biasa di situ.")
    print("  Password diketik langsung ke X, TIDAK lewat skrip ini dan")
    print("  tidak disimpan di mana pun.")
    print()
    print("  Tidak perlu menekan apa pun di terminal ini -- begitu kamu")
    print("  sampai beranda, cookie-nya tersimpan sendiri.")
    print()
    print("  Pakai akun cadangan, bukan akun utama.")
    print()

    driver = buat_driver(headless=False)
    try:
        driver.get("https://x.com/login")
        print(f"  Menunggu kamu selesai login (batas {batas_menit:.0f} menit) ...")
        if not tunggu_login(driver, batas_menit):
            print("\n  Login tidak terdeteksi. Cookie TIDAK disimpan.")
            print("  Kalau tadi kurang waktu:  --login --tunggu 15")
            return
        print("\n  Login terdeteksi.")
        simpan_sesi(driver)
    finally:
        driver.quit()


# -------------------------------------------------------------------- panen

def angka_dari(kartu, selektor: str) -> str:
    """
    Ambil angka likes/retweet sebagai TEKS APA ADANYA ('1.2K', '3,456', '').

    Sengaja tidak diubah jadi integer di sini. preprocess.parse_angka() sudah
    tahu cara membaca format X, dan satu tempat yang mengurus itu lebih mudah
    dipertanggungjawabkan daripada dua tempat yang bisa berbeda diam-diam.

    Tombol tanpa angka berarti nol -- X memang menyembunyikan angka nol.
    """
    try:
        el = kartu.find_element(By.CSS_SELECTOR, selektor)
    except (NoSuchElementException, StaleElementReferenceException):
        return "0"
    teks = (el.text or "").strip()
    if teks:
        return teks
    # Cadangan: aria-label biasanya berbunyi "1234 Likes" / "1234 suka".
    label = el.get_attribute("aria-label") or ""
    m = re.search(r"[\d.,]+", label)
    return m.group(0) if m else "0"


def baca_kartu(kartu, utc: bool) -> dict | None:
    """Ubah satu <article> jadi satu baris. None kalau kartunya tidak utuh."""
    try:
        waktu_el = kartu.find_element(By.CSS_SELECTOR, SEL_WAKTU)
        iso = waktu_el.get_attribute("datetime")
        if not iso:
            return None

        # Permalink ada di <a> pembungkus <time>. Dari situ sekaligus didapat
        # id tweet dan username -- dua-duanya tanpa perlu selektor tambahan
        # yang gampang berubah.
        tautan = waktu_el.find_element(By.XPATH, "./ancestor::a[1]")
        url = tautan.get_attribute("href") or ""
        m = RE_ID_STATUS.search(url)
        if not m:
            return None
        tweet_id = m.group(1)
        username = url.split("/status/")[0].rstrip("/").rsplit("/", 1)[-1]

        try:
            teks = kartu.find_element(By.CSS_SELECTOR, SEL_TEKS).text
        except (NoSuchElementException, StaleElementReferenceException):
            # Tweet gambar/video tanpa teks. Tidak berguna untuk analisis
            # sentimen berbasis teks, jadi dilewati.
            return None

        kepotong = bool(kartu.find_elements(By.CSS_SELECTOR, SEL_SHOWMORE))

        saat = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if not utc:
            saat = saat.astimezone(WIB)

        return {
            "tanggal": saat.strftime("%Y-%m-%d %H:%M:%S"),
            "teks": teks_satu_baris(teks),
            "likes": angka_dari(kartu, SEL_LIKE),
            "retweet": angka_dari(kartu, SEL_RT),
            "username": username,
            "id": tweet_id,
            "url": url,
            "kepotong": "1" if kepotong else "0",
        }
    except (NoSuchElementException, StaleElementReferenceException, ValueError):
        return None


def halaman_mentok(driver) -> bool:
    try:
        tubuh = driver.find_element(By.TAG_NAME, "body").text
    except WebDriverException:
        return False
    return any(t in tubuh for t in TANDA_MENTOK)


def panen_sehari(driver, keyword: str, hari: date, args) -> tuple[list[dict], bool]:
    """
    Gulir satu halaman pencarian sampai habis, kembalikan (baris, kena_limit).

    Timeline X itu virtual: kartu yang sudah lewat DIHAPUS dari DOM supaya
    halaman tidak membengkak. Jadi memanen harus dilakukan SAMBIL menggulir,
    bukan sekali di akhir -- kalau di akhir, yang tersisa cuma layar terakhir.
    """
    # DUA HAL DI QUERY INI SUDAH PERNAH SALAH. Jangan diubah tanpa mengukur
    # ulang dengan src/cek_query.py.
    #
    # 1. TANPA `lang:id`. Kelihatannya masuk akal -- kita memang cuma mau tweet
    #    Indonesia -- tapi digabung since:/until: hasilnya SELALU NOL. Diuji
    #    pada 20 Okt 2024: dengan lang:id 0 tweet, tanpa lang:id 37 tweet, query
    #    selebihnya sama persis. Gagalnya pun diam: X menjawab "No results",
    #    bukan error, jadi 244 query bisa habis tanpa satu baris pun terkumpul.
    #    Penyaringan bahasa dikerjakan belakangan; keyword-nya sudah frasa
    #    Indonesia, jadi yang lolos mayoritas memang Indonesia.
    #
    # 2. `until:{hari}`, BUKAN besok. `until:D` itu INKLUSIF dan mengikuti zona
    #    waktu akun (WIB untuk akun Indonesia), jadi since:D until:D = tepat
    #    satu hari WIB penuh. Versi lama memakai until:besok sehingga tiap query
    #    menjaring dua hari; karena hasil diurut terbaru-dulu dan ada plafon
    #    --maks per hari, plafonnya habis dipakai hari yang lebih baru dan hari
    #    yang lebih tua nyaris tidak kebagian.
    query = f"{keyword} since:{hari:%Y-%m-%d} until:{hari:%Y-%m-%d}"
    # f=live = tab "Latest". Tanpa ini X memberi tab "Top" yang sudah disaring
    # algoritma -- hasilnya bias ke tweet populer dan tidak bisa dipakai untuk
    # mengukur distribusi sentimen.
    driver.get(f"https://x.com/search?q={quote(query)}&src=typed_query&f=live")
    tidur(*args.jeda_muat)

    terkumpul: dict[str, dict] = {}
    tanpa_tambahan = 0
    gulir = 0

    while True:
        if halaman_mentok(driver):
            return list(terkumpul.values()), True

        sebelum = len(terkumpul)
        for kartu in driver.find_elements(By.CSS_SELECTOR, SEL_KARTU):
            baris = baca_kartu(kartu, args.utc)
            if baris and baris["id"] not in terkumpul:
                terkumpul[baris["id"]] = baris

        if len(terkumpul) == sebelum:
            tanpa_tambahan += 1
        else:
            tanpa_tambahan = 0

        if tanpa_tambahan >= args.sabar:
            break
        if args.maks and len(terkumpul) >= args.maks:
            break
        if gulir >= args.maks_gulir:
            print("      (batas gulir tercapai, hari ini mungkin belum habis)")
            break

        driver.execute_script("window.scrollBy(0, arguments[0]);", random.randint(700, 1200))
        gulir += 1
        tidur(*args.jeda_gulir)

    return list(terkumpul.values()), False


def lengkapi_kepotong(driver, baris: list[dict], args) -> int:
    """
    Buka halaman tiap tweet kepotong untuk mengambil teks penuhnya.

    Dipanggil hanya kalau --lengkapi. Satu tweet satu kunjungan halaman, jadi
    ini bagian yang paling boros dan paling gampang memicu limit. Kalau satu
    tweet gagal diambil, biarkan versi kepotongnya -- preprocess.py yang akan
    membuangnya, dan itu jauh lebih baik daripada menghentikan seluruh panen.
    """
    sasaran = [b for b in baris if b["kepotong"] == "1"]
    if not sasaran:
        return 0
    print(f"      melengkapi {len(sasaran)} tweet kepotong ...")
    berhasil = 0
    for b in sasaran:
        try:
            driver.get(b["url"])
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, SEL_TEKS))
            )
            penuh = driver.find_element(By.CSS_SELECTOR, SEL_TEKS).text
            if len(penuh) > len(b["teks"]):
                b["teks"] = teks_satu_baris(penuh)
                b["kepotong"] = "0"
                berhasil += 1
        except (TimeoutException, WebDriverException):
            pass
        tidur(*args.jeda_gulir)
    return berhasil


# -------------------------------------------------------------- simpan & resume

def path_keluaran(keyword: str) -> Path:
    return RAW_DIR / f"tweets_{slug(keyword)}_{date.today():%Y%m%d}.csv"


def path_progres(keyword: str) -> Path:
    return RAW_DIR / f".progres_{slug(keyword)}.json"


def baca_progres(keyword: str) -> set[str]:
    p = path_progres(keyword)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")).get("selesai", []))
    except (ValueError, OSError):
        return set()


def catat_progres(keyword: str, hari: date) -> None:
    """
    Tandai satu hari selesai, supaya scraping bisa dilanjutkan kalau putus.

    Hari dicatat HANYA setelah gulirnya tuntas. Kalau proses mati di tengah
    hari, hari itu tidak tercatat dan akan diulang penuh -- lebih baik memanen
    ulang satu hari daripada diam-diam kehilangan separuhnya.
    """
    p = path_progres(keyword)
    selesai = sorted(baca_progres(keyword) | {f"{hari:%Y-%m-%d}"})
    p.write_text(json.dumps({"selesai": selesai}, indent=2), encoding="utf-8")


def simpan(baris: list[dict], path: Path) -> None:
    """Tulis append per hari. Jangan tunggu selesai -- scraping gampang putus."""
    if not baris:
        return
    baru = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KOLOM)
        if baru:
            w.writeheader()
        w.writerows(baris)


def id_tersimpan(path: Path) -> set[str]:
    """Id yang sudah ada di berkas, supaya menjalankan ulang tidak menggandakan."""
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {r.get("id", "") for r in csv.DictReader(f)}


# ---------------------------------------------------------------------- main

def buat_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Ambil tweet dari X untuk analisis sentimen pelantikan.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--login", action="store_true", help="login sekali, simpan cookie sesi")
    p.add_argument("--tunggu", type=float, default=5.0,
                   help="batas menit menunggu login selesai (dipakai dengan --login)")
    p.add_argument("--keyword", action="append", help="boleh diulang; default semua keyword")
    p.add_argument("--mulai", default=f"{MULAI:%Y-%m-%d}")
    p.add_argument("--selesai", default=f"{SELESAI:%Y-%m-%d}")
    p.add_argument("--maks", type=int, default=400, help="batas tweet per hari (0 = tanpa batas)")
    p.add_argument("--maks-gulir", type=int, default=120, help="batas gulir per hari")
    p.add_argument("--sabar", type=int, default=5, help="berhenti setelah N gulir tanpa tweet baru")
    p.add_argument("--lengkapi", action="store_true", help="susul teks tweet yang kepotong")
    p.add_argument("--utc", action="store_true", help="simpan waktu UTC, jangan konversi ke WIB")
    p.add_argument("--headless", action="store_true", help="tanpa jendela browser")
    p.add_argument("--cepat", action="store_true", help="jeda lebih pendek; lebih gampang kena limit")
    p.add_argument("--ulang", action="store_true", help="abaikan catatan progres, panen ulang semua")
    return p


def main() -> None:
    args = buat_parser().parse_args()

    if args.login:
        login_manual(args.tunggu)
        return

    # Jeda dikumpulkan di satu tempat supaya --cepat cukup mengubahnya di sini.
    if args.cepat:
        args.jeda_muat, args.jeda_gulir, args.jeda_hari = (2.0, 3.5), (0.9, 1.8), (2.0, 4.0)
    else:
        args.jeda_muat, args.jeda_gulir, args.jeda_hari = (3.5, 6.0), (1.8, 3.6), (5.0, 10.0)

    try:
        mulai = date.fromisoformat(args.mulai)
        selesai = date.fromisoformat(args.selesai)
    except ValueError:
        raise SystemExit("Format tanggal harus YYYY-MM-DD, contoh: --mulai 2024-10-18")
    if mulai > selesai:
        raise SystemExit("--mulai tidak boleh setelah --selesai")

    keywords = args.keyword or KEYWORDS
    if not SESI.exists():
        raise SystemExit(
            "Belum ada sesi login.\n\n"
            "  Jalankan dulu sekali:  python src/scrape.py --login\n\n"
            "  X menolak menampilkan hasil pencarian ke pengunjung yang belum\n"
            "  login, dan hasilnya halaman kosong tanpa pesan error."
        )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    total_hari = (selesai - mulai).days + 1
    print()
    print(f"  {len(keywords)} keyword x {total_hari} hari = {len(keywords) * total_hari} query")
    print(f"  {mulai:%d %b} - {selesai:%d %b %Y}  |  waktu {'UTC' if args.utc else 'WIB (UTC+7)'}")
    if args.cepat:
        print("  MODE CEPAT -- jeda dipendekkan, risiko kena limit naik.")
    print()

    driver = buat_driver(args.headless)
    ringkasan: list[tuple[str, int, int]] = []
    t0 = time.time()

    try:
        if not muat_sesi(driver):
            raise SystemExit("Gagal memuat .x_session.json. Ulangi: --login")
        if not sudah_login(driver):
            raise SystemExit(
                "Sesi login sudah kedaluwarsa atau ditolak X.\n"
                "  Perbarui: python src/scrape.py --login"
            )
        print("  Sesi login OK.\n")

        for keyword in keywords:
            out = path_keluaran(keyword)
            sudah_ada = id_tersimpan(out)
            selesai_hari = set() if args.ulang else baca_progres(keyword)
            n_keyword = n_potong = 0

            print(f"  === {keyword} ===")
            for hari in rentang_hari(mulai, selesai):
                tag = f"{hari:%Y-%m-%d}"
                if tag in selesai_hari:
                    continue

                try:
                    baris, kena_limit = panen_sehari(driver, keyword, hari, args)
                except WebDriverException as e:
                    print(f"    {tag}  browser bermasalah: {str(e)[:70]}")
                    break

                if kena_limit:
                    print(f"    {tag}  KENA LIMIT X -- berhenti untuk keyword ini.")
                    print("           Tunggu 15-30 menit, lalu jalankan lagi.")
                    print("           Progres tersimpan, hari yang sudah selesai dilewati.")
                    break

                if args.lengkapi and baris:
                    lengkapi_kepotong(driver, baris, args)

                # Buang yang sudah pernah tersimpan dari jalan sebelumnya.
                segar = [b for b in baris if b["id"] not in sudah_ada]
                sudah_ada.update(b["id"] for b in segar)
                simpan(segar, out)
                catat_progres(keyword, hari)

                potong = sum(1 for b in segar if b["kepotong"] == "1")
                n_keyword += len(segar)
                n_potong += potong
                print(f"    {tag}  {len(segar):>4} tweet"
                      + (f"  ({potong} kepotong)" if potong else ""))

                tidur(*args.jeda_hari)

            ringkasan.append((keyword, n_keyword, n_potong))
            print(f"    -> {n_keyword:,} baris ke {out.name}\n")

    except KeyboardInterrupt:
        print("\n  Dihentikan manual. Yang sudah terpanen tetap tersimpan.")
    finally:
        driver.quit()

    # ---- ringkasan (salin ke bagian Methodology laporan) ----
    print("  RINGKASAN PANEN")
    print("  " + "-" * 60)
    print("  | %-28s | %9s | %11s |" % ("Keyword", "Tweet", "Kepotong"))
    print("  |%s|%s|%s|" % ("-" * 30, "-" * 11, "-" * 13))
    total = potong_total = 0
    for k, n, p in ringkasan:
        print("  | %-28s | %9s | %11s |" % (k[:28], f"{n:,}", f"{p:,}"))
        total += n
        potong_total += p
    print("  |%s|%s|%s|" % ("-" * 30, "-" * 11, "-" * 13))
    print("  | %-28s | %9s | %11s |" % ("TOTAL", f"{total:,}", f"{potong_total:,}"))
    print("  " + "-" * 60)
    print(f"\n  Selesai dalam {(time.time() - t0) / 60:.1f} menit")

    if total and potong_total / total > 0.10:
        print()
        print(f"  CATATAN: {potong_total / total:.0%} tweet kepotong. preprocess.py akan")
        print("  membuangnya. Kalau angka ini terasa terlalu besar, jalankan ulang")
        print("  dengan --lengkapi untuk menyusul teks penuhnya.")

    print(f"\n    Lanjut:  python src/preprocess.py")


if __name__ == "__main__":
    main()
