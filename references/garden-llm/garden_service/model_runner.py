#!/usr/bin/env python3
"""Model loading and single-frame inference for Garden.

This module owns everything directly tied to the multimodal model: processor
setup, prompt handoff, token streaming, and final alert parsing. It should not
manage sockets, sessions, or HTTP routes.
"""

import json
import sys
import threading
from typing import Dict, Optional, Tuple

import torch
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration, TextIteratorStreamer

from garden_config import resolve_torch_dtype
from image_utils import decode_image_from_meta
from prompting import (
    GardenPromptTemplate,
    normalize_stream_name,
    parse_model_json,
    should_alert_from_text,
)


def log(message: str) -> None:
    """Emit a shared service log prefix across split modules."""
    print(f"[GardenService] {message}", flush=True)

# 模型推理执行器 调用 Qwen3-VL 模型进行检测
class GardenModelRunner:
    """Wrap one loaded model instance and the prompt template it consumes."""

    def __init__(self, model_path: str, prompt_template_path: str, device_name: str):
        self.model_path = model_path
        self.prompt_template = GardenPromptTemplate(prompt_template_path)
        self.torch_dtype = resolve_torch_dtype(torch)
        self.device_name = device_name
        self.device = torch.device(device_name)

        log(
            f"loading model from {model_path} "
            f"(dtype={self.torch_dtype}, device={self.device})"
        )
        processor_kwargs = {"trust_remote_code": True}
        try:
            processor_kwargs["fix_mistral_regex"] = True
            self.processor = AutoProcessor.from_pretrained(
                model_path,
                **processor_kwargs,
            )
        except TypeError:
            processor_kwargs.pop("fix_mistral_regex", None)
            self.processor = AutoProcessor.from_pretrained(
                model_path,
                **processor_kwargs,
            )

        model_kwargs = {
            "torch_dtype": self.torch_dtype,
            "trust_remote_code": True,
            "low_cpu_mem_usage": False,
        }
        self.model = Qwen3VLForConditionalGeneration.from_pretrained(
            model_path,
            **model_kwargs,
        )
        self.model.to(self.device)
        self.model.eval()
        log("model loaded")

    def _model_device(self) -> torch.device:
        return self.device

    def infer(self, meta: dict) -> Tuple[str, bool, Optional[Dict], object]:
        """Run one frame through the model and return both raw and parsed output."""
        image = decode_image_from_meta(meta)
        self.prompt_template.reload()
        messages = self.prompt_template.build_messages(meta, image)
        prompt_text = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = self.processor(
            text=[prompt_text],
            images=[image],
            padding=True,
            return_tensors="pt",
        )
        model_device = self._model_device()
        inputs = {
            key: value.to(model_device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }

        # Some processors expose a tokenizer attribute while others already act
        # as one, so we normalize that lookup here.
        tokenizer = getattr(self.processor, "tokenizer", self.processor)
        streamer = TextIteratorStreamer(
            tokenizer,
            skip_prompt=True,
            skip_special_tokens=True,
        )

        generation_kwargs = dict(inputs)
        generation_kwargs.update(self.prompt_template.generation)
        generation_kwargs["streamer"] = streamer

        # Run generation in a background thread so we can stream partial tokens
        # and print alerts before the full response completes.
        worker = threading.Thread(
            target=self.model.generate,
            kwargs=generation_kwargs,
            daemon=True,
        )

        full_text = ""
        alert_printed = False
        stream_name = normalize_stream_name(meta)
        frame_ts = meta.get("timestamp", "")

        worker.start()
        for chunk in streamer:
            full_text += chunk
            if not alert_printed and should_alert_from_text(
                full_text, self.prompt_template.alert_predicates
            ):
                alert_printed = True
                print(
                    f"\n[GardenAlert] stream={stream_name} timestamp={frame_ts}",
                    flush=True,
                )
                sys.stdout.write(full_text)
                sys.stdout.flush()
            elif alert_printed:
                sys.stdout.write(chunk)
                sys.stdout.flush()

        worker.join()
        if alert_printed and not full_text.endswith("\n"):
            sys.stdout.write("\n")
            sys.stdout.flush()

        # Prefer structured JSON when available, but keep a text-based fallback
        # so alerting can still function if the model drifts from the template.
        parsed = parse_model_json(full_text)
        if parsed is not None:
            has_garbage = bool(parsed.get("has_garbage"))
            status = str(parsed.get("status", "")).upper()
            final_alert = has_garbage or status == "ALERT"
            if final_alert and not alert_printed:
                print(
                    f"\n[GardenAlert] stream={stream_name} timestamp={frame_ts}",
                    flush=True,
                )
                print(json.dumps(parsed, ensure_ascii=False), flush=True)
            return full_text, final_alert, parsed, image

        final_alert = should_alert_from_text(
            full_text, self.prompt_template.alert_predicates
        )
        if final_alert and not alert_printed:
            print(
                f"\n[GardenAlert] stream={stream_name} timestamp={frame_ts}",
                flush=True,
            )
            print(full_text.strip(), flush=True)
        return full_text, final_alert, None, image
