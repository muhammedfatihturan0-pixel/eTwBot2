from __future__ import annotations

import base64
import io
import json
import os
import re
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
import streamlit as st

# =============================================================================
# TWIN — eTwinning Danışman / Streamlit sürümü
# Amaç: yerel bilgi bankası + düşük token Gemini sentezi + yalnız gerektiğinde web grounding
# =============================================================================

st.set_page_config(
    page_title="TwinBot · eTwinning Danışmanı",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_DIR = Path(__file__).resolve().parent
MASKOT_ADAYLARI = [
    APP_DIR / "twin.maskot.jpg",
    APP_DIR / "twin.maskot.jpeg",
    APP_DIR / "twin.maskot.png",
    APP_DIR / "twinmaskot.jpg",
    APP_DIR / "twin_maskot.jpg",
]
MASKOT = next((x for x in MASKOT_ADAYLARI if x.exists()), None)


def maskot_data_uri() -> str:
    if not MASKOT:
        return ""
    try:
        suffix = MASKOT.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        encoded = base64.b64encode(MASKOT.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    except Exception:
        return ""
PROJE_DOKTORU_MAX_METIN_KARAKTER = 120_000
DOSYA_BOYUT_LIMITI = 12 * 1024 * 1024


def secret_al(*adlar: str, varsayilan: str = "") -> str:
    for ad in adlar:
        try:
            deger = st.secrets.get(ad, "")
            if deger is not None and str(deger).strip():
                return str(deger).strip()
        except Exception:
            pass
        deger = os.getenv(ad, "")
        if deger and str(deger).strip():
            return str(deger).strip()
    return varsayilan


API_KEY = secret_al("GEMINI_API_KEY", "GOOGLE_API_KEY", "API_KEY")
AKTIF_MODEL = secret_al("GEMINI_MODEL", varsayilan="gemini-3.1-flash-lite")
ADMIN_TOKEN = secret_al("ADMIN_TOKEN")
ADMIN_PASSWORD = secret_al("ADMIN_PASSWORD", varsayilan="")
GUNCEL_WEB_ARAMA_AKTIF = secret_al("GUNCEL_WEB_ARAMA_AKTIF", varsayilan="1").lower() in {
    "1", "true", "evet", "yes", "on"
}

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{AKTIF_MODEL}:generateContent"

# -----------------------------------------------------------------------------
# Görünüm
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
:root {
  --blue-900:#082F63;
  --blue-800:#0B3D7A;
  --blue-700:#1557A6;
  --blue-100:#E8F1FF;
  --yellow-500:#F4C430;
  --yellow-300:#F8D96A;
  --yellow-100:#FFF5C9;
  --ink:#111827;
  --muted:#5B677A;
  --line:#CAD8EC;
  --white:#FFFFFF;
}
html, body, [class*="css"] { font-family: Inter, system-ui, -apple-system, "Segoe UI", Arial, sans-serif; }
.stApp {
  background: linear-gradient(180deg,#F7FAFF 0%,#EEF5FF 65%,#FFF9E8 100%);
  color:var(--ink);
}
.block-container {
  max-width:1180px;
  padding-top:1rem;
  padding-bottom:6.2rem;
}

/* Sidebar */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg,var(--blue-900) 0%,var(--blue-800) 100%);
  border-right:4px solid var(--yellow-500);
}
[data-testid="stSidebar"] * { color:#F8FBFF; }
[data-testid="stSidebar"] hr { border-color:rgba(255,255,255,.16); }
[data-testid="stSidebar"] .stButton>button,
[data-testid="stSidebar"] .stDownloadButton>button {
  width:100%;
  background:var(--yellow-500) !important;
  color:var(--blue-900) !important;
  border:0 !important;
  border-radius:12px !important;
  font-weight:800 !important;
}
[data-testid="stSidebar"] .stButton>button:hover,
[data-testid="stSidebar"] .stDownloadButton>button:hover {
  background:var(--yellow-300) !important;
}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
  background:#FFFFFF !important;
  color:#111827 !important;
}

/* Main brand */
.hero {
  display:grid;
  grid-template-columns:minmax(170px,230px) 1fr;
  gap:24px;
  align-items:center;
  background:linear-gradient(135deg,var(--blue-900) 0%,var(--blue-700) 76%);
  border:3px solid var(--yellow-500);
  border-radius:24px;
  padding:22px 26px;
  box-shadow:0 18px 40px rgba(8,47,99,.16);
  margin:.25rem 0 1rem;
}
.heroMascot {
  width:100%;
  max-width:220px;
  max-height:220px;
  object-fit:contain;
  border-radius:18px;
  background:#FFFFFF;
  border:4px solid var(--yellow-500);
  box-shadow:0 10px 24px rgba(0,0,0,.18);
}
.heroTitle {
  margin:0;
  color:#FFFFFF !important;
  font-size:2.25rem;
  font-weight:850;
  line-height:1.08;
  letter-spacing:-.025em;
}
.heroSubtitle {
  color:#EAF2FF !important;
  margin:.65rem 0 0;
  font-size:1rem;
  max-width:760px;
  line-height:1.55;
}
.heroAccent {
  width:92px;
  height:7px;
  background:var(--yellow-500);
  border-radius:99px;
  margin:0 0 .9rem;
}

/* Expanders / cards */
[data-testid="stExpander"] {
  background:rgba(255,255,255,.92);
  border:1px solid var(--line);
  border-radius:16px;
  box-shadow:0 8px 20px rgba(15,23,42,.05);
  overflow:hidden;
}
[data-testid="stExpander"] summary {
  color:var(--blue-900) !important;
  font-weight:800 !important;
}

/* Chat */
div[data-testid="stChatMessage"] {
  background:#FFFFFF !important;
  color:var(--ink) !important;
  border:1px solid var(--line) !important;
  border-left:5px solid var(--blue-700) !important;
  border-radius:16px !important;
  padding:14px 17px !important;
  margin-bottom:11px !important;
  box-shadow:0 7px 18px rgba(15,23,42,.055) !important;
}
div[data-testid="stChatMessage"] p,
div[data-testid="stChatMessage"] li,
div[data-testid="stChatMessage"] span,
div[data-testid="stChatMessage"] strong,
div[data-testid="stChatMessage"] h1,
div[data-testid="stChatMessage"] h2,
div[data-testid="stChatMessage"] h3,
div[data-testid="stChatMessage"] td,
div[data-testid="stChatMessage"] th,
div[data-testid="stChatMessage"] code {
  color:var(--ink) !important;
}

/* user messages: yellow accent */
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]),
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
  background:var(--yellow-100) !important;
  border-left-color:var(--yellow-500) !important;
  border-color:#E9CD61 !important;
}

