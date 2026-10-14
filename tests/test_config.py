"""EP-00.02: E-02.01, E-07.03/E-07.06, P-04/P-10/P-17, ADR-006/011."""

import tomllib
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from acoa.config import (
    AccountSettings,
    ApplicationLimits,
    AuthorizationReference,
    BudgetLimits,
    ConfigurationError,
    OutreachLimits,
    PrivacySettings,
    Settings,
    external_action_readiness,
    load_settings,
    settings_from_mapping,
)

pytestmark = pytest.mark.configuration

# Synthetic values exercise readiness; they are not deployment defaults or real grants.
COMPLETE_TOML = """
dry_run = false
external_actions_enabled = true
[applications]
max_per_day = 2
max_per_week = 5
[outreach]
per_company_limit = 1
per_contact_limit = 1
[budget]
currency = "XXX"
max_currency_per_day = 1.25
max_currency_per_month = 7.50
max_tokens_per_task = 9
max_time_per_task = 30
[authorization]
grant_id = "00000000-0000-0000-0000-000000000001"
[accounts]
authorized_emails = ["sender@example.invalid"]
[privacy]
allowed_data_categories = ["synthetic_cv"]
"""

REQUIRED_LIMITS = (
    ("applications", "max_per_day"),
    ("applications", "max_per_week"),
    ("outreach", "per_company_limit"),
    ("outreach", "per_contact_limit"),
    ("budget", "max_currency_per_day"),
    ("budget", "max_currency_per_month"),
    ("budget", "max_tokens_per_task"),
    ("budget", "max_time_per_task"),
)


@pytest.fixture
def complete_data() -> dict[str, object]:
    return tomllib.loads(COMPLETE_TOML, parse_float=Decimal)


def test_defaults_block_external_action_configuration() -> None:
    settings = settings_from_mapping({})
    readiness = external_action_readiness(settings)

    assert settings == Settings()
    assert settings.dry_run is True
    assert settings.external_actions_enabled is False
    assert settings.budget.max_currency_per_day is None
    assert "dry_run_enabled" in readiness.blockers
    assert "external_actions_disabled" in readiness.blockers
    assert not readiness.ready


def test_example_preserves_safe_defaults_and_unset_limits() -> None:
    example = Path(__file__).resolve().parents[1] / "config.example.toml"
    settings = load_settings(example)

    assert settings == Settings()
    assert not external_action_readiness(settings).ready


def test_complete_declarations_satisfy_only_configuration_readiness(
    complete_data: dict[str, object],
) -> None:
    settings = settings_from_mapping(complete_data)

    assert external_action_readiness(settings).ready
    assert settings.budget.max_currency_per_day == Decimal("1.25")
    assert settings.authorization.grant_id is not None


@pytest.mark.parametrize(
    ("flag", "value", "blocker"),
    (
        ("dry_run", True, "dry_run_enabled"),
        ("external_actions_enabled", False, "external_actions_disabled"),
    ),
)
def test_each_safety_switch_independently_blocks_readiness(
    complete_data: dict[str, object], flag: str, value: bool, blocker: str
) -> None:
    complete_data[flag] = value

    readiness = external_action_readiness(settings_from_mapping(complete_data))

    assert readiness.blockers == (blocker,)


@pytest.mark.parametrize(
    ("section_name", "key"),
    REQUIRED_LIMITS
    + (
        ("budget", "currency"),
        ("authorization", "grant_id"),
        ("accounts", "authorized_emails"),
        ("privacy", "allowed_data_categories"),
    ),
)
def test_each_missing_required_setting_blocks_readiness(
    complete_data: dict[str, object], section_name: str, key: str
) -> None:
    section = complete_data[section_name]
    assert isinstance(section, dict)
    section.pop(key)

    readiness = external_action_readiness(settings_from_mapping(complete_data))

    assert readiness.blockers == (f"{section_name}.{key}",)


@pytest.mark.parametrize(("section_name", "key"), REQUIRED_LIMITS)
def test_zero_limits_are_valid_but_block_readiness(
    complete_data: dict[str, object], section_name: str, key: str
) -> None:
    section = complete_data[section_name]
    assert isinstance(section, dict)
    section[key] = 0

    readiness = external_action_readiness(settings_from_mapping(complete_data))

    assert readiness.blockers == (f"{section_name}.{key}",)


@pytest.mark.parametrize("flag", ("dry_run", "external_actions_enabled"))
@pytest.mark.parametrize("value", (0, 1, "false", "true", None))
def test_boolean_fields_reject_truthiness_coercion(flag: str, value: object) -> None:
    with pytest.raises(ConfigurationError, match="must be a boolean"):
        settings_from_mapping({flag: value})


@pytest.mark.parametrize("value", (-1, True, False, 1.5, "10", Decimal("1")))
def test_count_fields_reject_invalid_values(value: object) -> None:
    with pytest.raises(ConfigurationError, match="nonnegative integer"):
        settings_from_mapping({"applications": {"max_per_day": value}})


@pytest.mark.parametrize(
    "value", (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), -1, True, 1.5, "1.5")
)
def test_money_fields_reject_nonfinite_negative_and_ambiguous_values(value: object) -> None:
    with pytest.raises(ConfigurationError, match="finite nonnegative decimal"):
        settings_from_mapping({"budget": {"max_currency_per_day": value}})


