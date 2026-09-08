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
    defaults = dict(_env_file=None, authorized_telegram_ids="111,222")
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
    assert settings(user_display_names=blank).display_names == {}


@pytest.mark.parametrize("blank", ["", "null", "None"])
def test_an_empty_public_url_is_reported_as_absent(blank):
    """`null` gerçek bir adres sanılırsa gereksiz bir sunucu açılırdı."""
    assert settings(webapp_public_url=blank).public_url == ""


def test_a_real_public_url_survives():
    configured = settings(webapp_public_url="  https://ev.keenetic.pro/ ")
    assert configured.public_url == "https://ev.keenetic.pro/"


def test_blank_entries_inside_a_list_are_skipped():
    assert settings(authorized_telegram_ids="111,,222, ").authorized_ids == frozenset(
        {111, 222}
    )


# ---------------------------------------------------------------------------
# Hatali yapilandirma anlasilir mesaj vermeli
# ---------------------------------------------------------------------------


def test_a_mapping_without_a_colon_names_the_broken_setting():
    with pytest.raises(ValueError) as error:
        settings(user_display_names="Aykut,Aslıhan").display_names
    assert "user_display_names" in str(error.value)
    assert "anahtar:değer" in str(error.value)


def test_a_non_numeric_telegram_id_names_the_broken_setting():
    with pytest.raises(ValueError) as error:
        settings(authorized_telegram_ids="aykut").authorized_ids
    assert "authorized_telegram_ids" in str(error.value)


def test_a_half_written_mapping_entry_is_refused():
    with pytest.raises(ValueError):
        settings(ha_user_map="abc:").ha_user_mapping
    with pytest.raises(ValueError):
        settings(ha_user_map=":111").ha_user_mapping


# ---------------------------------------------------------------------------
# Acilis dogrulamasi
# ---------------------------------------------------------------------------


def test_validation_passes_for_a_typical_installation():
    configured = settings(
        user_display_names="111:Aykut,222:Aslıhan",
        ha_user_map="70bbe879:111,6ab54aa0:222",
        webapp_public_url="null",
    )
    configured.validate_configuration()


def test_validation_passes_when_every_optional_field_is_blank():
    """Kullanıcıya `webapp_public_url` alanını boş bırakması söyleniyor."""
    settings(
        user_display_names="111:Aykut",
        ha_user_map="null",
        webapp_public_url="null",
    ).validate_configuration()


def test_validation_refuses_an_installation_with_no_authorised_users():
    with pytest.raises(ValueError) as error:
        settings(authorized_telegram_ids="").validate_configuration()
    assert "authorized_telegram_ids" in str(error.value)


def test_validation_surfaces_a_broken_mapping():
    with pytest.raises(ValueError) as error:
        settings(ha_user_map="bozuk-girdi").validate_configuration()
    assert "ha_user_map" in str(error.value)


def test_the_summary_never_contains_the_token():
    summary = settings(telegram_bot_token="123456:GERCEK-TOKEN").safe_summary()
    assert "GERCEK-TOKEN" not in str(summary)
    assert summary["telegram_bot_token_configured"] is True