.bank-badge,.web-badge {
  display:inline-block;
  border-radius:999px;
  padding:4px 9px;
  font-size:.72rem;
  font-weight:800;
  margin-top:.2rem;
}
.bank-badge { background:#EAF7EE;color:#166534; }
.web-badge { background:var(--blue-100);color:#1D4ED8; }

/* Chat input: ALWAYS white / black */
[data-testid="stChatInputContainer"] {
  background:rgba(247,250,255,.98) !important;
  border-top:1px solid #D4E0F0 !important;
  padding-top:.55rem !important;
}
[data-testid="stChatInput"] {
  background:#FFFFFF !important;
  border:2px solid var(--blue-700) !important;
  border-radius:16px !important;
  box-shadow:0 9px 24px rgba(8,47,99,.12) !important;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] textarea:focus,
[data-testid="stChatInput"] [contenteditable="true"],
[data-baseweb="textarea"] textarea {
  background:#FFFFFF !important;
  color:#000000 !important;
  -webkit-text-fill-color:#000000 !important;
  caret-color:#000000 !important;
}
[data-testid="stChatInput"] textarea::placeholder,
[data-baseweb="textarea"] textarea::placeholder {
  color:#667085 !important;
  -webkit-text-fill-color:#667085 !important;
  opacity:1 !important;
}
[data-testid="stChatInputSubmitButton"] button {
  background:var(--yellow-500) !important;
  color:var(--blue-900) !important;
  border-radius:12px !important;
  border:0 !important;
}

/* General controls */
.stButton>button, .stDownloadButton>button {
  background:var(--blue-900) !important;
  color:#FFFFFF !important;
  border:0 !important;
  border-radius:12px !important;
  font-weight:800 !important;
}
.stButton>button:hover, .stDownloadButton>button:hover { background:var(--blue-700) !important; }
.stTextInput input,.stTextArea textarea {
  background:#FFFFFF !important;
  color:#111827 !important;
  border:1px solid var(--line) !important;
  border-radius:12px !important;
}
.stTextInput input::placeholder,.stTextArea textarea::placeholder { color:#667085 !important; }
.stCaption, small { color:var(--muted) !important; }
hr { border:none;border-top:1px solid #D6E1EF;margin:1rem 0; }

@media(max-width:760px){
  .hero { grid-template-columns:1fr; text-align:center; padding:18px; }
  .heroMascot { margin:0 auto; max-width:170px; }
  .heroAccent { margin:0 auto .9rem; }
  .heroTitle { font-size:1.75rem; }
}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# Bilgi bankası
# Öncelik: 2025 İl Koordinatörleri Çalıştayı + NSO Desktop dokümanları.
# Kullanıcı doğrulaması: 2026 teması Geleceğe Hazır Okullar; ortaklıkta toplam en fazla 6 okul ve okul başına en fazla 4 öğretmen; Türkiye için ayrı 10 kişi kotası yoktur.
# Güçlü eşleşmede cevap doğrudan verilir; eşleşme zayıfsa yalnız ilgili yerel parçalar
# Gemini'ye bağlam olarak gönderilir. Bankada konu yoksa Gemini/API fallback çalışır.
# -----------------------------------------------------------------------------
# 2026 için kullanıcı tarafından doğrulanmış güncel tema.
# Bu kayıt yerel "source of truth" kabul edilir; proje fikri üretirken Gemini bu temayı bağlam olarak kullanır.
GUNCEL_ETWINNING_TEMASI = "Geleceğe Hazır Okullar"
GUNCEL_ETWINNING_TEMASI_EN = "Future-Ready Schools"
GUNCEL_ETWINNING_TEMA_YILI = 2026

BILGI_BANKASI: list[dict[str, Any]] = [{'anahtarlar': ['2026 etwinning teması', '2026 etwinning temasi', 'bu yılın etwinning teması', 'bu yilin etwinning temasi', 'etwinning yıllık tema', 'etwinning yillik tema', 'future ready schools', 'geleceğe hazır okullar', 'gelecege hazir okullar'],
  'cevap': '2026 eTwinning yıllık teması “Geleceğe Hazır Okullar” (Future-Ready Schools) temasıdır. Proje fikirleri bu tema altında geleceğe dönük beceriler, okulun dönüşüm kapasitesi, kapsayıcılık, dijital/yeşil yetkinlikler ve öğrencilerin geleceğe hazırlanması eksenlerinde kurgulanabilir.',
  'kaynak': 'Güncel tema · kullanıcı doğrulaması · 2026',
  'otoriter': True,
  'tur': 'guncel_tema'},
{'anahtarlar': ['etwinning nedir', 'e twinning nedir', 'etwinning ne işe yarar', 'etwinning vizyonu'],
  'cevap': 'eTwinning, Avrupa’daki okullar arasında iş birliğini teşvik eden büyük bir eğitim topluluğudur. '
           'Dijital yetkinlik, kültürler arası diyalog, çok dillilik ve yenilikçi pedagojiyi destekler.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['etwinning tarihçesi',
                 'etwinning ne zaman kuruldu',
                 'türkiye etwinning ne zaman katıldı',
                 'esep entegrasyonu'],
  'cevap': 'eTwinning 2005’te Avrupa Komisyonu tarafından başlatıldı; Türkiye 2009’da katıldı. Topluluk '
           '2019’da 1 milyon kayıtlı öğretmene ulaştı, 2023’te European School Education Platform (ESEP) ile '
           'entegre edildi.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['etwinning kaç ülke', '46 ülke', 'etwinning ülkeler'],
  'cevap': 'Çalıştay bilgisinde eTwinning topluluğu 46 ülkeyi kapsayan; çok dillilik, kültürler arası '
           'diyalog, dijital yetkinlik ve eğitimde yenilikçiliği destekleyen bir yapı olarak sunulmaktadır.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['öğretmenler için etwinning faydaları',
                 'öğretmen kazanımları',
                 'etwinning öğretmene ne kazandırır'],
  'cevap': 'Öğretmenler için başlıca kazanımlar mesleki gelişim, Avrupa çapında ağ kurma, yenilikçi '
           'pedagojiyi sınıfa taşıma ve tanınma/ödüllendirmedir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['öğrenciler için etwinning faydaları',
                 'öğrenci kazanımları',
                 'etwinning öğrenciye ne kazandırır'],
  'cevap': 'Öğrenciler açısından eTwinning; dijital okuryazarlık, eleştirel düşünme, problem çözme, iş '
           'birliği, kültürler arası farkındalık, yabancı dil pratiği, motivasyon ve özgüveni destekler.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['okul için etwinning faydaları', 'okul stratejik değer', 'etwinning okul faydası'],
  'cevap': 'Okul düzeyinde eTwinning; uluslararası görünürlük, yenilikçi okul kültürü, paydaş ilişkilerinin '
           'güçlenmesi ve kalite güvencesi açısından stratejik değer üretir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['etwinning paydaşları',
                 'merkezi destek servisi',
                 'ulusal destek servisi',
                 'etwinning elçileri',
                 'eğitim fakülteleri'],
  'cevap': 'Temel paydaşlar; Merkezi Destek Servisi, Ulusal Destek Servisleri, eTwinning elçileri, '
           'öğretmenler ve eğitim fakülteleridir. Rolleri platform/faaliyet yönetimi, ulusal '
           'rehberlik-yaygınlaştırma, bölgesel destek ve uygulamayı kapsar.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['eu login nasıl oluşturulur', 'eu login hesabı', 'eu login şifre', 'onay epostası spam'],
  'cevap': 'EU Login için ad-soyad ve aktif e-posta girilir; onay e-postası Spam klasörü dahil kontrol '
           'edilir. Güçlü şifre en az 10 karakter, büyük-küçük harf, rakam ve özel karakter içermelidir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['esep kayıt nasıl yapılır', 'join etwinning', 'etwinning aktive et', 'esep kayıt'],
  'cevap': 'EU Login ile ESEP’e giriş yaptıktan sonra profil bilgileri tamamlanır ve profil oluşturma '
           'sırasında ‘Join eTwinning’ seçeneği üzerinden eTwinning üyeliği etkinleştirilir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['doğru üye tipi',
                 'teacher rolü',
                 'hangi hesap türü',
                 'etwinning hesap türleri',
                 'student teacher',
                 'teacher educator'],
  'cevap': 'Okuldaki öğretmenler proje özelliklerine tam erişim için rolünü doğru seçmelidir; normal '
           'öğretmen için ‘Teacher’ kullanılır. Sistem ayrıca Head Teacher/Principal, ICT Coordinator, '
           'Pedagogical Adviser, School Psychologist, Librarian, Student Teacher ve Teacher Educator gibi '
           'hesap türlerini destekler.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2 + Oturum 3'},
 {'anahtarlar': ['okul ekleme', 'register a new school', 'esep okul ekle', 'okul kaydı onay'],
  'cevap': 'Önce okulun resmî adı ve şehirle mevcut kaydı aranır. Yoksa ‘Register a new school’ ile resmî '
           'ad, adres, posta kodu ve müdürün kurumsal e-postası girilir; yeni okul kaydı UDS onayına gider.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['profil nasıl olmalı', 'etwinning profil', 'hakkında bölümü', 'profil görünürlük'],
  'cevap': 'Profil dijital kartvizit gibi hazırlanmalıdır: profesyonel fotoğraf, kısa ve somut ‘Hakkında’ '
           'metni, ilgi alanları ve projeye sunulabilecek beceriler belirtilmeli; eTwinning üyelerine '
           'görünürlük ayarı açık olmalıdır.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['connect bölümü', 'ortak bulma', 'kişi arama', 'okul arama', 'ortak ilanları'],
  'cevap': 'ESEP Connect bölümünde kişi ve okul araması yapılabilir; ülke, branş ve yaş aralığı gibi '
           'filtreler kullanılabilir. Ortak İlanları bölümü proje ortağı bulmak veya kendi proje ilanını '
           'yayımlamak için en aktif alanlardan biridir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['iyi ortak ilanı',
                 'ortak ilanı nasıl yazılır',
                 'project partner posting',
                 'proje ortakları aranıyor'],
  'cevap': 'İyi ortak ilanı genel ifadeler yerine konu, hedef, öğrenci yaşı/rolü, 2-3 somut etkinlik ve '
           'beklenen ortak katkısını açıklar. Başlık da projenin temasını yansıtacak kadar özgün ve belirgin '
           'olmalıdır.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['ilk ortak mesajı', 'ortağa mesaj', 'etwinning iletişim', 'partner mesajı'],
  'cevap': 'İlk mesaj kısa ve profesyonel olmalı; öğretmenin branşı/öğrenci yaş grubu, neden o ortakla '
           'çalışmak istediği ve projeden 2-3 somut etkinlik örneği belirtilmelidir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['proje planlama', 'görev dağılımı', 'zaman çizelgesi', 'ortak ürün', 'iletişim kanalları'],
  'cevap': 'Proje planında görev dağılımı, başlangıç-bitiş ve aylık hedefleri içeren zaman çizelgesi, '
           'iletişim kanalları ve somut ortak ürünler baştan netleştirilmelidir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['ulusal kalite etiketi nedir',
                 'avrupa kalite etiketi nedir',
                 'kalite etiketi türleri',
                 'uke ake'],
  'cevap': 'Ulusal Kalite Etiketi, projenin ulusal kalite standardını karşıladığını gösterir ve UDS '
           'tarafından değerlendirilir. Avrupa Kalite Etiketi için farklı ülkelerden en az iki ortağın '
           'Ulusal Kalite Etiketi almış olması gerekir; süreç UDS teklifi ve Merkezi Destek Servisi onayıyla '
           'ilerler.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['kalite etiketi neden önemli', 'kalite etiketi faydaları', 'uke fayda'],
  'cevap': 'Kalite Etiketi öğretmen ve okula tanınırlık/prestij, öğrenci-öğretmen motivasyonu ve mesleki '
           'gelişim dosyasında somut başarı göstergesi sağlar; Avrupa eTwinning Ödülleri yolunda da '
           'önemlidir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['kalite etiketi ön koşulları',
                 'uke başvuru şartları',
                 'kalite etiketi başvuru şartları',
                 'aktif katkı twinspace görünür'],
  'cevap': 'Kalite Etiketi için proje uluslararası olmalı, ana etkinlikleri bitmiş veya son aşamada olmalı, '
           'başvuran öğretmenin aktif ve görünür katkısı bulunmalı ve TwinSpace özellikle çıktı/sonuçları '
           'gösterecek şekilde değerlendiriciye açık-düzenli olmalıdır.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['kalite etiketi kriterleri',
                 'quality label kriterleri',
                 'ql kriterleri',
                 'değerlendirme kriterleri'],
  'cevap': 'Kalite Etiketi değerlendirmesi 5 ana eksende yapılır: pedagojik yenilik, müfredat entegrasyonu, '
           'ortaklar arası iş birliği, pedagojik amaçlı teknoloji kullanımı ve sonuçlar/etki/belgeleme. En '
           'kritik kanıt, öğrencilerin ve ortakların gerçekten birlikte ürettiğini TwinSpace üzerinde '
           'gösterebilmektir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['etwinning okulu şartları', 'etwinning school ön koşulları', 'etwinning okulu unvanı'],
  'cevap': 'Çalıştay sunumundaki ön koşullar: okulun en az 2 yıldır ESEP/eTwinning’e kayıtlı olması, okulda '
           'en az 3 aktif eTwinner öğretmen bulunması ve son iki yıl içinde okuldan en az bir öğretmenin bir '
           'projesiyle Ulusal Kalite Etiketi almış olmasıdır.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 2'},
 {'anahtarlar': ['proje beklemede', 'waiting for nso approval', 'kurucu ortak onayı', 'proje onay bekliyor'],
  'cevap': 'Bekleyen projede önce kurucu ortağın onay verip vermediği kontrol edilir. Kurucu onayı varsa NSO '
           'ekranından onay tarihi, hangi ülkenin UDS onayının beklendiği ve düzenleme talebi olup olmadığı '
           'görülebilir; düzenleme talebinde kurucular e-postalarını kontrol etmelidir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['projeye katılamıyorum',
                 'projeye davet edilemiyor',
                 'proje daveti görünmüyor',
                 'available for projects'],
  'cevap': 'Projeye katılım/davet sorunu için profilde aktif okul, ‘Available for projects = Evet’, '
           'kurucunun irtibat listesinde bulunma, doğru okul rolü ve profilin aktif olması kontrol edilir. '
           'Student Teacher/Teacher Educator rolü proje davetini engelleyebilir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['sanity check',
                 'ortak bulma forumu uyarı',
                 'organisation needs a sanity check',
                 'posting oluşturamıyorum'],
  'cevap': 'Ortak bulma forumunda ‘organisation needs a Sanity Check’ uyarısı görülürse '
           'okul/organizasyondaki üyelerin eTwinning üyelik onay durumları NSO Desktop veya okul profili '
           'üzerinden kontrol edilmelidir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['hesaba erişemiyorum', 'esep hesabıma giremiyorum', 'esep giriş yapamıyorum', 'e posta erişim yok', 'esep şifre unuttum', 'hotmail mail gelmiyor'],
  'cevap': 'E-posta ve ESEP’e erişim yoksa aktif e-postayla yeni hesap açıp UDS’ye bilgi verilerek eski '
           'hesabın e-postası yeni adresle ilişkilendirilebilir; yeni hesap silinir. ESEP’e giriş '
           'yapılabiliyorsa e-posta profilden güncellenebilir; Hotmail adreslerinde platform e-postalarının '
           'ulaşmaması daha sık görülebilir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['profil ismi güncelle',
                 'e posta adresi değiştir',
                 'change eu login credentials',
                 'configure my account'],
  'cevap': 'Profil adı/e-posta değişikliği kullanıcı tarafından yapılır: ESEP → Profilim → Düzenle → ‘Change '
           'EU login credentials’ → EU Login ayarlarında ‘Configure my account’ yolu izlenir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['proje oluştururken dikkat',
                 'kurucular farklı ülkeler',
                 'veli izin',
                 'okul idaresi izin',
                 'kalite etiketi kaç proje başvuru'],
  'cevap': 'Kalite Etiketi hedefleniyorsa kurucular farklı ülkelerden olmalıdır; aynı ülkeden iki kurucuyla '
           'başlayan proje sonradan yabancı üye eklenince uluslararasıya dönüşmez. Okul idaresinden yazılı '
           'izin zorunlu değildir ancak bilgilendirme uygundur; veliler ayrıntılı bilgilendirilmeli ve '
           'öğrenci katılımı için yazılı izin alınmalıdır. Bir dönemde en fazla 4 proje için Kalite Etiketi '
           'başvurusu yapılabilir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['ortak sınırı',
                 'ortak sayısı',
                 'kaç okul olabilir',
                 'maksimum okul',
                 'en fazla kaç okul',
                 'aynı okuldan kaç öğretmen',
                 'ayni okuldan kac ogretmen',
                 'öğretmen sınırı',
                 'proje üye sınırı',
                 'türkiyeden en fazla kaç öğretmen',
                 'türkiye üye sınırı',
                 '10 türk sınırı',
                 '10 üye sınırı',
                 'türkiyeden 10 üye',
                 'turkiyeden 10 uye'],
  'cevap': 'Güncel uygulama kuralında Türkiye için ayrı bir “en fazla 10 üye” sınırı yoktur. Esas sınırlar: '
           'projede toplam en fazla 6 okul ve aynı okuldan en fazla 4 öğretmen. Kalite Etiketi hedeflenen '
           'uluslararası projede en az iki farklı ülke gerektiğinden, 6 okulun en fazla 5’i Türkiye’den olabilir; '
           'bu durumda Türkiye’den öğretmen sayısı teorik olarak 5 × 4 = 20’ye kadar çıkabilir. Toplam öğretmen '
           'sayısı için ayrıca 10 kişilik bir Türkiye kotası uygulanmaz. Öğrenci sayısı için sabit bir üst sınır yoktur.',
  'kaynak': 'Güncel koordinasyon kuralı · kullanıcı doğrulaması · 2026-10-04',
  'otoriter': True},
 {'anahtarlar': ['proje ne zaman başlatılır', 'proje süresi', 'aynı eğitim yılı', 'proje dili'],
  'cevap': 'Proje yılın herhangi bir zamanında başlatılabilir ve süre esnektir; mümkünse aynı eğitim yılı '
           'içinde tamamlanacak şekilde planlanması önerilir. Proje dili ortakların birlikte iletişim '
           'kurabileceği bir dil olmalıdır.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['twinspace üyesi ama proje üyesi değil',
                 'sadece twinspace daveti',
                 'twinspace davet sorunu'],
  'cevap': 'Kurucular proje üyeliği için proje sayfasındaki Üyeler bölümünden davet göndermelidir. Yalnız '
           'TwinSpace erişimi isteniyorsa TwinSpace/Üyeler alanındaki ‘Sadece TwinSpace’ daveti '
           'kullanılabilir; temel katılım şartlarını sağlamayan kişi buradan da proje üyesi yapılamaz.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['proje neden onaylanmaz', 'onaylanmayan proje', 'proje reddedilir', 'düzenleme talebi'],
  'cevap': 'Onay sorunu doğurabilecek örnekler: yetişkin odaklı/öğrenci etkinliği olmayan projeler, MEB '
           'kapsamında yürütülemeyecek çalışmalar, eTwinning Davranış Kurallarına aykırılık, yardım toplama, '
           'yetersiz/boş başvuru ve ortak iletişimine uygun olmayan tek taraflı proje dili. Bazı durumlarda '
           'doğrudan ret yerine düzenleme istenir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['projeye katılırken okul seçimi',
                 'yanlış okul seçtim',
                 'projede okul değiştir',
                 'okul bilgisi değişir mi'],
  'cevap': 'Projeye katılırken seçilen okul sonradan doğrudan değiştirilemez; profile yeni okul eklemek eski '
           'projedeki okul bilgisini değiştirmez. Hata başlangıçta fark edilirse üye projeden ayrılıp doğru '
           'okulla yeniden katılabilir; özellikle Kalite Etiketi başvurusu yapılmış projede bu işlem uygun '
           'değildir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['kurucu değişikliği', 'kurucu projeden ayrılırsa', 'kurucu devam edemiyor'],
  'cevap': 'Kuruculardan biri devam edemiyorsa proje başlangıç aşamasında kapatılıp yeni proje açılabilir. '
           'Proje ilerlemişse en az iki okul kaldığı sürece mevcut üyelerle tamamlanabilir; kuruculardan '
           'birinin pasifleşmesi tek başına projenin bitmesini gerektirmez.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['öğrenci hesabı',
                 'öğrenci twinspace giriş',
                 'pupil login',
                 'öğrenci yaş sınırı',
                 'öğrenci şifresi'],
  'cevap': 'Öğrenciler platformda kendi eTwinning hesabını oluşturmaz; öğretmen TwinSpace’e davet eder. 8 '
           'yaş ve üzeri öğrenciler davet edilebilir; otomatik oluşturulan şifre kartı indirilip bireysel '
           'paylaşılmalıdır. Küçük öğrencilerin adlarının açık yazılmaması önerilir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['mesleki gelişim etkinlikleri',
                 'course catalogue',
                 'webinarlar',
                 'european commission filtresi'],
  'cevap': 'ESEP Learn alanında kurslar, webinarlar ve diğer mesleki gelişim fırsatları bulunur. Merkezi '
           'Destek Servisi/Avrupa Komisyonu kurslarını görmek için Course Catalogue’da provider filtresinde '
           'European Commission seçilebilir; webinarların tamamı EC tarafından düzenlenmektedir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['öğrenci görseli paylaşma', 'yüz maskelenmeli mi', 'veli izni görsel', 'twinspace fotoğraf'],
  'cevap': 'Veli izinleri alınmışsa öğrenci görselleri TwinSpace üyelerine açık sayfalarda paylaşılabilir. '
           'Herkese açık sayfalarda daha ihtiyatlı olunması önerilir; öğrencilerin yüzünü maskelemenin '
           'zorunlu olduğuna dair genel bir kural bulunmadığı belirtilmiştir.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['okul kaydı nasıl yazılır',
                 'public name legal name',
                 'school türü',
                 'okul adı karakter',
                 'okul bilgisi güncelle'],
  'cevap': 'Okul eklerken Public Name ve Legal Name alanlarına resmî okul adı aynı şekilde yazılmalı, kurum '
           'türü ‘School’ seçilmelidir. İsim/iletişim değişikliğinde yeni okul açmak yerine mevcut kayıt '
           'güncellenmeli; okul adına harf ve rakam dışı karakter eklemekten kaçınılmalıdır.',
  'kaynak': '2025 İl Koordinatörleri Çalıştayı · Oturum 3'},
 {'anahtarlar': ['nso desktop üyelik onayı',
                 'onay bekleyen öğretmenler',
                 'registrations nso',
                 'kayıtlı öğretmen okul listesi'],
  'cevap': 'NSO Desktop’ta üyelik onayı bekleyen öğretmenlerin ve kayıtlı öğretmen/okulların listeleri '
           'Registrations alanından görüntülenebilir. Kişi aramasında ‘Requested validation’ filtresi onay '
           'bekleyen kullanıcıları daraltır.',
  'kaynak': 'NSO Desktop · İl Koordinatörleri'},
 {'anahtarlar': ['nso kişi profili kontrol',
                 'pending validated okul',
                 'available for projects profil',
                 'profil id eposta'],
  'cevap': 'NSO kişi profilinde ID, Hakkında bölümünde e-posta/projelere uygunluk ve Schools sekmesinde okul '
           'üyelik durumu kontrol edilebilir. Yeni okul üyeliği onaydaysa Pending, onaylandıysa Validated '
           'sekmesinde görünür.',
  'kaynak': 'NSO Desktop · İl Koordinatörleri'},
 {'anahtarlar': ['non etwinning okul', 'etwinning e başvur', 'okul üyeliği tamamlanmamış'],
  'cevap': 'Kişi okul eklerken ‘Bu okulda eTwinning’e katılmak istiyor musunuz?’ sorusunu evet '
           'işaretlemediyse okul Non eTwinning görünür ve üyelik onaylanamaz. Öğretmen profilindeki okul '
           'menüsünden ‘eTwinning’e başvur’ işlemini tamamlamalıdır.',
  'kaynak': 'NSO Desktop · İl Koordinatörleri'},
 {'anahtarlar': ['nso etkinlik kaydet',
                 'professional development event',
                 'add event',
                 'koordinatör etkinlik'],
  'cevap': 'İl koordinatörü etkinlik/eğitim kaydını NSO Desktop → Professional Development → Event → Add '
           'event yoluyla oluşturabilir. Etkinlik kapsamı Regional/Bölgesel seçilmelidir.',
  'kaynak': 'NSO Desktop · İl Koordinatörleri'},
 {'anahtarlar': ['etkinlik visibility hidden', 'nso etkinlikte visibility',
                 'provide certificate',
                 'provider type ambassador',
                 'etkinlik dil seçimi',
                 'registration event'],
  'cevap': 'NSO etkinlik kaydında tür ve yüz yüze/çevrim içi bilgisi zorunludur; Visibility ‘Hidden’ '
           'seçilir. Sertifika verilecekse ‘Provide certificate’ ve sertifika detayı doldurulur; yüz yüze '
           'etkinlikte il/ilçe/yer/ülke bilgileri, Provider type = Ambassador ve dil seçimi gerekir. Katılım '
           'türünde Registrations seçilebilir.',
  'kaynak': 'NSO Desktop · İl Koordinatörleri'},
 {'anahtarlar': ['etkinliğe katılımcı ekle',
                 'manage participants',
                 'add import participants',
                 'attended',
                 'sertifika gönder'],
  'cevap': 'Etkinlik yayımlandıktan sonra Manage participants → Add/Import participants ile tek tek veya '
           'tabloyla katılımcı eklenir; geçerli kayıtlar ‘Add participants to event’ ile kaydedilir. '
           'Katılanlar ‘Attended’ olarak işaretlenir; Manage certificate üzerinden metin hazırlanıp '
           'katılımcılar seçilerek ‘Send certificate’ ile gönderilir.',
  'kaynak': 'NSO Desktop · İl Koordinatörleri'},
 {'anahtarlar': ['iyi etwinning projesi', 'başarılı etwinning projesi', 'proje nasıl olmalı'],
  'cevap': 'İyi bir eTwinning projesi gerçek bir öğrenci ihtiyacından başlar, müfredatla ilişkilidir ve '
           'ortakların paralel değil birlikte üretmesini sağlar. Az sayıda ölçülebilir hedef, karma öğrenci '
           'çalışmaları, güvenli dijital araçlar, ortak final ürün ve süreç-sonuç değerlendirmesi '
           'yeterlidir.',
  'kaynak': 'Yerel danışmanlık rehberi'},
 {'anahtarlar': ['twinspace nasıl kullanılmalı', 'twinspace düzeni', 'twinspace sayfaları'],
  'cevap': 'TwinSpace’ı proje hikâyesi gibi düzenleyin: amaç-planlama, ortak tanıtımı, eSafety, '
           'aylık/haftalık ortak çalışmalar, karma takım ürünleri, değerlendirme ve yaygınlaştırma. Her '
           'sayfada kimin ne yaptığı ve ortaklığın nasıl gerçekleştiği görünür olmalı.',
  'kaynak': 'Yerel danışmanlık rehberi'},
 {'anahtarlar': ['esafety', 'e safety', 'internet güvenliği', 'dijital güvenlik'],
  'cevap': 'eSafety için veli izinleri, kişisel veri/görsel kullanım kuralları, telif ve kaynak gösterme, '
           'güçlü parola, güvenli paylaşım ve dijital vatandaşlık farkındalığı birlikte ele alınmalıdır; '
           'bunlar proje sürecinde uygulanan kurallar olarak görünür olmalıdır.',
  'kaynak': 'Yerel danışmanlık rehberi'},
 {'anahtarlar': ['yaygınlaştırma', 'dissemination', 'proje yaygınlaştırma'],
  'cevap': 'Yaygınlaştırmayı yalnız sosyal medya paylaşımı olarak görmeyin. Okul panosu/web sitesi, '
           'veli-öğretmen toplantıları, yerel paydaşlar, sonuç ürünlerinin paylaşımı ve proje sonrasında '
           'kullanılabilir materyaller daha güçlü kanıttır.',
  'kaynak': 'Yerel danışmanlık rehberi'}]


