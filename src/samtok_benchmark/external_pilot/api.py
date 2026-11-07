"""Bounded, resumable paid scoring; no editor use and no unknown-answer resampling."""

import base64
import json
import mimetypes
from pathlib import Path
import uuid

from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import digest

MODEL = "gpt-5.4-2026-03-05"


def image_part(path):
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{encoded}", "detail": "high"}}


def create_client(key_file):
    from openai import AzureOpenAI
    return AzureOpenAI(api_key=Path(key_file).read_text().strip(), api_version="2024-02-01",
                       azure_endpoint="https://aidp-i18ntt-sg.byteintl.net/api/modelhub/online/v2/crawl",
                       timeout=240, max_retries=0)


def call(client, directory, messages, identity, **parameters):
    directory = Path(directory)
    params = {"model": MODEL, "max_tokens": 8192, "stream": False, **parameters}
    binding = {**identity, "messages_sha256": digest(messages), "parameters": params}
    if (directory / "admitted.json").exists():
        if read(directory / "admitted.json")["identity"] != binding:
            raise ValueError("Paid call input changed")
        if not (directory / "response.json").exists():
            raise RuntimeError("Previously admitted call has no response; not resubmitted")
        response = read(directory / "response.json")
    else:
        directory.mkdir(parents=True, exist_ok=True)
        logid = uuid.uuid4().hex
        with (directory / "admitted.json").open("x") as out:
            json.dump({"identity": binding, "logid": logid}, out, indent=2)
        try:
            response = client.chat.completions.create(messages=messages, **params,
                        extra_headers={"X-TT-LOGID": logid}).model_dump(mode="json")
            immutable(directory / "response.json", response)
        except Exception as error:
            immutable(directory / "error.json", {"error": str(error), "type": type(error).__name__})
            raise
    if any(x["finish_reason"] != "stop" for x in response["choices"]):
        raise ValueError("Judge response did not finish normally")
    return response


def json_answer(text):
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)
