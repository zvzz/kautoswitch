"""API client — sends correction requests to a local API endpoint."""
import logging
import os
from typing import Optional, List
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Load prompt template
_PROMPT_PATH = Path(__file__).parent / "resources" / "tinyllm_prompt.md"
_PROMPT_TEMPLATE = ""
if _PROMPT_PATH.exists():
    _PROMPT_TEMPLATE = _PROMPT_PATH.read_text(encoding="utf-8")


class APIClient:
    """Client for optional local API correction endpoint."""

    def __init__(self, url: str, timeout_ms: int = 100, model: str = ""):
        self.url = url
        self.timeout_sec = timeout_ms / 1000.0
        self.model = model  # selected model ID

    @property
    def base_url(self) -> str:
        """Derive the API base URL from the correction endpoint URL.

        e.g. http://localhost:8080/v1/correct → http://localhost:8080
        """
        url = self.url.rstrip('/')
        # Strip known path suffixes to find base
        for suffix in ('/v1/correct', '/correct', '/v1/completions', '/completions'):
            if url.endswith(suffix):
                return url[:-len(suffix)]
        # Fallback: strip last path component
        parts = url.rsplit('/', 1)
        return parts[0] if len(parts) > 1 else url

    def fetch_models(self) -> List[dict]:
        """Fetch available models from the API.

        Queries GET /v1/models (OpenAI-compatible endpoint).

        Returns list of dicts with at least 'id' key, e.g.:
            [{"id": "model-name", "object": "model"}, ...]

        Returns empty list on failure.
        """
        base = self.base_url
        models_url = f"{base}/v1/models"

        try:
            resp = requests.get(models_url, timeout=max(self.timeout_sec, 3.0))
            resp.raise_for_status()
            data = resp.json()

            # OpenAI-compatible: {"data": [{"id": "...", ...}, ...]}
            if isinstance(data, dict) and 'data' in data:
                models = data['data']
                if isinstance(models, list):
                    return [m for m in models if isinstance(m, dict) and 'id' in m]

            # Alternative: plain list of model objects
            if isinstance(data, list):
                return [m for m in data if isinstance(m, dict) and 'id' in m]

            # Alternative: {"models": [...]}
            if isinstance(data, dict) and 'models' in data:
                models = data['models']
                if isinstance(models, list):
                    result = []
                    for m in models:
                        if isinstance(m, str):
                            result.append({"id": m})
                        elif isinstance(m, dict) and 'id' in m:
                            result.append(m)
                        elif isinstance(m, dict) and 'name' in m:
                            result.append({"id": m['name']})
                    return result

            logger.debug("Unexpected models response format: %s", type(data))
            return []

        except requests.Timeout:
            logger.debug("API models request timed out at %s", models_url)
        except requests.ConnectionError:
            logger.debug("API models connection error — is the server running? URL: %s", models_url)
        except Exception as e:
            logger.debug("API models error: %s", e)

        return []

    def correct(self, text: str, context: str = "") -> Optional[str]:
        """Send correction request to local API.

        Expected API: POST with JSON body, returns JSON with corrected text.
        Follows the tinyllm_prompt.md format.
        """
        prompt = _PROMPT_TEMPLATE + f"\n<RAW_INPUT>\n{text}\n</RAW_INPUT>\n"

        payload = {
            "prompt": prompt,
            "text": text,
            "context": context,
            "max_tokens": len(text) * 2,
            "temperature": 0.0,
        }
        if self.model:
            payload["model"] = self.model

        try:
            resp = requests.post(
                self.url,
                json=payload,
                timeout=self.timeout_sec,
            )
            resp.raise_for_status()
            data = resp.json()

            # Try to extract corrected text from response
            result = self._extract_result(data)
            if result and result.strip():
                return result.strip()

        except requests.Timeout:
            logger.debug("API timeout for: %r", text)
        except requests.ConnectionError:
            logger.debug("API connection error — is the local server running?")
        except Exception as e:
            logger.debug("API error: %s", e)

        return None

    @staticmethod
    def _extract_result(data: dict) -> Optional[str]:
        """Extract corrected text from API response.

        Supports multiple response formats:
        - {"output": "..."}
        - {"text": "..."}
        - {"result": "..."}
        - {"choices": [{"text": "..."}]}
        - {"completion": "..."}
        """
        if isinstance(data, str):
            return data

        for key in ("output", "text", "result", "completion", "corrected"):
            if key in data:
                val = data[key]
                if isinstance(val, str):
                    # Try to extract from <OUTPUT> tags
                    return APIClient._extract_output_tags(val)

        if "choices" in data and isinstance(data["choices"], list):
            for choice in data["choices"]:
                if isinstance(choice, dict):
                    for key in ("text", "message", "content"):
                        if key in choice:
                            val = choice[key]
                            if isinstance(val, dict):
                                val = val.get("content", "")
                            if isinstance(val, str):
                                return APIClient._extract_output_tags(val)

        return None

    @staticmethod
    def _extract_output_tags(text: str) -> str:
        """Extract text between <OUTPUT> tags if present."""
        if "<OUTPUT>" in text and "</OUTPUT>" in text:
            start = text.index("<OUTPUT>") + len("<OUTPUT>")
            end = text.index("</OUTPUT>")
            return text[start:end].strip()
        return text.strip()