def _ek_bilgi_bankasi_yukle() -> list[dict[str, Any]]:
    ham = secret_al("EK_BILGI_BANKASI_JSON")
    if not ham:
        return []
    try:
        veri = json.loads(ham)
        if isinstance(veri, list):
            sonuc = []
            for x in veri:
                if isinstance(x, dict) and isinstance(x.get("cevap"), str):
                    anahtarlar = x.get("anahtarlar") or []
                    if isinstance(anahtarlar, str):
                        anahtarlar = [anahtarlar]
                    sonuc.append({
                        "anahtarlar": list(anahtarlar),
                        "cevap": x["cevap"],
                        "kaynak": str(x.get("kaynak", "Özel bilgi bankası")),
                        "otoriter": bool(x.get("otoriter", False)),
                    })
            return sonuc
    except Exception:
        pass
    return []


BILGI_BANKASI.extend(_ek_bilgi_bankasi_yukle())


def normalize(metin: str) -> str:
    metin = str(metin or "").casefold()
    tablo = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c"})
    metin = metin.translate(tablo)
    metin = re.sub(r"[^a-z0-9+\s]", " ", metin)
    return re.sub(r"\s+", " ", metin).strip()


def detay_istiyor_mu(soru: str) -> bool:
    s = normalize(soru)
    tetikler = [
        "detay", "ayrintili", "ayrintili anlat", "analiz", "rapor", "kapsamli", "adim adim",
        "orneklerle", "karsilastir", "strateji", "taslak hazirla", "proje yaz", "plan olustur",
    ]
    return any(t in s for t in tetikler)


