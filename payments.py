"""Authenticated WeChat Pay v3 / Alipay RSA2 notification boundaries.

Checkout stays disabled until the merchant integration is configured and
validated. No browser redirect or client-supplied payment status grants credit.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from time import time
from urllib.parse import parse_qsl
from fastapi import Request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from billing import BillingError


class PaymentError(ValueError):
    pass


@dataclass(frozen=True)
class VerifiedPayment:
    order_id: str
    provider: str
    transaction_id: str
    amount_cents: int
    currency: str = "CNY"

    def settle(self, billing):
        return billing.settle_verified_order(**self.__dict__)


def verify_signature(public_key, content, signature):
    try:
        serialization.load_pem_public_key(public_key).verify(
            base64.b64decode(signature, validate=True),
            content,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (InvalidSignature, ValueError, TypeError) as error:
        raise PaymentError("支付通知签名无效") from error


class WechatVerifier:
    def __init__(
        self,
        *,
        app_id: str,
        merchant_id: str,
        api_v3_key: bytes,
        public_keys: dict[str, bytes],
    ):
        if not app_id or not merchant_id or len(api_v3_key) != 32 or not public_keys:
            raise PaymentError("微信支付验签配置不完整")
        self.app_id, self.merchant_id = app_id, merchant_id
        self.api_v3_key, self.public_keys = api_v3_key, public_keys

    def verify(self, body: bytes, headers: dict, *, now=None):
        try:
            headers = {key.lower(): value for key, value in headers.items()}
            timestamp, nonce = (
                headers["wechatpay-timestamp"],
                headers["wechatpay-nonce"],
            )
            if abs(int(time() if now is None else now) - int(timestamp)) > 300:
                raise PaymentError("支付通知已过期")
            key = self.public_keys.get(headers["wechatpay-serial"])
            if key is None:
                raise PaymentError("微信支付验签密钥标识不匹配")
            verify_signature(
                key,
                timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body + b"\n",
                headers["wechatpay-signature"],
            )
            event = json.loads(body)
            if event["event_type"] != "TRANSACTION.SUCCESS":
                raise PaymentError("支付通知尚未完成付款")
            resource = event["resource"]
            if resource["algorithm"] != "AEAD_AES_256_GCM":
                raise PaymentError("支付通知加密算法不匹配")
            payload = json.loads(
                AESGCM(self.api_v3_key).decrypt(
                    resource["nonce"].encode(),
                    base64.b64decode(resource["ciphertext"], validate=True),
                    resource.get("associated_data", "").encode(),
                )
            )
            if (
                payload["appid"] != self.app_id
                or payload["mchid"] != self.merchant_id
                or payload["trade_state"] != "SUCCESS"
            ):
                raise PaymentError("支付商户、应用或状态不匹配")
            amount = payload["amount"]["total"]
            if (
                type(amount) is not int
                or amount <= 0
                or payload["amount"]["currency"] != "CNY"
            ):
                raise PaymentError("支付金额或币种不匹配")
            return VerifiedPayment(
                payload["out_trade_no"], "wechat", payload["transaction_id"], amount
            )
        except PaymentError:
            raise
        except Exception as error:
            raise PaymentError("微信支付通知格式或加密内容无效") from error


class AlipayVerifier:
    def __init__(self, *, app_id: str, seller_id: str, public_key: bytes):
        if not app_id or not seller_id or not public_key:
            raise PaymentError("支付宝验签配置不完整")
        self.app_id, self.seller_id, self.public_key = app_id, seller_id, public_key

    def verify(self, body: bytes):
        try:
            pairs = parse_qsl(
                body.decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=True,
                max_num_fields=100,
            )
            payload = dict(pairs)
            if len(payload) != len(pairs) or payload.get("sign_type") != "RSA2":
                raise PaymentError("支付宝通知参数或签名类型无效")
            content = "&".join(
                f"{key}={payload[key]}"
                for key in sorted(payload)
                if key not in {"sign", "sign_type"} and payload[key] != ""
            )
            verify_signature(self.public_key, content.encode("utf-8"), payload["sign"])
            if (
                payload["app_id"] != self.app_id
                or payload["seller_id"] != self.seller_id
            ):
                raise PaymentError("支付商户或应用不匹配")
            if payload["trade_status"] not in {"TRADE_SUCCESS", "TRADE_FINISHED"}:
                raise PaymentError("支付通知尚未完成付款")
            amount = Decimal(payload["total_amount"]) * 100
            if (
                not amount.is_finite()
                or amount <= 0
                or amount != amount.to_integral_value()
            ):
                raise PaymentError("支付金额无效")
            return VerifiedPayment(
                payload["out_trade_no"], "alipay", payload["trade_no"], int(amount)
            )
        except PaymentError:
            raise
        except (KeyError, ValueError, InvalidOperation, UnicodeError) as error:
            raise PaymentError("支付宝支付通知格式无效") from error


def load_payment_verifiers(config_path: Path) -> dict:
    """Private server file; supports multiple pinned WeChat keys for rotation."""
    config = json.loads(config_path.read_text(encoding="utf-8"))
    verifiers = {}

    def key_file(name):
        path = (config_path.parent / name).resolve()
        if not path.is_relative_to(config_path.parent.resolve()):
            raise PaymentError("验签密钥需要放在支付配置目录内")
        return path.read_bytes()

    if "wechat" in config:
        item = config["wechat"]
        verifiers["wechat"] = WechatVerifier(
            app_id=item["app_id"],
            merchant_id=item["merchant_id"],
            api_v3_key=item["api_v3_key"].encode(),
            public_keys={
                serial: key_file(name) for serial, name in item["public_keys"].items()
            },
        )
    if "alipay" in config:
        item = config["alipay"]
        verifiers["alipay"] = AlipayVerifier(
            app_id=item["app_id"],
            seller_id=item["seller_id"],
            public_key=key_file(item["public_key"]),
        )
    return verifiers


def register_payment_callbacks(app, billing, *, wechat=None, alipay=None):
    """Register only explicitly configured verifiers; checkout is independent."""
    from fastapi.responses import JSONResponse, PlainTextResponse

    async def bounded_body(request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                raise PaymentError("支付通知过大")
        return bytes(body)

    @app.post("/api/payments/callback/wechat")
    async def wechat_callback(request: Request):
        if wechat is None:
            return JSONResponse(
                {"code": "FAIL", "message": "支付渠道未启用"}, status_code=503
            )
        try:
            event = wechat.verify(await bounded_body(request), dict(request.headers))
            event.settle(billing)
        except (PaymentError, BillingError):
            return JSONResponse(
                {"code": "FAIL", "message": "支付通知校验失败"}, status_code=400
            )
        return JSONResponse({"code": "SUCCESS", "message": "成功"})

    @app.post("/api/payments/callback/alipay")
    async def alipay_callback(request: Request):
        if alipay is None:
            return PlainTextResponse("failure", status_code=503)
        try:
            event = alipay.verify(await bounded_body(request))
            event.settle(billing)
        except (PaymentError, BillingError):
            return PlainTextResponse("failure", status_code=400)
        return PlainTextResponse("success")
