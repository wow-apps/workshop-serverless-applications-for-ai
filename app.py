#!/usr/bin/env python3

import aws_cdk as cdk

from utils import config
from stacks import (
    KmsStack,
    InterviewBucketStack,
)


app = cdk.App()

environment = cdk.Environment(
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

# S3 Interview Bucket Stack
s3_interview_stack = InterviewBucketStack(
    app,
    f"{APP_STACK_PREFIX}InterviewBucketStack",
    env=environment,
)


app.synth()