def guncel_web_aramasi_gerekli_mi(soru: str, yerel_otoriter_var: bool = False) -> bool:
    """Güncel bilgi gerçekten yerelde yoksa Google Search grounding açılır.

    Otoriter/güncel bir yerel kayıt eşleşmişse aynı bilgiyi web'de tekrar aramayarak
    hem token hem gecikme tasarrufu sağlarız.
    """
    if not GUNCEL_WEB_ARAMA_AKTIF:
        return False
    if yerel_otoriter_var:
        return False
    s = normalize(soru)
    tetikler = [
        "guncel", "bugun", "bu yil", "2026", "2027", "son cagri", "son tarih", "deadline",
        "tema", "duyuru", "mevzuat", "rehber", "ulusal ajans", "ara", "arastir", "internet",
        "son durum", "degisti mi", "yeni kriter",
    ]
    return any(t in s for t in tetikler)


def yaratici_uretim_mi(soru: str) -> bool:
    """Bilgi bankasındaki olguyu aynen döndürmek yerine Gemini sentezi gereken istekler."""
    s = normalize(soru)
    tetikler = [
        "oner", "proje oner", "fikir", "tasarla", "olustur", "hazirla", "yaz",
        "etkinlik oner", "aktivite oner", "isim oner", "baslik oner", "planla",
        "okul oncesi", "ilkokul icin", "ortaokul icin", "lise icin",
    ]
    return any(t in s for t in tetikler)