@pytest.mark.parametrize("value", ("usd", "US", "123", " US", 123))
def test_currency_label_is_explicit_and_unambiguous(value: object) -> None:
    with pytest.raises(ConfigurationError, match="three-letter uppercase"):
        settings_from_mapping({"budget": {"currency": value}})


@pytest.mark.parametrize("section_name", ("applications", "budget", "authorization", "privacy"))
def test_unknown_keys_are_rejected_without_disclosing_the_key(section_name: str) -> None:
    with pytest.raises(ConfigurationError) as error:
        settings_from_mapping({section_name: {"synthetic-private-key": "synthetic-private-value"}})

    assert "synthetic-private" not in str(error.value)


def test_unknown_top_level_key_is_rejected_without_disclosing_its_value() -> None:
    with pytest.raises(ConfigurationError) as error:
        settings_from_mapping({"external_actions_enable": "synthetic-private-value"})

    assert str(error.value) == "Unknown fields in configuration."


@pytest.mark.parametrize("value", (None, True, "table", []))
def test_sections_must_be_tables(value: object) -> None:
    with pytest.raises(ConfigurationError, match="must be a table"):
        settings_from_mapping({"budget": value})


@pytest.mark.parametrize("value", ("invalid", "", 1, True))
def test_grant_reference_requires_a_uuid_and_redacts_input(value: object) -> None:
    with pytest.raises(ConfigurationError, match="UUID string"):
        settings_from_mapping({"authorization": {"grant_id": value}})


@pytest.mark.parametrize("value", ("account", [""], [" trailing "], [1], [True]))
@pytest.mark.parametrize(
    ("section_name", "key"),
    (("accounts", "authorized_emails"), ("privacy", "allowed_data_categories")),
)
def test_scope_declarations_require_arrays_of_nonempty_strings(
    section_name: str, key: str, value: object
) -> None:
    with pytest.raises(ConfigurationError):
        settings_from_mapping({section_name: {key: value}})


def test_loading_preserves_decimal_precision(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text(
        "[budget]\nmax_currency_per_day = 0.100000000000000000000001\n", encoding="utf-8"
    )

    settings = load_settings(path)

    assert settings.budget.max_currency_per_day == Decimal("0.100000000000000000000001")


def test_empty_explicit_file_ignores_environment_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "settings.toml"
    path.write_text("", encoding="utf-8")
    monkeypatch.setenv("ACOA_DRY_RUN", "false")
    monkeypatch.setenv("ACOA_EXTERNAL_ACTIONS_ENABLED", "true")

    assert load_settings(path) == Settings()


@pytest.mark.parametrize(
    "contents",
    (
        b"[invalid",
        b"\xff",
        b'dry_run = "synthetic-private-value"\n?',
        b"[budget]\nmax_currency_per_day = 1e9999999999999999999999999999999\n",
    ),
)
def test_malformed_files_report_only_a_redacted_error(tmp_path: Path, contents: bytes) -> None:
    path = tmp_path / "settings.toml"
    path.write_bytes(contents)

    with pytest.raises(ConfigurationError) as error:
        load_settings(path)

    assert str(error.value) == "Unable to load configuration TOML."
    assert error.value.__suppress_context__


def test_missing_file_does_not_fall_back_to_a_permissive_configuration(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="Unable to load configuration TOML"):
        load_settings(tmp_path / "missing.toml")


def test_directory_cannot_be_loaded_as_configuration(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="Unable to load configuration TOML"):
        load_settings(tmp_path)


@pytest.mark.parametrize(
    "constructor",
    (
        lambda: Settings(dry_run=cast(bool, "false")),
        lambda: Settings(budget=cast(BudgetLimits, {})),
        lambda: ApplicationLimits(max_per_day=True),
        lambda: OutreachLimits(per_contact_limit=-1),
        lambda: BudgetLimits(max_tokens_per_task=False),
        lambda: BudgetLimits(max_currency_per_day=Decimal("NaN")),
        lambda: AuthorizationReference(grant_id=cast(UUID, "invalid")),
        lambda: AccountSettings(authorized_emails=cast(tuple[str, ...], ["synthetic"])),
        lambda: PrivacySettings(allowed_data_categories=("",)),
    ),
)
def test_direct_construction_validates_invariants(constructor: Callable[[], object]) -> None:
    with pytest.raises(ConfigurationError):
        constructor()


@pytest.mark.parametrize("field_name", ("dry_run", "external_actions_enabled"))
def test_settings_are_immutable_and_detached_from_input_lists(
    complete_data: dict[str, object], field_name: str
) -> None:
    settings = settings_from_mapping(complete_data)
    accounts = complete_data["accounts"]
    assert isinstance(accounts, dict)
    accounts["authorized_emails"].clear()

    assert settings.accounts.authorized_emails == ("sender@example.invalid",)
    with pytest.raises(FrozenInstanceError):
        setattr(settings, field_name, True)


def test_account_and_authorization_references_are_not_exposed_in_repr(
    complete_data: dict[str, object],
) -> None:
    settings = settings_from_mapping(complete_data)

    assert "sender@example.invalid" not in repr(settings)
    assert "synthetic_cv" not in repr(settings)
    assert "00000000-0000-0000-0000-000000000001" not in repr(settings)
