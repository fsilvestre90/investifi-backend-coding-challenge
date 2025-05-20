from fastapi.testclient import TestClient
from test.helpers import InvestifiTestCase
from src.api import app
from hypothesis import given, settings
from hypothesis.strategies import text, sampled_from, decimals, composite
from decimal import Decimal
from src.model import User, CryptoType, Frequency
from uuid import uuid4
from src.schemas import OrderResponse

# --- Constants ---
VALID_CRYPTOS = {e.value for e in CryptoType}
VALID_FREQUENCIES = {e.value for e in Frequency}


# --- Helpers ---
def build_order_payload(crypto, frequency, amount):
    # Normalize enums and format amount as string with 2 decimal places
    if isinstance(crypto, CryptoType):
        crypto = crypto.value
    if isinstance(frequency, Frequency):
        frequency = frequency.value
    if isinstance(amount, Decimal):
        amount = f"{amount:.2f}"
    else:
        # Try to convert to Decimal and format
        try:
            amount = f"{Decimal(amount):.2f}"
        except Exception:
            amount = str(amount)
    return {"crypto": crypto, "frequency": frequency, "amount": amount}


def make_user(user_id: str, first_name="Test", last_name="User"):
    from src.model import UserInfo

    user = User(
        user_id=user_id, info=UserInfo(first_name=first_name, last_name=last_name)
    )
    user.save()
    return user


@composite
def order_input(draw):
    return {
        "crypto": draw(sampled_from(list(VALID_CRYPTOS))),
        "frequency": draw(sampled_from(list(VALID_FREQUENCIES))),
        "amount": draw(
            decimals(min_value=Decimal("0.01"), max_value=Decimal("9999999999.99"), places=2)
        ),
    }


# --- Base Test Class with shared helpers ---
class BaseRecurringOrderTest(InvestifiTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = TestClient(app)
        cls.url_template = "/users/{user_id}/recurring-orders"

    def url_for(self, user_id):
        return self.url_template.format(user_id=user_id)

    def post_order(self, user_id: str, payload: dict):
        return self.client.post(self.url_for(user_id), json=payload)

    def create_user(self, user_id):
        return make_user(user_id, first_name="Test", last_name="User")

    def generate_user_id(self, prefix="user") -> str:
        return f"{prefix}-{uuid4().hex[-6:]}"


# --- Requirements Validation Tests ---
class TestRecurringOrderValidation(BaseRecurringOrderTest):

    def test_invalid_crypto_rejected(self):
        user_id = self.generate_user_id("invalid-crypto")
        self.create_user(user_id)
        res = self.post_order(
            user_id, build_order_payload("DOGE", Frequency.DAILY, Decimal("10.00"))
        )
        self.assertEqual(
            res.status_code, 422, f"Expected 422, got {res.status_code} — {res.text}"
        )

    def test_invalid_frequency_rejected(self):
        user_id = self.generate_user_id("invalid-frequency")
        self.create_user(user_id)
        res = self.post_order(
            user_id, build_order_payload(CryptoType.BTC, "Weekly", Decimal("10.00"))
        )
        self.assertEqual(
            res.status_code, 422, f"Expected 422, got {res.status_code} — {res.text}"
        )

    def test_zero_amount_rejected(self):
        user_id = self.generate_user_id("zero-amount")
        self.create_user(user_id)
        res = self.post_order(
            user_id,
            build_order_payload(CryptoType.BTC, Frequency.DAILY, Decimal("0.00")),
        )
        self.assertEqual(
            res.status_code, 422, f"Expected 422, got {res.status_code} — {res.text}"
        )

    def test_duplicate_order_rejected(self):
        user_id = self.generate_user_id("duplicate-order")
        self.create_user(user_id)
        payload = build_order_payload(CryptoType.BTC, Frequency.DAILY, Decimal("10.00"))
        res1 = self.post_order(user_id, payload)
        res2 = self.post_order(user_id, payload)
        self.assertEqual(
            res1.status_code, 201, f"Unexpected failure creating order: {res1.text}"
        )
        self.assertEqual(res2.status_code, 400)
        self.assertIn("Recurring order already exists", res2.text)

    def test_user_not_found_returns_404(self):
        user_id = self.generate_user_id("nonexistent-user")
        res = self.post_order(
            user_id,
            build_order_payload(CryptoType.BTC, Frequency.DAILY, Decimal("10.00")),
        )
        self.assertEqual(res.status_code, 404)
        self.assertIn("User not found", res.text)

    def test_get_returns_empty_list_for_new_user(self):
        user_id = self.generate_user_id("no-orders-user")
        self.create_user(user_id)
        res = self.client.get(self.url_for(user_id))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), [])