def _bilgi_bankasi_skoru(q: str, anahtar: str) -> float:
    a = normalize(anahtar)
    if not a:
        return 0.0
    if a == q:
        return 1.0
    if a in q:
        return 0.96
    if q in a and len(q.split()) >= 2:
        return 0.90
    genel = {"etwinning", "proje", "project", "esep", "nso", "twinspace", "kalite", "etiketi"}
    q_tokens = {x for x in q.split() if len(x) >= 3 and x not in genel}
    a_tokens = {x for x in a.split() if len(x) >= 3 and x not in genel}
    if not q_tokens or not a_tokens:
        return 0.0
    ortak = len(q_tokens & a_tokens)
    jaccard = ortak / max(1, len(a_tokens | q_tokens))
    key_coverage = ortak / max(1, len(a_tokens))
    query_coverage = ortak / max(1, len(q_tokens))
    return max(jaccard, key_coverage * 0.84, query_coverage * 0.72)


def bilgi_bankasi_eslesmeleri(soru: str, limit: int = 4) -> list[tuple[float, dict[str, Any]]]:
    q = normalize(soru)
    if not q:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for kayit in BILGI_BANKASI:
        en_iyi = 0.0
        for anahtar in kayit.get("anahtarlar", []) or []:
            en_iyi = max(en_iyi, _bilgi_bankasi_skoru(q, str(anahtar)))
        if en_iyi > 0:
            # Otoriter/güncel kurallar eşit skorda öne çıkar.
            if kayit.get("otoriter"):
                en_iyi += 0.06
            scored.append((min(1.0, en_iyi), kayit))
    scored.sort(key=lambda x: (x[0], bool(x[1].get("otoriter"))), reverse=True)
    return scored[:limit]


def bilgi_bankasi_ara(soru: str) -> tuple[str | None, float, dict[str, Any] | None]:
    eslesmeler = bilgi_bankasi_eslesmeleri(soru, limit=1)
    if not eslesmeler:
        return None, 0.0, None
    skor, kayit = eslesmeler[0]
    esik = 0.50 if kayit.get("otoriter") else 0.62
    if skor >= esik:
        return str(kayit.get("cevap", "")), skor, kayit
    return None, skor, kayit


def bilgi_bankasi_baglam_ara(soru: str, limit: int = 4) -> tuple[str, float]:
    eslesmeler = bilgi_bankasi_eslesmeleri(soru, limit=limit)
    secilen = [(skor, k) for skor, k in eslesmeler if skor >= 0.24]
    if not secilen:
        return "", 0.0
    parcalar = []
    for skor, kayit in secilen:
        kaynak = str(kayit.get("kaynak", "Bilgi bankası"))
        parcalar.append(f"[Yerel kaynak: {kaynak}]\n{str(kayit.get('cevap','')).strip()}")
    return "\n\n".join(parcalar), max(x[0] for x in secilen)


