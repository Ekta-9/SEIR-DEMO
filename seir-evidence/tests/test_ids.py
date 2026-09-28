import pytest

from app.ids import is_test_path, make_evidence_id, module_of, path_to_component_id


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/main/java/com/shop/payment/LegacyPaymentService.java", "com.shop.payment.LegacyPaymentService"),
        ("payment-service/src/main/java/com/shop/Pay.java", "com.shop.Pay"),
        ("src\\main\\java\\com\\shop\\Pay.java", "com.shop.Pay"),
        ("src/test/java/com/shop/PayTest.java", "com.shop.PayTest"),
        ("src/java/org/apache/commons/lang/StringUtils.java", "org.apache.commons.lang.StringUtils"),
        ("src/main/java/Main.java", "Main"),
        ("src/main/resources/application.yml", None),
        ("docs/Example.java", None),
        ("src/main/java/org/apache/commons/lang3/package-info.java", None),
        ("src/main/java/module-info.java", None),
    ],
)
def test_path_to_component_id(path, expected):
    assert path_to_component_id(path) == expected


def test_module_and_test_detection():
    assert module_of("payment-service/src/main/java/com/shop/Pay.java") == "payment-service"
    assert module_of("src/main/java/com/shop/Pay.java") is None
    assert is_test_path("core/src/test/java/com/shop/PayTest.java")
    assert not is_test_path("src/main/java/com/shop/Pay.java")


def test_make_evidence_id_is_stable_and_none_safe():
    assert make_evidence_id("a", None, 1) == make_evidence_id("a", None, 1)
    assert make_evidence_id("a", None) != make_evidence_id("a", "b")
