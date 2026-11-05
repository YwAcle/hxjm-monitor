import multiprocessing as mp
import os
import signal
import tempfile
import time
import unittest

import zmq

from server_base import BaseServer


class HealthOnlyServer(BaseServer):
    @staticmethod
    def init_model_context():
        return {}

    def process_frame(self, meta, model_ctx=None):
        raise AssertionError("health requests must not enter the worker pool")


def run_server(address):
    HealthOnlyServer(address).serve()


class BaseServerHealthTest(unittest.TestCase):
    def test_health_request_bypasses_workers(self):
        with tempfile.TemporaryDirectory() as directory:
            address = f"ipc://{directory}/health.ipc"
            process = mp.Process(target=run_server, args=(address,), daemon=True)
            process.start()
            context = zmq.Context()
            client = context.socket(zmq.REQ)
            client.setsockopt(zmq.LINGER, 0)
            client.setsockopt(zmq.RCVTIMEO, 200)
            client.connect(address)
            try:
                deadline = time.time() + 3
                while True:
                    try:
                        client.send_json({"task": "__health__"})
                        self.assertEqual(client.recv_string(), "OK")
                        break
                    except zmq.Again:
                        client.close()
                        if time.time() >= deadline:
                            self.fail("health server did not become ready")
                        client = context.socket(zmq.REQ)
                        client.setsockopt(zmq.LINGER, 0)
                        client.setsockopt(zmq.RCVTIMEO, 200)
                        client.connect(address)
            finally:
                client.close()
                context.term()
                if process.is_alive():
                    os.kill(process.pid, signal.SIGINT)
                process.join(timeout=2)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
