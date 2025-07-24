#!/usr/bin/env python3

import aws_cdk as cdk

from utils import config
from stacks import (
    KmsStack,
    ProfileAvatarUploadBucketStack,
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

# Create the S3 bucket stack for profile avatar uploads
s3_profile_avatar_upload_stack = ProfileAvatarUploadBucketStack(
    app,
    f"{APP_STACK_PREFIX}ProfileAvatarUploadBucketStack",
    env=environment,
)


app.synth()
