from django.test import TestCase

from observability.services import _redact


class RedactionTests(TestCase):
    def test_top_level_sensitive_keys_are_redacted(self):
        payload = {"password": "secret123", "username": "alice"}
        result = _redact(payload)
        self.assertEqual(result["password"], "***REDACTED***")
        self.assertEqual(result["username"], "alice")

    def test_nested_sensitive_keys_inside_dicts_are_redacted(self):
        payload = {
            "user": {
                "name": "alice",
                "password": "secret123",
                "address_line1": "123 Main St",
            }
        }
        result = _redact(payload)
        self.assertEqual(result["user"]["name"], "alice")
        self.assertEqual(result["user"]["password"], "***REDACTED***")
        self.assertEqual(result["user"]["address_line1"], "***REDACTED***")

    def test_sensitive_keys_inside_lists_of_dicts_are_redacted(self):
        payload = {
            "users": [
                {"name": "alice", "token": "abc123"},
                {"name": "bob", "secret_key": "def456"},
            ]
        }
        result = _redact(payload)
        self.assertEqual(result["users"][0]["name"], "alice")
        self.assertEqual(result["users"][0]["token"], "***REDACTED***")
        self.assertEqual(result["users"][1]["name"], "bob")
        self.assertEqual(result["users"][1]["secret_key"], "***REDACTED***")

    def test_non_sensitive_keys_are_preserved_unchanged(self):
        payload = {
            "action": "login",
            "details": {
                "ip": "1.2.3.4",
                "items": [{"id": 1, "name": "test"}],
            },
        }
        result = _redact(payload)
        self.assertEqual(result["action"], "login")
        self.assertEqual(result["details"]["ip"], "1.2.3.4")
        self.assertEqual(result["details"]["items"][0]["id"], 1)
        self.assertEqual(result["details"]["items"][0]["name"], "test")

    def test_deeply_nested_sensitive_keys_are_redacted(self):
        payload = {
            "level1": {
                "level2": {
                    "level3": {
                        "account_number": "123456",
                        "safe_field": "ok",
                    }
                }
            }
        }
        result = _redact(payload)
        self.assertEqual(
            result["level1"]["level2"]["level3"]["account_number"], "***REDACTED***"
        )
        self.assertEqual(result["level1"]["level2"]["level3"]["safe_field"], "ok")

    def test_none_payload_returns_empty_dict(self):
        self.assertEqual(_redact(None), {})

    def test_empty_payload_returns_empty_dict(self):
        self.assertEqual(_redact({}), {})

    def test_pattern_matching_redacts_partial_key_matches(self):
        payload = {
            "user_phone": "555-1234",
            "home_address": "123 Main",
            "ssn": "123-45-6789",
        }
        result = _redact(payload)
        self.assertEqual(result["user_phone"], "***REDACTED***")
        self.assertEqual(result["home_address"], "***REDACTED***")
        self.assertEqual(result["ssn"], "***REDACTED***")

    def test_bypass_variant_key_names_are_redacted(self):
        payload = {
            "user_password": "secret",
            "Password": "SECRET",
            "new_token": "tok123",
            "ACCESS_TOKEN": "atok",
            "secret_value": "sval",
            "api_key": "apikey123",
            "private_key_pem": "----BEGIN----",
            "credential_hash": "abc",
            "passwd_hash": "def",
        }
        result = _redact(payload)
        for key in payload:
            self.assertEqual(
                result[key],
                "***REDACTED***",
                f"Key '{key}' should be redacted but was not",
            )

    def test_config_payload_is_redacted_as_opaque_blob(self):
        payload = {
            "version_number": 3,
            "config_payload": {"feature_flags": {"beta": True}, "api_secret": "s3cr3t"},
        }
        result = _redact(payload)
        self.assertEqual(result["config_payload"], "***REDACTED***")
        self.assertEqual(result["version_number"], 3)

    def test_credit_card_and_financial_keys_are_redacted(self):
        payload = {
            "credit_card": "4111111111111111",
            "card_number": "4111111111111111",
            "cvv": "123",
            "account_number": "9876543210",
        }
        result = _redact(payload)
        for key in payload:
            self.assertEqual(
                result[key],
                "***REDACTED***",
                f"Key '{key}' should be redacted but was not",
            )

    def test_authorization_and_api_keys_are_redacted(self):
        payload = {
            "authorization": "Bearer xxx",
            "api_key": "ak-12345",
            "refresh_token": "rt-67890",
            "access_token": "at-abcdef",
        }
        result = _redact(payload)
        for key in payload:
            self.assertEqual(
                result[key],
                "***REDACTED***",
                f"Key '{key}' should be redacted but was not",
            )

    def test_mixed_safe_and_sensitive_at_multiple_levels(self):
        payload = {
            "action": "config.update",
            "metadata": {
                "version": 5,
                "changed_by": "admin",
                "old_api_key": "oldkey",
                "items": [
                    {"name": "flag_a", "value": True},
                    {"name": "secret_setting", "credential": "xyz"},
                ],
            },
        }
        result = _redact(payload)
        self.assertEqual(result["action"], "config.update")
        self.assertEqual(result["metadata"]["version"], 5)
        self.assertEqual(result["metadata"]["changed_by"], "admin")
        self.assertEqual(result["metadata"]["old_api_key"], "***REDACTED***")
        self.assertEqual(result["metadata"]["items"][0]["name"], "flag_a")
        self.assertEqual(result["metadata"]["items"][0]["value"], True)
        self.assertEqual(result["metadata"]["items"][1]["credential"], "***REDACTED***")

    def test_nested_path_variants_are_redacted(self):
        payload = {
            "metadata": {
                "request": {
                    "headers": {
                        "Authorization": "Bearer xyz",
                        "x-session-key": "skey-123",
                    }
                },
                "actors": [
                    {"name": "alice", "contactPhone": "555-1111"},
                    {"name": "bob", "private-key-pem": "---BEGIN---"},
                ],
            }
        }
        result = _redact(payload)
        self.assertEqual(
            result["metadata"]["request"]["headers"]["Authorization"],
            "***REDACTED***",
        )
        self.assertEqual(
            result["metadata"]["request"]["headers"]["x-session-key"],
            "***REDACTED***",
        )
        self.assertEqual(result["metadata"]["actors"][0]["name"], "alice")
        self.assertEqual(
            result["metadata"]["actors"][0]["contactPhone"],
            "***REDACTED***",
        )
        self.assertEqual(result["metadata"]["actors"][1]["name"], "bob")
        self.assertEqual(
            result["metadata"]["actors"][1]["private-key-pem"],
            "***REDACTED***",
        )

    def test_opaque_config_payload_variant_is_redacted(self):
        payload = {
            "metadata": {
                "config-payload": {
                    "safe_flag": True,
                    "nested_secret_value": "s3cr3t",
                }
            }
        }
        result = _redact(payload)
        self.assertEqual(result["metadata"]["config-payload"], "***REDACTED***")