# -----------------------------------------------------------------------------
# Gemini yardımcıları
# -----------------------------------------------------------------------------
def sohbet_gecmisi_hazirla(gecmis: list[dict], soru: str, detayli: bool) -> list[dict]:
    limit = 6 if detayli else 2
    onceki = list(gecmis[-limit:])
    if onceki and onceki[-1].get("role") == "user" and normalize(onceki[-1].get("content", "")) == normalize(soru):
        onceki = onceki[:-1]

    contents = []
    for msg in onceki:
        rol = msg.get("role", "user")
        if rol not in {"user", "assistant"}:
            continue
        metin = str(msg.get("content", ""))[:1200]
        if not metin.strip():
            continue
        gemini_rolu = "user" if rol == "user" else "model"
        if not contents and gemini_rolu == "model":
            continue
        contents.append({"role": gemini_rolu, "parts": [{"text": metin}]})
    return contents


def grounding_kaynaklarini_al(veri: dict) -> list[dict[str, str]]:
    kaynaklar: list[dict[str, str]] = []
    try:
        candidate = (veri.get("candidates") or [])[0]
        metadata = candidate.get("groundingMetadata", {}) or {}
        for chunk in metadata.get("groundingChunks", []) or []:
            web = (chunk or {}).get("web") or {}
            uri = str(web.get("uri", "") or "").strip()
            title = str(web.get("title", "") or uri).strip()
            if uri and not any(k["uri"] == uri for k in kaynaklar):
                kaynaklar.append({"title": title, "uri": uri})
            if len(kaynaklar) >= 5:
                break
    except Exception:
        pass
    return kaynaklar


def gemini_yanit_metin(veri: dict) -> str:
    parcalar: list[str] = []
    for aday in veri.get("candidates", []) or []:
        content = aday.get("content", {}) or {}
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and part.get("text"):
                parcalar.append(str(part["text"]))
        if parcalar:
            break
    return "".join(parcalar).strip()


def istek_yap(payload: dict, deneme: int = 3, timeout_s: int = 90) -> dict:
    if not API_KEY:
        raise RuntimeError("Gemini API anahtarı bulunamadı. Streamlit Secrets içine GEMINI_API_KEY ekleyin.")
    son_hata = ""
    for i in range(deneme):
        try:
            r = requests.post(
                GEMINI_URL,
                params={"key": API_KEY},
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=(10, timeout_s),
            )
            if r.status_code == 200:
                return r.json()
            son_hata = f"HTTP {r.status_code}: {r.text[:500]}"
            if r.status_code in {429, 500, 502, 503, 504} and i < deneme - 1:
                time.sleep(1.2 * (2 ** i))
                continue
            break
        except requests.RequestException as exc:
            son_hata = str(exc)
            if i < deneme - 1:
                time.sleep(1.2 * (2 ** i))
                continue
    raise RuntimeError(f"Gemini isteği başarısız: {son_hata or 'bilinmeyen hata'}")


def gemini_cevap_uret(soru: str, gecmis: list[dict]) -> tuple[str, dict]:
    detayli = detay_istiyor_mu(soru)
    yaratici = yaratici_uretim_mi(soru)

    # Önce yerel bilgi bankasını tara. Güncel/otoriter kayıt varsa bunu source-of-truth kabul et.
    eslesmeler = bilgi_bankasi_eslesmeleri(soru, limit=3)
    en_iyi_skor = eslesmeler[0][0] if eslesmeler else 0.0
    en_iyi_kayit = eslesmeler[0][1] if eslesmeler else None
    otoriter = bool((en_iyi_kayit or {}).get("otoriter")) and en_iyi_skor >= 0.50

    # Salt bilgi sorusunda güçlü ve güncel yerel kayıt varsa API çağırmadan cevap ver.
    # Proje önerisi/yazım gibi üretken işlerde ise bu bilgiyi Gemini'ye kısa bağlam olarak ver.
    if en_iyi_kayit and not yaratici and not detayli:
        esik = 0.50 if otoriter else 0.78
        if en_iyi_skor >= esik:
            return str(en_iyi_kayit.get("cevap", "")), {
                "source": "bilgi_bankasi",
                "knowledge_source": str(en_iyi_kayit.get("kaynak", "Bilgi bankası")),
                "prompt_tokens": 0, "output_tokens": 0, "total_tokens": 0, "grounding_sources": [],
            }

    # Sadece ilgili 1-3 yerel parçayı kullan; tüm bilgi bankasını prompta basma.
    baglam_eslesmeleri = [(skor, k) for skor, k in eslesmeler if skor >= 0.22]
    baglam_parcalari = []
    for skor, kayit in baglam_eslesmeleri[:3]:
        kaynak = str(kayit.get("kaynak", "Bilgi bankası"))
        baglam_parcalari.append(f"[Yerel kaynak: {kaynak}]\n{str(kayit.get('cevap','')).strip()}")
    banka_baglam = "\n\n".join(baglam_parcalari)

    # Yerelde otoriter bilgi varsa web'e çıkma. Yoksa güncel sorularda Search grounding kullan.
    web_arama = guncel_web_aramasi_gerekli_mi(soru, yerel_otoriter_var=otoriter)
    bugun = datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat()

    if detayli:
        cevap_kurali = "Yapılandırılmış ve uygulanabilir cevap ver; gereksiz tekrar yapma. Yaklaşık 350 kelimeyi aşma."
        max_tokens = 700
    elif yaratici:
        cevap_kurali = (
            "Kısa ama yaratıcı ve uygulanabilir cevap ver. Proje önerisinde başlık + 1 cümle amaç + "
            "3 somut etkinlik + 1 ortak ürün yeterlidir. Yaklaşık 140-180 kelimeyi aşma."
        )
        max_tokens = 320
    else:
        cevap_kurali = "Doğrudan 2-4 cümleyle cevap ver; yaklaşık 80-100 kelimeyi aşma."
        max_tokens = 200

    sistem = f"""
Sen 'Twin', deneyimli bir eTwinning proje danışmanısın. Tarih: {bugun}.
{cevap_kurali}
YEREL BİLGİ BANKASI, verilen konularda birincil kaynaktır. Otoriter/güncel yerel bilgiyle çelişme.
2026 eTwinning yıllık teması: “{GUNCEL_ETWINNING_TEMASI}” ({GUNCEL_ETWINNING_TEMASI_EN}).
Güncel ortaklık kuralı: toplam en fazla 6 okul; aynı okuldan en fazla 4 öğretmen; Türkiye için ayrı 10 kişi kotası yoktur.
Yerel bankada yeterli bilgi yoksa kendi model bilginle destekle; soru güncelse Google Search grounding kullan.
Kullanıcı proje/etkinlik fikri isterse yerel gerçekleri aynen koru, geri kalan yaratıcı tasarımı sen üret.
Türkçe yanıt ver; kullanıcı başka dil isterse ona geç.
""".strip()

    banka_baglam_metni = f"\n\nYEREL BİLGİ BANKASI BAĞLAMI:\n{banka_baglam[:2200]}" if banka_baglam else ""
    contents = sohbet_gecmisi_hazirla(gecmis, soru, detayli)
    contents.append({"role": "user", "parts": [{"text": sistem + banka_baglam_metni + f"\n\nKULLANICI SORUSU:\n{soru}"}]})

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.35 if yaratici else 0.15,
            "topP": 0.82,
            "maxOutputTokens": max_tokens,
        },
    }
    if web_arama:
        payload["tools"] = [{"google_search": {}}]

    veri = istek_yap(payload)
    cevap = gemini_yanit_metin(veri)
    if not cevap:
        raise RuntimeError("Gemini boş yanıt döndürdü.")

    usage = veri.get("usageMetadata", {}) or {}
    kaynaklar = grounding_kaynaklarini_al(veri)
    return cevap, {
        "source": "web" if web_arama else ("hybrid" if banka_baglam else "gemini"),
        "knowledge_source": str((en_iyi_kayit or {}).get("kaynak", "")),
        "prompt_tokens": int(usage.get("promptTokenCount", 0) or 0),
        "output_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
        "total_tokens": int(usage.get("totalTokenCount", 0) or 0),
        "grounding_sources": kaynaklar,
    }


