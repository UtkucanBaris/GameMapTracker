# GameMapTracker

Windows üzerinde Exanima koordinatlarını okuyup patika ve POI olarak kaydeden
PySide6 masaüstü uygulaması.

> Bu proje, Exanima hareket takibi fikri için
> [Sokkero/exanimapHelper](https://github.com/Sokkero/exanimapHelper)
> projesinden esinlenilmiştir. Bağımsız bir Python uygulamasıdır; orijinal depo
> ile doğrudan bağlantılı değildir.

## Gereksinimler

- Windows 10/11
- Python 3.12 veya üzeri
- [uv](https://docs.astral.sh/uv/)
- Çalışan Exanima süreci (bellek adresleri profile göre değiştirilebilir)

## Kurulum ve çalıştırma

```powershell
uv sync
uv run python main.py
```

Uygulama ayarlarını ve kayıtları `%USERPROFILE%\.exanimap_helper\` altında
saklar. Varsayılan X/Y adresleri UI veya profile ekranından değiştirilebilir.

## Temel kullanım

- `F8`: Kayıt başlat/durdur.
- `F10`: Kayıt sırasında mevcut konuma POI ekle.
- Harita yüklemek için iki oyun/image noktasıyla calibration yap.
- Kayıt dışı modda bir POI seçerek trail paint/erase kullanılabilir.

## Kalite komutları

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
$env:QT_QPA_PLATFORM = "offscreen"; uv run pytest -m qt
uv run python tests/perf_harness.py --points 10000
```

Windows ve görsel davranış kontrolleri için
[`docs/MANUAL_REGRESSION.md`](docs/MANUAL_REGRESSION.md) dosyasını kullanın.
