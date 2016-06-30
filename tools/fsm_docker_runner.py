# system imports
import os
import base64
import sys
import json
import logging

# library imports
from docker import Client

# application imports
from aws_lambda_fsm.aws import send_next_event_for_dispatch
from aws_lambda_fsm.aws import load_environment
from aws_lambda_fsm.constants import PAYLOAD
from aws_lambda_fsm.constants import SYSTEM_CONTEXT
from aws_lambda_fsm.constants import ENVIRONMENT

return_code = None
environment = None
stdout, stderr, client = None, None, None

DOCKER_SOCK_URI = 'unix://var/run/docker.sock'
DOCKER_SOCK_PATH = '/var/run/docker.sock'
FATAL_ENVIRONMENT_ERROR = "FATAL environment error. FSM cannot continue."

DONE_EVENT = 'done'
FAIL_EVENT = 'fail'

try:

    # just run the image and return an event based on the return value
    fsm_environment_guid = os.environ[ENVIRONMENT.FSM_ENVIRONMENT_GUID_KEY]
    environment = load_environment(None, fsm_environment_guid)
    image = environment.pop(ENVIRONMENT.FSM_DOCKER_IMAGE)
    client = Client(base_url=DOCKER_SOCK_URI, version='auto')
    container = client.create_container(
        image=image,
        environment=environment,
        volumes=DOCKER_SOCK_PATH + ':' + DOCKER_SOCK_PATH
    )
    client.start(container=container)
    stdout = client.logs(container, stdout=True, stream=True)
    for line in stdout:
        sys.stdout.write(line)
    stderr = client.logs(container, stderr=True, stream=True)
    for line in stderr:
        sys.stderr.write(line)
    return_code = client.wait(container)

except Exception:
    logging.exception('')
    raise

finally:

    if not environment:
        sys.stderr.write(FATAL_ENVIRONMENT_ERROR)
        sys.exit(1)

    # FSM_CONTEXT is the environment variable used by aws_lambda_fsm.utils.ECSTaskEntryAction
    event = DONE_EVENT if return_code == 0 else FAIL_EVENT
    payload_encoded = environment[ENVIRONMENT.FSM_CONTEXT]
    payload = json.loads(base64.b64decode(payload_encoded))
    payload[PAYLOAD.SYSTEM_CONTEXT][SYSTEM_CONTEXT.CURRENT_EVENT] = event
    serialized = json.dumps(payload)
    send_next_event_for_dispatch(
        None,
        serialized,
        payload[PAYLOAD.SYSTEM_CONTEXT][SYSTEM_CONTEXT.CORRELATION_ID]
    )