# -----------------------------------------------------------------------------
# Proje Doktoru
# -----------------------------------------------------------------------------
def guvenli_dosya_adi(dosya_adi: str) -> str:
    ad = os.path.basename(str(dosya_adi or "proje"))
    ad = re.sub(r"[^A-Za-z0-9._-]+", "_", ad).strip("._")
    return ad[:100] or "proje"


def docx_metni_cikar(dosya_baytlari: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(dosya_baytlari)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab[^>]*/>", "\t", xml)
        metin = re.sub(r"<[^>]+>", "", xml)
        return re.sub(r"\n{3,}", "\n\n", metin).strip()
    except Exception:
        return ""


def proje_doktoru_girdi_hazirla(uploaded_file, ek_metin: str = "") -> tuple[list[dict], list[str], str]:
    parts: list[dict] = []
    uyarilar: list[str] = []
    belge_adi = "Yapıştırılan metin"

    if uploaded_file is not None:
        belge_adi = guvenli_dosya_adi(uploaded_file.name)
        baytlar = uploaded_file.getvalue()
        if len(baytlar) > DOSYA_BOYUT_LIMITI:
            raise ValueError("Dosya çok büyük. En fazla 12 MB yükleyin.")
        uzanti = Path(uploaded_file.name).suffix.lower()
        if uzanti == ".pdf":
            parts.append({
                "inlineData": {
                    "mimeType": "application/pdf",
                    "data": base64.b64encode(baytlar).decode("ascii"),
                }
            })
        elif uzanti == ".docx":
            metin = docx_metni_cikar(baytlar)
            if not metin:
                raise ValueError("DOCX metni çıkarılamadı.")
            parts.append({"text": metin[:PROJE_DOKTORU_MAX_METIN_KARAKTER]})
        elif uzanti in {".txt", ".md"}:
            metin = baytlar.decode("utf-8", errors="replace")
            parts.append({"text": metin[:PROJE_DOKTORU_MAX_METIN_KARAKTER]})
        else:
            raise ValueError("Desteklenen dosyalar: PDF, DOCX, TXT, MD.")

    if ek_metin.strip():
        parts.append({"text": ek_metin.strip()[:PROJE_DOKTORU_MAX_METIN_KARAKTER]})

    if not parts:
        raise ValueError("Analiz için dosya yükleyin veya metin girin.")
    return parts, uyarilar, belge_adi


def proje_doktoru_analiz_et(uploaded_file=None, ek_metin: str = "") -> tuple[str, dict]:
    parts, _, belge_adi = proje_doktoru_girdi_hazirla(uploaded_file, ek_metin)
    talimat = """
Bu eTwinning proje belgesini proje doktoru gibi denetle. Çıktıyı kısa ama eyleme dönük tut.
Sadece belgede kanıtı olan noktaları güçlü yön say; kanıt olmayan şeyi uydurma.
Şu başlıkları kullan:
1. Genel teşhis (en fazla 5 madde)
2. Kritik eksikler / riskler (öncelik sırasıyla)
3. Kalite etiketi açısından kanıt durumu: pedagojik yenilik, müfredat entegrasyonu, ortak iş birliği, teknoloji, sonuç-etki
4. Hemen yapılacak 5 düzeltme
5. Sonuç: Hazır / Geliştirilmeli / Kritik eksik
Gereksiz teori anlatma.
""".strip()
    # Dosya analizi ile Google Search aracını aynı istekte çalıştırmıyoruz.
    # Bu kombinasyon bazı model/Streamlit Cloud senaryolarında isteği uzun süre açık
    # bırakabiliyor. Güncel, kullanıcı-doğrulamalı kuralları kısa yerel bağlam olarak veriyoruz.
    guncel_baglam = f"""
GÜNCEL YEREL KURALLAR:
- 2026 eTwinning teması: {GUNCEL_ETWINNING_TEMASI} ({GUNCEL_ETWINNING_TEMASI_EN}).
- Ortaklık sınırı: toplam en fazla 6 okul; aynı okuldan en fazla 4 öğretmen; Türkiye için ayrı 10 kişi kotası yoktur.
- Kalite Etiketi değerlendirme eksenleri: pedagojik yenilik, müfredat entegrasyonu, ortaklar arası iş birliği, pedagojik teknoloji kullanımı, sonuç-etki-belgeleme.
Belge bu kurallarla çelişiyorsa bunu risk olarak belirt.
""".strip()

    payload: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": talimat + "\n\n" + guncel_baglam}] + parts}],
        "generationConfig": {"temperature": 0.15, "maxOutputTokens": 1000},
    }

    # Proje Doktoru tek kontrollü istek yapar. Böylece başarısız bir API çağrısında
    # arayüz dakikalarca boş/spinner durumunda kalmaz. Normal sohbetin retry ayarı değişmez.
    try:
        veri = istek_yap(payload, deneme=1, timeout_s=65)
    except RuntimeError as exc:
        raise RuntimeError(
            "Proje Doktoru Gemini'den zamanında yanıt alamadı. Dosyayı yeniden deneyin; "
            "sorun sürerse dosyayı PDF yerine DOCX/TXT olarak yükleyin. Teknik ayrıntı: " + str(exc)
        ) from exc

    rapor = gemini_yanit_metin(veri)
    if not rapor:
        raise RuntimeError("Proje Doktoru boş yanıt döndürdü. Dosyayı yeniden yükleyip tekrar deneyin.")
    usage = veri.get("usageMetadata", {}) or {}
    return rapor, {
        "belge": belge_adi,
        "prompt_tokens": int(usage.get("promptTokenCount", 0) or 0),
        "output_tokens": int(usage.get("candidatesTokenCount", 0) or 0),
        "total_tokens": int(usage.get("totalTokenCount", 0) or 0),
        "grounding_sources": grounding_kaynaklarini_al(veri),
    }


# -----------------------------------------------------------------------------
# Yardımcı araç promptları
# -----------------------------------------------------------------------------
def arac_kutusu_promptu(arac: str, **alanlar) -> str:
    if arac == "Proje Tasarım Sihirbazı":
        return (
            "Kısa ve uygulanabilir bir eTwinning proje tasarımı oluştur. "
            f"Tema: {alanlar.get('tema','')}. Yaş grubu: {alanlar.get('yas','')}. Süre: {alanlar.get('sure','')}. "
            f"Özel istek: {alanlar.get('not','')}. "
            "Sadece şu başlıkları ver: amaç, 3 ölçülebilir hedef, 5 ortak etkinlik, 1 ortak final ürün, değerlendirme, yaygınlaştırma."
        )
    if arac == "Kalite Etiketi Hızlı Kontrol":
        return (
            "Aşağıdaki proje özetini kalite etiketi açısından değerlendir. Uzun teori yazma. "
            "Beş kriteri (pedagoji, müfredat, iş birliği, teknoloji, sonuç-etki) Güçlü / Geliştirilmeli / Eksik olarak değerlendir "
            "ve yalnız en kritik 5 iyileştirmeyi ver.\n\n" + alanlar.get("metin", "")
        )
    if arac == "TwinSpace Kontrol Listesi":
        return (
            "Bu proje için kısa bir TwinSpace kontrol listesi oluştur. Planlama, eSafety, öğrenci ortak çalışması, karma takım, "
            "ortak ürün, değerlendirme ve yaygınlaştırma başlıklarında en fazla 12 madde olsun.\n\n" + alanlar.get("metin", "")
        )
    return alanlar.get("metin", "")


def sohbeti_markdowna_cevir(messages: list[dict]) -> str:
    satirlar = ["# Twin - eTwinning Danışmanlık Oturumu", ""]
    for msg in messages:
        rol = "Kullanıcı" if msg.get("role") == "user" else "Twin"
        satirlar += [f"## {rol}", str(msg.get("content", "")), ""]
    return "\n".join(satirlar)


# -----------------------------------------------------------------------------
# Oturum
# -----------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "Merhaba. eTwinning proje tasarımı, kalite etiketi, TwinSpace ve proje geliştirme konusunda yardımcı olabilirim.",
            "meta": {"source": "system", "total_tokens": 0, "grounding_sources": []},
        }
    ]
if "cevap_cache" not in st.session_state:
    st.session_state.cevap_cache = {}
if "son_token" not in st.session_state:
    st.session_state.son_token = 0
if "toplam_token" not in st.session_state:
    st.session_state.toplam_token = 0


