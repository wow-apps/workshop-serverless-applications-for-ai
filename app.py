#!/usr/bin/env python3

import aws_cdk as cdk

from utils import config
from stacks import (
    KmsStack,
    ProfileAvatarUploadBucketStack,
    ProfileAvatarPublicBucketStack,
    ProfileAvatarResizeAndStoreLambdaStack,
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

# Create the Lambda function stack for resizing and storing profile avatars
profile_avatar_resize_and_store_stack = ProfileAvatarResizeAndStoreLambdaStack(
    app,
    f"{APP_STACK_PREFIX}ProfileAvatarResizeAndStoreLambdaStack",
    env=environment,
    kms_key=kms_stack.kms_key,
)

# Create the S3 bucket stack for public profile avatars, passing the Lambda function
s3_profile_avatar_public_stack = ProfileAvatarPublicBucketStack(
    app,
    f"{APP_STACK_PREFIX}ProfileAvatarPublicBucketStack",
    env=environment,
    lambda_fn=profile_avatar_resize_and_store_stack.lambda_fn,
)

# Create the S3 bucket stack for profile avatar uploads, passing the Lambda function
s3_profile_avatar_upload_stack = ProfileAvatarUploadBucketStack(
    app,
    f"{APP_STACK_PREFIX}ProfileAvatarUploadBucketStack",
    env=environment,
    lambda_fn=profile_avatar_resize_and_store_stack.lambda_fn,
)


app.synth()
