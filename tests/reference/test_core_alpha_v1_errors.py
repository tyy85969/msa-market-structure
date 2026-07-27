import pytest

from msa.reference import (
    MSAReferenceError,
    ReferenceAuthorityError,
    ReferenceConfigurationError,
    ReferenceInputError,
    ReferenceSerializationError,
    validate_core_alpha_v1_config,
    validate_core_alpha_v1_profile,
)


def test_error_hierarchy_is_reference_domain_only() -> None:
    assert issubclass(ReferenceConfigurationError, MSAReferenceError)
    assert issubclass(ReferenceInputError, MSAReferenceError)
    assert issubclass(ReferenceSerializationError, MSAReferenceError)
    assert issubclass(ReferenceAuthorityError, MSAReferenceError)


@pytest.mark.parametrize("value", (None, False, 0, "", (), {}))
def test_invalid_public_inputs_do_not_leak_python_errors(value: object) -> None:
    with pytest.raises(ReferenceInputError):
        validate_core_alpha_v1_config(value)
    with pytest.raises(ReferenceInputError):
        validate_core_alpha_v1_profile(value)
