from re import compile
from json import loads, JSONDecodeError
from typing import Union

from lxml.etree import HTML
from yaml import safe_load, YAMLError

__all__ = ["Converter"]


class Converter:
    YAML_ILLEGAL = compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    INITIAL_STATE = "//script/text()"
    ASSIGNMENT = compile(r"^\s*window\.__INITIAL_STATE__\s*=\s*")
    JS_VALUES = compile(r'("(?:\\.|[^"\\])*")|\bundefined\b|new Map\(\[\]\)')
    PC_KEYS_LINK = (
        "note",
        "noteDetailMap",
        "[-1]",
        "note",
    )
    PHONE_KEYS_LINK = (
        "noteData",
        "data",
        "noteData",
    )

    def run(self, content: str) -> dict:
        return self._filter_object(self._convert_object(self._extract_object(content)))

    def _extract_object(self, html: str) -> str:
        if not html:
            return ""
        html_tree = HTML(html)
        if html_tree is None:
            return ""
        scripts = html_tree.xpath(self.INITIAL_STATE)
        return self.get_script(scripts)

    @classmethod
    def _convert_object(cls, text: str) -> dict:
        cleaned = cls.YAML_ILLEGAL.sub("", cls.ASSIGNMENT.sub("", text)).strip().rstrip(";")
        cleaned = cls.JS_VALUES.sub(lambda match: match.group(1) or ("[]" if match.group() == "new Map([])" else "null"), cleaned)
        try:
            return loads(cleaned)
        except JSONDecodeError:
            try:
                value = safe_load(cleaned)
                return value if isinstance(value, dict) else {}
            except YAMLError:
                return {}

    @classmethod
    def _filter_object(cls, data: dict) -> dict:
        return (
            cls.deep_get(data, cls.PHONE_KEYS_LINK)
            or cls.deep_get(data, cls.PC_KEYS_LINK)
            or {}
        )

    @classmethod
    def deep_get(cls, data: dict, keys: list | tuple, default=None):
        if not data:
            return default
        try:
            for key in keys:
                if key.startswith("[") and key.endswith("]"):
                    data = cls.safe_get(data, int(key[1:-1]))
                else:
                    data = data[key]
            return data
        except (KeyError, IndexError, ValueError, TypeError):
            return default

    @staticmethod
    def safe_get(data: Union[dict, list, tuple, set], index: int):
        if isinstance(data, dict):
            return list(data.values())[index]
        elif isinstance(data, list | tuple | set):
            return data[index]
        raise TypeError

    @staticmethod
    def get_script(scripts: list) -> str:
        scripts.reverse()
        return next(
            (
                script
                for script in scripts
                if Converter.ASSIGNMENT.match(script)
            ),
            "",
        )