# --- Behavior and Fuzz Testing ---
class TestRecurringOrderBehavior(BaseRecurringOrderTest):

    @given(data=order_input())
    @settings(max_examples=10)
    def test_create_and_get_recurring_order(self, data):
        user_id = self.generate_user_id("hypo")
        self.create_user(user_id)
        payload = build_order_payload(data["crypto"], data["frequency"], data["amount"])
        res = self.post_order(user_id, payload)
        self.assertEqual(res.status_code, 201, f"Failed to create order: {res.text}")

        res = self.client.get(self.url_for(user_id))
        self.assertEqual(res.status_code, 200, f"Failed to retrieve order: {res.text}")
        orders = [OrderResponse(**o) for o in res.json()]
        self.assertTrue(
            any(
                o.crypto == data["crypto"]
                and o.frequency == data["frequency"]
                and Decimal(str(o.amount)) == round(data["amount"], 2)
                for o in orders
            ),
            f"Expected order not found in result: {res.json()}",
        )

    def test_user_can_create_multiple_unique_orders(self):
        user_id = self.generate_user_id("multi-combo-user")
        self.create_user(user_id)
        payloads = [
            build_order_payload(CryptoType.BTC, Frequency.DAILY, Decimal("10.00")),
            build_order_payload(CryptoType.ETH, Frequency.BI_MONTHLY, Decimal("15.00")),
        ]
        for payload in payloads:
            res = self.post_order(user_id, payload)
            self.assertEqual(res.status_code, 201, f"Failed to post: {payload}")

        res = self.client.get(self.url_for(user_id))
        orders = [OrderResponse(**o) for o in res.json()]
        self.assertEqual(len(orders), 2)

    @given(
        invalid_crypto=text(min_size=1).filter(lambda x: x not in VALID_CRYPTOS),
    )
    def test_invalid_crypto_generated(
        self, invalid_crypto
    ):
        user_id = self.generate_user_id("bad-crypto")
        self.create_user(user_id)
        res = self.post_order(
            user_id,
            build_order_payload(invalid_crypto, Frequency.DAILY, Decimal("10.00")),
        )
        self.assertEqual(res.status_code, 422)

    @given(
        invalid_frequency=text(min_size=1).filter(lambda x: x not in VALID_FREQUENCIES),
    )
    def test_invalid_frequency_generated(
        self, invalid_frequency
    ):
        user_id = self.generate_user_id("bad-frequency")
        self.create_user(user_id)
        res = self.post_order(
            user_id,
            build_order_payload(CryptoType.BTC, invalid_frequency, Decimal("10.00")),
        )
        self.assertEqual(res.status_code, 422)

    @given(
        bad_amount=decimals(max_value=Decimal("0.00"), allow_nan=False),
    )
    def test_invalid_amount_rejected_generated(
        self, bad_amount
    ):
        user_id = self.generate_user_id("bad-amount")
        self.create_user(user_id)
        res = self.post_order(
            user_id, build_order_payload(CryptoType.BTC, Frequency.DAILY, bad_amount)
        )
        self.assertEqual(res.status_code, 422)


# --- Positive Test Cases ---
class TestRecurringOrderPositive(BaseRecurringOrderTest):

    def test_create_btc_daily_order(self):
        user_id = self.generate_user_id("positive-user-1")
        self.create_user(user_id)
        payload = build_order_payload(
            CryptoType.BTC, Frequency.DAILY, Decimal("100.00")
        )
        res = self.post_order(user_id, payload)
        self.assertEqual(res.status_code, 201)
        self.assertIn("crypto", res.json())
        self.assertEqual(res.json()["crypto"], CryptoType.BTC.value)

    def test_create_eth_bi_monthly_order(self):
        user_id = self.generate_user_id("positive-user-2")
        self.create_user(user_id)
        payload = build_order_payload(
            CryptoType.ETH, Frequency.BI_MONTHLY, Decimal("150.00")
        )
        res = self.post_order(user_id, payload)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["crypto"], CryptoType.ETH.value)

    def test_retrieve_created_orders(self):
        user_id = self.generate_user_id("positive-user-3")
        self.create_user(user_id)
        payloads = [
            build_order_payload(CryptoType.BTC, Frequency.DAILY, Decimal("10.00")),
            build_order_payload(CryptoType.ETH, Frequency.BI_MONTHLY, Decimal("25.00")),
        ]
        for payload in payloads:
            res = self.post_order(user_id, payload)
            self.assertEqual(res.status_code, 201)

        res = self.client.get(self.url_for(user_id))
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data), 2)
        self.assertSetEqual(
            {o["crypto"] for o in data}, {CryptoType.BTC.value, CryptoType.ETH.value}
        )


class TestRecurringOrderEdgeCases(BaseRecurringOrderTest):

    def test_missing_field_rejected(self):
        for missing_field in ["crypto", "frequency", "amount"]:
            with self.subTest(missing_field=missing_field):
                user_id = self.generate_user_id(f"missing-field-{missing_field}")
                self.create_user(user_id)
                base = {
                    "crypto": CryptoType.BTC.value,
                    "frequency": Frequency.DAILY.value,
                    "amount": "10.00",
                }
                del base[missing_field]
                res = self.post_order(user_id, base)
                self.assertEqual(res.status_code, 422)

    def test_multiple_get_requests_idempotent(self):
        user_id = self.generate_user_id("get-idempotent")
        self.create_user(user_id)
        payload = build_order_payload(CryptoType.BTC, Frequency.DAILY, Decimal("10.00"))
        self.post_order(user_id, payload)
        for _ in range(3):
            res = self.client.get(self.url_for(user_id))
            self.assertEqual(res.status_code, 200)
            self.assertEqual(len(res.json()), 1)

    def test_duplicate_order_with_casing_variation(self):
        user_id = self.generate_user_id("case-dup-check")
        self.create_user(user_id)
        self.post_order(
            user_id,
            build_order_payload(CryptoType.BTC, Frequency.DAILY, Decimal("10.00")),
        )
        res = self.post_order(
            user_id,
            build_order_payload("btc", "daily", Decimal("20.00")),
        )
        self.assertEqual(res.status_code, 400)
