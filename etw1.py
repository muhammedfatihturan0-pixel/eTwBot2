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
st.caption("Hizmeti geliştirmek amacıyla sorular ve yanıtlar yöneticiye özel kayıt sisteminde saklanabilir. Lütfen mesajlarda parola veya gereksiz kişisel bilgi paylaşmayın.")
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
            soru_kaydi_ekle(soru, cevap, meta, durum="başarılı")

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
            soru_kaydi_ekle(soru, "", {"source": "error"}, durum="hata", hata=str(exc))
