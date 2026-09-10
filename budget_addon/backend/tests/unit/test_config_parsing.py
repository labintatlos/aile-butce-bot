"""Yapılandırma ayrıştırma testleri.

Eklenti üretimde iki kez üst üste açılışta çöktü ve Supervisor günlüğü yalnızca
"exit code 1" gösterdi. Sebebi buradaydı: `bashio::config`, Home Assistant
ayarlarında **boş bırakılmış** isteğe bağlı bir alan için boş dize değil
`null` dizesini döndürür. Ayrıştırıcı bunu gerçek bir girdi sanıp `ValueError`
fırlatıyor, hata lifespan içinde patlıyor ve uvicorn hiç dinlemeye başlamadan
çıkıyordu.
"""

import pytest

from app.config import Settings, is_blank


def settings(**overrides) -> Settings:
    defaults = dict(_env_file=None)
    defaults.update(overrides)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# bashio'nun "null" dizesi
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   ", "null", "NULL", "None", "~"])
def test_bashio_blank_values_are_treated_as_empty(blank):
    assert is_blank(blank)


@pytest.mark.parametrize("blank", ["", "null", "None", "~"])
def test_an_empty_optional_mapping_does_not_crash(blank):
    """Boş bırakılan `ha_user_map` eklentiyi düşürmemelidir."""
    assert settings(ha_user_map=blank).ha_user_mapping == {}


@pytest.mark.parametrize("blank", ["", "null", "None"])
def test_an_empty_site_url_is_reported_as_absent(blank):
    """`null` gerçek bir adres sanılırsa bildirim bağlantıları bozulurdu."""
    assert settings(site_url=blank).public_url == ""


def test_a_real_site_url_survives():
    configured = settings(site_url="  https://butce.ev.keenetic.pro/ ")
    assert configured.public_url == "https://butce.ev.keenetic.pro/"


def test_the_pre_2_0_setting_name_is_still_read(monkeypatch):
    """Güncellenen kurulumda eski `WEBAPP_PUBLIC_URL` değeri kaybolmamalıdır."""
    monkeypatch.setenv("WEBAPP_PUBLIC_URL", "https://eski.keenetic.pro")
    assert Settings(_env_file=None).public_url == "https://eski.keenetic.pro"


def test_blank_entries_inside_a_mapping_are_skipped():
    assert settings(ha_user_map="abc:aykut,, def:aslihan ").ha_user_mapping == {
        "abc": "aykut",
        "def": "aslihan",
    }


# ---------------------------------------------------------------------------
# Hatali yapilandirma anlasilir mesaj vermeli
# ---------------------------------------------------------------------------


def test_a_mapping_without_a_colon_names_the_broken_setting():
    with pytest.raises(ValueError) as error:
        settings(ha_user_map="aykut,aslihan").ha_user_mapping
    assert "ha_user_map" in str(error.value)
    assert "anahtar:değer" in str(error.value)


def test_a_half_written_mapping_entry_is_refused():
    with pytest.raises(ValueError):
        settings(ha_user_map="abc:").ha_user_mapping
    with pytest.raises(ValueError):
        settings(ha_user_map=":aykut").ha_user_mapping


# ---------------------------------------------------------------------------
# Acilis dogrulamasi
# ---------------------------------------------------------------------------


def test_validation_passes_for_a_typical_installation():
    settings(
        ha_user_map="70bbe879:aykut,6ab54aa0:aslihan",
        site_url="https://butce.ev.keenetic.pro",
    ).validate_configuration()


def test_validation_passes_when_every_optional_field_is_blank():
    """Yeni kurulumda hiçbir ayar doldurulmadan eklenti açılabilmelidir."""
    settings(ha_user_map="null", site_url="null").validate_configuration()


def test_validation_surfaces_a_broken_mapping():
    with pytest.raises(ValueError) as error:
        settings(ha_user_map="bozuk-girdi").validate_configuration()
    assert "ha_user_map" in str(error.value)


def test_the_summary_never_contains_secrets():
    summary = settings(
        session_secret="GIZLI-ANAHTAR", smtp_password="GIZLI-SIFRE"
    ).safe_summary()
    assert "GIZLI" not in str(summary)