# -----------------------------------------------------------------------------
# Sidebar / Yönetici paneli
# -----------------------------------------------------------------------------
if "admin_acik" not in st.session_state:
    st.session_state.admin_acik = False

with st.sidebar:
    if MASKOT:
        st.image(str(MASKOT), use_container_width=True)
    st.markdown("## TwinBot")
    st.caption("eTwinning proje danışmanı")

    if not st.session_state.admin_acik:
        st.markdown("### Yönetici Paneli")
        admin_girdi = st.text_input("Yönetici şifresi", type="password", placeholder="Şifre")
        if st.button("Yönetici girişi", use_container_width=True):
            if not ADMIN_PASSWORD:
                st.error("ADMIN_PASSWORD tanımlı değil. Streamlit Secrets'a ekleyin.")
            elif admin_girdi == ADMIN_PASSWORD:
                st.session_state.admin_acik = True
                st.rerun()
            else:
                st.error("Şifre hatalı.")
    else:
        st.success("Yönetici paneli açık")
        if st.button("Yönetici panelini kapat", use_container_width=True):
            st.session_state.admin_acik = False
            st.rerun()

        st.markdown("### Sistem")
        st.write(f"**Model:** `{AKTIF_MODEL}`")
        st.write(f"**Güncel web doğrulaması:** {'Açık' if GUNCEL_WEB_ARAMA_AKTIF else 'Kapalı'}")
        st.caption("Bilgi bankası önceliklidir; gerektiğinde model ve web doğrulaması kullanılır.")

        if st.button("Sohbeti temizle", use_container_width=True):
            st.session_state.messages = []
            st.session_state.cevap_cache = {}
            st.session_state.son_token = 0
            st.rerun()

        md = sohbeti_markdowna_cevir(st.session_state.messages)
        st.download_button(
            "Sohbeti indir",
            data=md,
            file_name="twin_sohbet.md",
            mime="text/markdown",
            use_container_width=True,
        )

        st.markdown("---")
        st.markdown("### Hızlı Araçlar")
        arac = st.selectbox(
            "Araç",
            ["Proje Tasarım Sihirbazı", "Kalite Etiketi Hızlı Kontrol", "TwinSpace Kontrol Listesi"],
        )
        if arac == "Proje Tasarım Sihirbazı":
            tema = st.text_input("Tema", placeholder="Örn. dijital vatandaşlık")
            yas = st.text_input("Yaş grubu", placeholder="Örn. 11-14")
            sure = st.text_input("Süre", placeholder="Örn. 4 ay")
            not_ = st.text_area("Not", height=80)
            if st.button("Sihirbazı çalıştır", use_container_width=True):
                prompt = arac_kutusu_promptu(arac, tema=tema, yas=yas, sure=sure, **{"not": not_})
                st.session_state._arac_prompt = prompt
                st.rerun()
        else:
            metin = st.text_area("Proje özeti / not", height=130)
            if st.button("Analiz et", use_container_width=True):
                st.session_state._arac_prompt = arac_kutusu_promptu(arac, metin=metin)
                st.rerun()


# -----------------------------------------------------------------------------
# Ana ekran
# -----------------------------------------------------------------------------
maskot_uri = maskot_data_uri()
maskot_html = (
    f'<img class="heroMascot" src="{maskot_uri}" alt="TwinBot maskotu">'
    if maskot_uri else
    '<div style="width:180px;height:180px;border-radius:18px;background:#fff;border:4px solid #F4C430;display:flex;align-items:center;justify-content:center;color:#0B3D7A;font-weight:800;">TwinBot</div>'
)
st.markdown(
    f"""
<div class="hero">
  <div>{maskot_html}</div>
  <div>
    <div class="heroAccent"></div>
    <h1 class="heroTitle">TwinBot · eTwinning Danışmanı</h1>
    <div class="heroSubtitle">Proje tasarımı, Kalite Etiketi, TwinSpace düzeni ve proje geliştirme için kısa, uygulanabilir ve gerektiğinde kaynak doğrulamalı destek.</div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

if not API_KEY:
    st.error("Gemini API anahtarı bulunamadı. Streamlit Cloud → App settings → Secrets içine `GEMINI_API_KEY = \"...\"` ekleyin.")

# Proje Doktoru
with st.expander("Proje Doktoru", expanded=False):
    st.caption("Proje planı veya Kalite Etiketi metnini yükleyin. PDF, DOCX, TXT ve MD desteklenir.")
    col1, col2 = st.columns([1, 1])
    with col1:
        doktor_file = st.file_uploader("Belge", type=["pdf", "docx", "txt", "md"], key="doktor_file")
    with col2:
        doktor_text = st.text_area("Ek açıklama / yapıştırılan metin", height=130, key="doktor_text")
    if st.button("Projeyi incele", type="primary"):
        try:
            with st.spinner("Belge inceleniyor…"):
                rapor, meta = proje_doktoru_analiz_et(doktor_file, doktor_text)
            st.markdown(rapor)
            st.caption(f"Belge: {meta['belge']}")
            if meta.get("grounding_sources"):
                with st.expander("Güncel doğrulama kaynakları"):
                    for k in meta["grounding_sources"]:
                        st.markdown(f"- [{k['title']}]({k['uri']})")
        except Exception as exc:
            st.error(str(exc))

st.markdown("---")

# Geçmişi göster
for msg in st.session_state.messages:
    with st.chat_message(msg.get("role", "assistant")):

        st.markdown(msg.get("content", ""))
        meta = msg.get("meta", {}) or {}
        if meta.get("source") == "bilgi_bankasi":
            st.markdown('<span class="bank-badge">Bilgi bankası</span>', unsafe_allow_html=True)
        elif meta.get("source") == "web":
            st.markdown('<span class="web-badge">Güncel web doğrulaması</span>', unsafe_allow_html=True)
        elif meta.get("source") == "hybrid":
            st.markdown('<span class="web-badge">Bilgi bankası + AI</span>', unsafe_allow_html=True)
        if meta.get("grounding_sources"):
            with st.expander("Kaynaklar"):
                for k in meta["grounding_sources"]:
                    st.markdown(f"- [{k['title']}]({k['uri']})")

# Sidebar aracından gelen promptu sohbet gibi çalıştır
hazir_prompt = st.session_state.pop("_arac_prompt", None)
chat_prompt = st.chat_input("Sorunu buraya yaz…")
soru = hazir_prompt or chat_prompt

if soru:
    soru = str(soru).strip()
    if soru:
        st.session_state.messages.append({"role": "user", "content": soru, "meta": {}})
        with st.chat_message("user"):
            st.markdown(soru)

        cache_key = normalize(soru)
        cached = st.session_state.cevap_cache.get(cache_key)
        try:
            if cached and not guncel_web_aramasi_gerekli_mi(soru):
                cevap, meta = cached
                meta = dict(meta)
                meta["cache"] = True
            else:
                with st.spinner("Twin düşünüyor…"):
                    cevap, meta = gemini_cevap_uret(soru, st.session_state.messages[:-1])
                # Güncel web cevaplarını uzun süreli cache'leme.
                if meta.get("source") != "web":
                    st.session_state.cevap_cache[cache_key] = (cevap, meta)

            st.session_state.son_token = int(meta.get("total_tokens", 0) or 0)
            st.session_state.toplam_token += st.session_state.son_token
            st.session_state.messages.append({"role": "assistant", "content": cevap, "meta": meta})

            with st.chat_message("assistant"):
                st.markdown(cevap)
                if meta.get("source") == "bilgi_bankasi":
                    st.markdown('<span class="bank-badge">Bilgi bankası</span>', unsafe_allow_html=True)
                elif meta.get("source") == "web":
                    st.markdown('<span class="web-badge">Güncel web doğrulaması</span>', unsafe_allow_html=True)
                elif meta.get("source") == "hybrid":
                    st.markdown('<span class="web-badge">Bilgi bankası + AI</span>', unsafe_allow_html=True)
                if meta.get("grounding_sources"):
                    with st.expander("Kaynaklar"):
                        for k in meta["grounding_sources"]:
                            st.markdown(f"- [{k['title']}]({k['uri']})")
        except Exception as exc:
            hata = f"İşlem tamamlanamadı: {exc}"
            st.session_state.messages.append({"role": "assistant", "content": hata, "meta": {"source": "error"}})
            with st.chat_message("assistant"):
                st.error(hata)
