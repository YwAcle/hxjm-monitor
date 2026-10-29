from __future__ import annotations

from flask import Flask, jsonify, request
from flask_cors import CORS

from llm_chat_service.config import DbConfig, ServiceConfig
from llm_chat_service.db.chat_count_repo import inc_chat_count
from llm_chat_service.service.agent import run_chat
from llm_chat_service.service.formatter import format_with_json_block


def create_app(*, engine, db_cfg: DbConfig, svc_cfg: ServiceConfig, llm) -> Flask:
    app = Flask(__name__)
    CORS(app)

    @app.post("/chat")
    def chat():
        payload = request.get_json(silent=True) or {}
        prompt = payload.get("prompt")
        if prompt is None or str(prompt).strip() == "":
            return jsonify({"error": "missing prompt"}), 400

        try:
            inc_chat_count(engine, db_cfg.schema)
        except Exception:
            pass

        data = run_chat(
            engine=engine,
            db_cfg=db_cfg,
            svc_cfg=svc_cfg,
            llm=llm,
            prompt=str(prompt),
            person_name=payload.get("person_name"),
            time_hint=payload.get("time_hint"),
            top_k=payload.get("top_k"),
            image_bytes=None,
        )

        text = format_with_json_block(data.get("answer_text") or "", data)
        return jsonify({"text": text, "data": data})

    @app.post("/chat_with_image")
    def chat_with_image():
        prompt = request.form.get("prompt") or request.args.get("prompt")
        if prompt is None or str(prompt).strip() == "":
            return jsonify({"error": "missing prompt"}), 400

        file = request.files.get("file")
        if file is None:
            return jsonify({"error": "missing file"}), 400

        image_bytes = file.read()

        try:
            inc_chat_count(engine, db_cfg.schema)
        except Exception:
            pass

        data = run_chat(
            engine=engine,
            db_cfg=db_cfg,
            svc_cfg=svc_cfg,
            llm=llm,
            prompt=str(prompt),
            person_name=request.form.get("person_name"),
            time_hint=request.form.get("time_hint"),
            top_k=request.form.get("top_k", type=int),
            image_bytes=image_bytes,
        )

        text = format_with_json_block(data.get("answer_text") or "", data)
        return jsonify({"text": text, "data": data})

    return app
