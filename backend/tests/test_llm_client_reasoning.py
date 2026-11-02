"""LLMClient: `reasoning_effort` de la conexión (Config) viaja al proveedor; sin él no se envía."""
from unittest.mock import patch

import httpx

from infrastructure.external_apis.llm_client import LLMClient


def _resp(payloads: list):
    def post(url, json, headers, timeout):
        payloads.append(json)
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]},
                              request=httpx.Request("POST", url))
    return post


def test_reasoning_effort_de_config_se_envia():
    enviados: list = []
    with patch("infrastructure.external_apis.llm_client.httpx.post", _resp(enviados)):
        LLMClient({"base_url": "http://x/v1", "model": "qwen3.5-64k", "reasoning_effort": "none"}).chat([{"role": "user", "content": "hola"}])
    assert enviados[0]["reasoning_effort"] == "none"


def test_sin_reasoning_effort_no_se_envia():
    enviados: list = []
    with patch("infrastructure.external_apis.llm_client.httpx.post", _resp(enviados)):
        LLMClient({"base_url": "http://x/v1", "model": "m"}).chat([{"role": "user", "content": "hola"}])
    assert "reasoning_effort" not in enviados[0]
