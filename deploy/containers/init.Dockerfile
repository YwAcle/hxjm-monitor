FROM python:3.10.16-slim-bookworm
COPY deploy/containers/init.lock /opt/requirements.lock
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --timeout 120 --retries 5 -i "$PIP_INDEX_URL" -r /opt/requirements.lock && pip check
COPY deploy/init /opt/init
ENTRYPOINT []
CMD ["python", "/opt/init/bootstrap.py", "check"]
