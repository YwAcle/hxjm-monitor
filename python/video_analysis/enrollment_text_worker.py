"""Encode stored crops into the Chinese-CLIP text feature space.

Run this as a separate, long-lived worker next to the existing sample pipeline.
It consumes backend-owned samples (``purpose=enrollment`` by default, or
``purpose=history`` when ``ENROLLMENT_TEXT_SAMPLE_PURPOSE=history``) and never
touches live frames, queries or the CLIP-ReID image space.

Required environment:
  ENROLLMENT_TEXT_BUSINESS_URL   e.g. http://127.0.0.1:8080/api/v1/business
  ENROLLMENT_TEXT_SERVICE_ID     service credential ID
  ENROLLMENT_TEXT_SERVICE_TOKEN  service credential token
  ENROLLMENT_TEXT_INSTANCE_ID    canonical nonzero UUID of the feature capability
Optional:
  ENROLLMENT_TEXT_FEATURE_URL    default http://127.0.0.1:28024
  ENROLLMENT_TEXT_CAPABILITY_CODE default person.reidentification
  ENROLLMENT_TEXT_POLL_SECONDS   default 5
  ENROLLMENT_TEXT_TIMEOUT_SECONDS default 30
  ENROLLMENT_TEXT_SAMPLE_PURPOSE default enrollment; history encodes stored
                                 tracklet crops into the same text space so text
                                 search can rank all retained images
"""
import logging
import os
import signal
import sys
import threading
import uuid

from .business_client import BusinessClient
from .sample_pipeline import LocalSamplePipeline, TextReIDFeatureClient

LOG = logging.getLogger('enrollment-text-worker')


def _required(env, name):
    value = env.get(name, '').strip()
    if not value or 'REPLACE_WITH_' in value or any(ord(char) < 32 for char in value):
        raise ValueError('Missing or invalid ' + name)
    return value


def _positive_float(env, name, default):
    try:
        value = float(env.get(name, default))
    except (TypeError, ValueError):
        raise ValueError('Invalid ' + name) from None
    if not value > 0:
        raise ValueError('Invalid ' + name)
    return value


def config_from_env(env=None):
    env = os.environ if env is None else env
    instance_id = _required(env, 'ENROLLMENT_TEXT_INSTANCE_ID')
    parsed = uuid.UUID(instance_id)
    if str(parsed) != instance_id or parsed.int == 0:
        raise ValueError('ENROLLMENT_TEXT_INSTANCE_ID must be a canonical nonzero UUID')
    token = _required(env, 'ENROLLMENT_TEXT_SERVICE_TOKEN')
    purpose = env.get('ENROLLMENT_TEXT_SAMPLE_PURPOSE', 'enrollment').strip()
    if purpose not in ('enrollment', 'history'):
        raise ValueError('Invalid ENROLLMENT_TEXT_SAMPLE_PURPOSE')
    return {
        'business_url': _required(env, 'ENROLLMENT_TEXT_BUSINESS_URL'),
        'service_id': _required(env, 'ENROLLMENT_TEXT_SERVICE_ID'),
        'token': token,
        'instance_id': instance_id,
        'feature_url': env.get('ENROLLMENT_TEXT_FEATURE_URL', 'http://127.0.0.1:28024').strip(),
        'capability_code': env.get('ENROLLMENT_TEXT_CAPABILITY_CODE',
                                   'person.reidentification').strip(),
        'poll_seconds': _positive_float(env, 'ENROLLMENT_TEXT_POLL_SECONDS', 5),
        'timeout': _positive_float(env, 'ENROLLMENT_TEXT_TIMEOUT_SECONDS', 30),
        'sample_purpose': purpose,
    }


def build_pipeline(config):
    client = BusinessClient(
        config['business_url'],
        service_id=config['service_id'],
        token_provider=lambda: config['token'],
        timeout=config['timeout'],
    )
    return LocalSamplePipeline(
        client,
        instance_id=config['instance_id'],
        capability_code=config['capability_code'],
        threshold=0.88,
        extractor=TextReIDFeatureClient(config['feature_url'], timeout=config['timeout']),
        poll_interval_seconds=config['poll_seconds'],
        enrollment_only=True,
        sample_purpose=config['sample_purpose'],
    )


def main(argv=None):
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    try:
        config = config_from_env()
        pipeline = build_pipeline(config)
    except ValueError as error:
        LOG.error('Invalid configuration: %s', error)
        return 2

    stopped = threading.Event()

    def _stop(signum, _frame):
        LOG.info('Received signal %s; stopping enrollment worker', signum)
        stopped.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    pipeline.start()
    LOG.info('Text sample worker started (purpose=%s, feature=%s, '
             'space is registered on first poll)',
             config['sample_purpose'], config['feature_url'])
    try:
        while not stopped.wait(1):
            pass
    finally:
        if pipeline.stop():
            LOG.info('Enrollment text worker stopped: %s', pipeline.status())
        else:
            LOG.warning('Enrollment text worker did not stop within the timeout')
    return 0


if __name__ == '__main__':
    sys.exit(main())