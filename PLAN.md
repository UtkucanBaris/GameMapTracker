# GameMapTracker — Geliştirme Planı

PySide6 tabanlı masaüstü uygulama: Windows üzerinde oyun belleğinden X/Y okur, patika ve POI kaydeder, isteğe bağlı harita görseli üzerinde kalibre edilmiş koordinatlarla çizer. Canlı önizleme, kayıt sırasında artımlı patika ve smooth live marker ile akıcı takip desteklenir.

## Aşama 0: Temel Uygulama ⭐⭐⭐ ✅
Bellek okuma, polling, veri modeli ve ana arayüz.

- `main.py`: Uygulama giriş noktası ✅
- `memory_reader.py`: Win32 process attach + float okuma ✅
- `polling_service.py`: Periyodik okuma + ardışık hata / idle sinyalleri ✅
- `trail_model.py`: Çoklu path, minimum mesafe filtresi ✅
- `settings_service.py`: `~/.exanimap_helper/settings.json` + `trail.json` ✅
- `views/main_window.py`: Koyu tema UI, process seçimi, adres ve interval ayarları ✅
- **Çıktı:** Çalışan tracker iskeleti, ayarlar ve trail kalıcılığı ✅

## Aşama 1: Harita Resmi Yükleme + Kalibrasyon ⭐⭐⭐ ✅
En yüksek görsel etki. Oyun haritasını PNG/JPEG olarak yükle, trail'i harita üzerinde çiz.

- `graph_renderer.py`: Arkaplan resmi + affine transform (2 nokta kalibrasyon) ✅
- `views/main_window.py`: "Load Map" butonu, kalibrasyon arayüzü ✅
- `settings_service.py`: Harita yolu + kalibrasyon noktaları kaydı ✅
- **Çıktı:** Trail oyun haritası üzerinde, doğru pozisyonda ✅

## Aşama 2: Teleport / Loading Algılama ⭐ ✅
Koordinat anormal sıçradığında otomatik yeni path başlat.

- `trail_model.py`: `add()` içinde sıçrama kontrolü (`teleport_threshold`) ✅
- `views/main_window.py`: Threshold ayarı için `QDoubleSpinBox` ✅
- **Çıktı:** Fast travel / ölüm sonrası patika otomatik bölünür ✅

## Aşama 3: Path Smoothing ⭐ ✅
Gereksiz noktaları temizle, daha temiz görüntü.

- `trail_model.py`: Ramer-Douglas-Peucker algoritması (`smooth()`) ✅
- `views/main_window.py`: "Smooth" butonu + epsilon `QDoubleSpinBox` ✅
- **Çıktı:** Aynı çizgi üzerindeki gereksiz noktalar kalkar ✅

## Aşama 4: Path Renkleri + Zoom/Pan ⭐⭐ ✅
Her path farklı renkte, interaktif görüntüleme.

- `graph_renderer.py`: 10 renkli palet, `ScrollHandDrag` ile pan, mouse wheel zoom ✅
- `graph_renderer.py`: "Zoom Fit" butonu (`zoom_to_fit()`) ✅
- **Çıktı:** Çoklu path ayırt edilebilir, kullanıcı haritada gezinir ✅

## Aşama 5: Heat Map ⭐ ✅
Sık geçilen yerlerin yoğunluk haritası.

- `graph_renderer.py`: Yarı-saydam kırmızı daireler (`_render_heat_map()`) ✅
- `views/main_window.py`: "Heat Map" toggle butonu ✅
- **Çıktı:** Sık kullanılan rotalar görselleşir ✅

## Aşama 6: Bölge Profilleri ⭐⭐ ✅
Her oyun/zone için ayrı yapılandırma.

- `settings_service.py`: `profiles: dict` + `_apply_profile()` / `_save_current_as_profile()` ✅
- `views/main_window.py`: `QComboBox` + "Save As" / "Delete" butonları ✅
- **Çıktı:** Farklı oyunlar arası hızlı geçiş ✅

## Aşama 7: Canlı Konum ve Kayıt ⭐⭐ ✅
Polling sırasında canlı konum ve kayıt döngüsü.

- `views/main_window.py`: Canlı X/Y etiketleri, şüpheli değer uyarısı ✅
- `hotkey_service.py`: F8 ile kayıt başlat/durdur ✅
- `polling_service.py`: Idle eşiği — durunca otomatik pause, hareketle resume ✅
- `graph_renderer.py`: Kayıt istatistikleri overlay (`update_stats`) ✅
- **Çıktı:** Oyun oynarken patika kaydı ve canlı geri bildirim ✅

## Aşama 8: POI ⭐ ✅
Önemli noktaları işaretle ve yönet.

- `trail_model.py`: `POI` + `add_poi` / `update_poi` ✅
- `hotkey_service.py`: F10 ile kayıt sırasında POI ✅
- `graph_renderer.py`: Kategori renkli halka + etiket ✅
- `views/main_window.py`: Veri listesi — seçim, Go To, düzenle, sil ✅
- **Çıktı:** Boss, loot, giriş vb. noktalar haritada ve listede ✅

## Aşama 9: Import / Export ⭐ ✅
Patikayı dışa aktar ve geri yükle.

- `export_service.py`: TXT import/export, PNG export ✅
- `views/main_window.py`: Import, Export TXT, Export PNG butonları ✅
- `settings_service.py`: `save_trail` / `load_trail` otomatik kalıcılık ✅
- **Çıktı:** Veri paylaşımı ve yedekleme ✅

## Aşama 10: Artımlı Canlı Patika ⭐⭐ ✅
Kayıt sırasında her tick tam sahne yeniden çizimi yerine artımlı çizim.

- `graph_renderer.py`: `add_trail_point()` — cubic segmentler, aktif path ✅
- `graph_renderer.py`: Son nokta ile ham konum arası yarı saydam tail çizgisi ✅
- `views/main_window.py`: Kayıtta `add_trail_point` + debounced tam render ✅
- **Çıktı:** Akıcı canlı patika, düşük gecikme ✅

## Aşama 11: Takip ve Görsel Seçenekler ⭐ ✅
Haritada gezinme ve görünüm tercihleri.

- `views/main_window.py`: Auto Follow, Zoom Follow, Flip X/Y, Fade Trail ✅
- `graph_renderer.py`: `_follow_tick` ile kamera takibi ✅
- `graph_renderer.py`: Fade trail — path başına alpha gradyanı ✅
- **Çıktı:** Kayıt sırasında oyuncuyu takip, isteğe bağlı soluk eski segmentler ✅

## Aşama 12: Smooth Live Tracking ⭐ ✅
Canlı marker ve tail çizgisinin polling adımları arasında yumuşak hareketi.

- `graph_renderer.py`: 16 ms `QTimer` + `_update_smooth_marker` ✅
- `graph_renderer.py`: `set_smooth_marker_target` — hız adaptasyonu, interpolasyon ✅
- `graph_renderer.py`: Tail çizgisi anchor → smooth marker konumu ✅
- **Çıktı:** Keskin sıçramasız canlı konum göstergesi ✅

## Gelecek / Backlog

- ⬜ README: kurulum (`uv`), Exanima adresleri, kısa kullanım
- ⬜ Oyun üstü overlay / şeffaf pencere (isteğe bağlı)
- ⬜ Ek export formatları (ör. GPX)
- ⬜ Kalibrasyon iyileştirmesi (3+ nokta veya perspektif)
- ⬜ Adres bulucu / pointer chain yardımcısı
- ⬜ Linux veya non-Win32 için bellek okuma (şu an `memory_reader` Win32)
