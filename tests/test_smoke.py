from export_service import ExportResult
from polling_service import PollingService
from settings_service import AppSettings, MapCalibration
from trail_model import TrailModel


def test_core_modules_import_and_construct() -> None:
    model = TrailModel()
    settings = AppSettings()
    calibration = MapCalibration()

    assert model.paths == []
    assert settings.interval_ms == 500
    assert not calibration.is_complete()
    assert ExportResult().paths == []
    assert isinstance(PollingService, type)
