from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from uuid import uuid4


class AIConfigError(ValueError):
    pass


class AIGatewayConnectionError(RuntimeError):
    pass


API_PROTOCOLS = frozenset({"chat_completions", "responses"})
SYSTEM_PROMPT = (
    "你是专业的小红书内容编辑。请使用自然、具体的中文，保留输入中的事实，"
    "不要编造未提供的体验、数据或承诺。输出可以直接编辑使用的正文，不要解释创作过程。"
)


def normalize_base_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise AIConfigError("中转 Base URL 必须是有效的 HTTP 或 HTTPS 地址")
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, parsed.path.rstrip("/"), "", "")
    )


class AIConfigStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()

    def public_config(self) -> dict:
        with self._lock:
            return self._public(self._read())

    def update(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        clear_api_key: bool = False,
        protocol: str = "responses",
        image_model: str = "",
    ) -> dict:
        normalized_url = normalize_base_url(base_url)
        normalized_model = model.strip()
        normalized_protocol = protocol.strip().lower()
        if normalized_protocol not in API_PROTOCOLS:
            raise AIConfigError("API 协议必须是 Responses 或 Chat Completions")
        with self._lock:
            config = self._read()
            config["base_url"] = normalized_url
            config["model"] = normalized_model
            config["protocol"] = normalized_protocol
            config["image_model"] = image_model.strip()
            if clear_api_key:
                config["api_key"] = ""
            elif api_key.strip():
                config["api_key"] = api_key.strip()
            self._write(config)
            return self._public(config)

    def connection_config(self) -> dict:
        with self._lock:
            config = self._read()
        if not config["base_url"] or not config["api_key"]:
            raise AIConfigError("请先配置中转 Base URL 和 API Key")
        return config

    def _read(self) -> dict[str, str]:
        default = {
            "base_url": "",
            "api_key": "",
            "model": "",
            "image_model": "",
            "protocol": "responses",
        }
        if not self.path.is_file():
            return default
        try:
            with self.path.open("r", encoding="utf-8") as config_file:
                stored = json.load(config_file)
        except (OSError, json.JSONDecodeError):
            return default
        return {key: str(stored.get(key, default[key])).strip() for key in default}

    def _write(self, config: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f".{self.path.stem}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            json.dump(config, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary_path = Path(temporary.name)
        temporary_path.replace(self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @staticmethod
    def _public(config: dict[str, str]) -> dict:
        base_url = config["base_url"]
        key_configured = bool(config["api_key"])
        protocol = config["protocol"]
        endpoint = "responses" if protocol == "responses" else "chat/completions"
        return {
            "base_url": base_url,
            "model": config["model"],
            "image_model": config["image_model"],
            "protocol": protocol,
            "api_key_configured": key_configured,
            "configured": bool(base_url and key_configured and config["model"]),
            "image_configured": bool(
                base_url and key_configured and config["image_model"]
            ),
            "models_url": f"{base_url}/models" if base_url else "",
            "request_url": f"{base_url}/{endpoint}" if base_url else "",
            "image_request_url": (f"{base_url}/images/generations" if base_url else ""),
        }


class AIGateway:
    def __init__(
        self,
        store: AIConfigStore,
        timeout: float = 10,
        generation_timeout: float = 120,
    ) -> None:
        self.store = store
        self.timeout = timeout
        self.generation_timeout = generation_timeout

    def public_config(self) -> dict:
        return self.store.public_config()

    def configure(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        clear_api_key: bool = False,
        protocol: str = "responses",
        image_model: str = "",
    ) -> dict:
        return self.store.update(
            base_url,
            model,
            api_key,
            clear_api_key,
            protocol,
            image_model,
        )

    def test_connection(self) -> dict:
        config = self.store.connection_config()
        models_url = f"{config['base_url']}/models"
        request = Request(
            models_url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {config['api_key']}",
                "User-Agent": "XHS-Downloader-Web/2.8",
            },
            method="GET",
        )
        started = perf_counter()
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = response.read(2 * 1024 * 1024 + 1)
        except HTTPError as error:
            raise AIGatewayConnectionError(f"中转服务返回 HTTP {error.code}") from error
        except URLError as error:
            raise AIGatewayConnectionError(
                f"无法连接中转服务：{error.reason}"
            ) from error
        except TimeoutError as error:
            raise AIGatewayConnectionError("连接中转服务超时") from error

        if len(body) > 2 * 1024 * 1024:
            raise AIGatewayConnectionError("中转服务响应过大")
        try:
            payload = json.loads(body)
            models = payload["data"]
            if not isinstance(models, list):
                raise TypeError
            model_ids = {
                str(item["id"])
                for item in models
                if isinstance(item, dict) and item.get("id")
            }
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise AIGatewayConnectionError(
                "中转服务响应不符合 OpenAI /models 格式"
            ) from error

        configured_model = config["model"]
        configured_image_model = config["image_model"]
        return {
            "ok": True,
            "latency_ms": round((perf_counter() - started) * 1000),
            "models_count": len(model_ids),
            "model_available": (
                configured_model in model_ids if configured_model else None
            ),
            "image_model_available": (
                configured_image_model in model_ids if configured_image_model else None
            ),
        }

    def generate(
        self,
        source_text: str,
        instructions: str,
        mode: str,
        images: list[tuple[str, bytes]],
    ) -> dict:
        config = self.store.connection_config()
        if not config["model"]:
            raise AIConfigError("请先配置默认模型")

        user_text = self._user_prompt(source_text, instructions, mode)
        data_urls = [
            f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
            for mime_type, data in images
        ]
        if config["protocol"] == "responses":
            payload = self._responses_payload(config["model"], user_text, data_urls)
            endpoint = "responses"
        else:
            payload = self._chat_payload(config["model"], user_text, data_urls)
            endpoint = "chat/completions"

        response = self._post_json(
            f"{config['base_url']}/{endpoint}",
            config["api_key"],
            payload,
        )
        text = self._extract_output_text(response)
        if not text:
            raise AIGatewayConnectionError("AI 中转返回了空内容")
        return {
            "text": text,
            "model": config["model"],
            "protocol": config["protocol"],
            "images_used": len(images),
        }

    def generate_image(
        self,
        source_text: str,
        instructions: str,
        images: list[tuple[str, bytes]],
        size: str,
        quality: str,
    ) -> dict:
        config = self.store.connection_config()
        if not config["image_model"]:
            raise AIConfigError("请先配置图片模型")
        prompt = self._image_prompt(source_text, instructions, bool(images))
        fields = {
            "model": config["image_model"],
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "n": "1",
        }
        if images:
            response = self._post_multipart(
                f"{config['base_url']}/images/edits",
                config["api_key"],
                fields,
                images,
            )
        else:
            response = self._post_json(
                f"{config['base_url']}/images/generations",
                config["api_key"],
                {**fields, "n": 1},
                max_response_bytes=50 * 1024 * 1024,
            )
        image_data, revised_prompt = self._extract_generated_image(response)
        return {
            "data": image_data,
            "model": config["image_model"],
            "revised_prompt": revised_prompt,
            "references_used": len(images),
        }

    def _post_json(
        self,
        url: str,
        api_key: str,
        payload: dict,
        max_response_bytes: int = 8 * 1024 * 1024,
    ) -> dict:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "XHS-Downloader-Web/2.8",
            },
            method="POST",
        )
        return self._read_json_response(request, max_response_bytes)

    def _post_multipart(
        self,
        url: str,
        api_key: str,
        fields: dict[str, str],
        images: list[tuple[str, bytes]],
    ) -> dict:
        boundary = f"----XHSDownloader{uuid4().hex}"
        body = bytearray()
        for name, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            )
            body.extend(str(value).encode("utf-8"))
            body.extend(b"\r\n")
        extensions = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }
        for index, (mime_type, data) in enumerate(images, start=1):
            extension = extensions.get(mime_type, "png")
            body.extend(f"--{boundary}\r\n".encode())
            body.extend(
                (
                    'Content-Disposition: form-data; name="image[]"; '
                    f'filename="reference-{index}.{extension}"\r\n'
                ).encode()
            )
            body.extend(f"Content-Type: {mime_type}\r\n\r\n".encode())
            body.extend(data)
            body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())
        request = Request(
            url,
            data=bytes(body),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "XHS-Downloader-Web/2.8",
            },
            method="POST",
        )
        return self._read_json_response(request, 50 * 1024 * 1024)

    def _read_json_response(self, request: Request, max_bytes: int) -> dict:
        try:
            with urlopen(request, timeout=self.generation_timeout) as response:
                body = response.read(max_bytes + 1)
        except HTTPError as error:
            raise AIGatewayConnectionError(f"AI 中转返回 HTTP {error.code}") from error
        except URLError as error:
            raise AIGatewayConnectionError(
                f"无法连接 AI 中转：{error.reason}"
            ) from error
        except TimeoutError as error:
            raise AIGatewayConnectionError("AI 生成请求超时") from error
        if len(body) > max_bytes:
            raise AIGatewayConnectionError("AI 中转响应过大")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as error:
            raise AIGatewayConnectionError("AI 中转返回的不是 JSON") from error
        if not isinstance(parsed, dict):
            raise AIGatewayConnectionError("AI 中转响应格式错误")
        return parsed

    @staticmethod
    def _image_prompt(source_text: str, instructions: str, has_references: bool) -> str:
        parts = [source_text.strip() or "根据参考图片创作一张小红书配图"]
        if instructions.strip():
            parts.append(instructions.strip())
        if has_references:
            parts.append("参考随附图片中的主体、造型和视觉元素，重新构图并生成新图片。")
        parts.append("画面完整清晰，不添加水印、平台标识或无关文字。")
        return "\n\n".join(parts)

    @staticmethod
    def _extract_generated_image(payload: dict) -> tuple[bytes, str]:
        items = payload.get("data")
        if not isinstance(items, list) or not items or not isinstance(items[0], dict):
            raise AIGatewayConnectionError("图片接口没有返回图片数据")
        item = items[0]
        encoded = item.get("b64_json")
        if not isinstance(encoded, str) or not encoded:
            raise AIGatewayConnectionError("图片接口未返回 Base64 图片")
        try:
            image_data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as error:
            raise AIGatewayConnectionError("图片接口返回的 Base64 数据无效") from error
        if not image_data or len(image_data) > 32 * 1024 * 1024:
            raise AIGatewayConnectionError("图片接口返回的图片大小无效")
        revised_prompt = item.get("revised_prompt", "")
        return image_data, revised_prompt if isinstance(revised_prompt, str) else ""

    @staticmethod
    def _user_prompt(source_text: str, instructions: str, mode: str) -> str:
        action = (
            "在保留事实和核心信息的前提下改写" if mode == "rewrite" else "根据素材创作"
        )
        parts = [f"任务：{action}一篇小红书正文。"]
        if source_text.strip():
            parts.append(f"原始内容或主题：\n{source_text.strip()}")
        if instructions.strip():
            parts.append(f"补充要求：\n{instructions.strip()}")
        if not source_text.strip():
            parts.append("请根据随附图片提炼真实可见的信息。")
        return "\n\n".join(parts)

    @staticmethod
    def _responses_payload(model: str, text: str, data_urls: list[str]) -> dict:
        content = [{"type": "input_text", "text": text}]
        content.extend(
            {"type": "input_image", "image_url": image_url} for image_url in data_urls
        )
        return {
            "model": model,
            "instructions": SYSTEM_PROMPT,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": 2000,
        }

    @staticmethod
    def _chat_payload(model: str, text: str, data_urls: list[str]) -> dict:
        content = [{"type": "text", "text": text}]
        content.extend(
            {"type": "image_url", "image_url": {"url": image_url}}
            for image_url in data_urls
        )
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            "max_tokens": 2000,
        }

    @staticmethod
    def _extract_output_text(payload: dict) -> str:
        if isinstance(payload.get("output_text"), str):
            return payload["output_text"].strip()
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            content = choices[0].get("message", {}).get("content", "")
            if isinstance(content, str):
                return content.strip()
        texts = []
        for output in payload.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if not isinstance(content, dict):
                    continue
                text = content.get("text")
                if isinstance(text, str) and content.get("type") in {
                    "output_text",
                    "text",
                }:
                    texts.append(text.strip())
        return "\n".join(text for text in texts if text)
