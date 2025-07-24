#!/usr/bin/env python3

import aws_cdk

from utils import config
from stacks import (
    KmsStack
)


app = aws_cdk.App()

environment = aws_cdk.Environment(
    account=config.env_account,
    region=config.env_region
)

APP_STACK_PREFIX = "Workshop"

# Create the KMS stack first
kms_stack = KmsStack(
    app,
    f"{APP_STACK_PREFIX}KmsStack",
    env=environment,
)


app.synth()
