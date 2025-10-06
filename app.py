#!/usr/bin/env python3

import aws_cdk as cdk

from utils import config
from stacks import (
    KmsStack,
    InterviewBucketStack,
    DynamoDbStack,
    StepFunctionsStack,
    LambdaStack,
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

# DynamoDB Stack for interview data
dynamodb_stack = DynamoDbStack(
    app,
    f"{APP_STACK_PREFIX}DynamoDbStack",
    kms_key=kms_stack.kms_key,
    env=environment,
)

# Use existing system-defined inference profile for Claude 4 Sonnet (200k
# context)
bedrock_inference_profile_arn = f"arn:aws:bedrock:{config.env_region}:{config.env_account}:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0"

# Step Functions Stack for orchestration
step_functions_stack = StepFunctionsStack(
    app,
    f"{APP_STACK_PREFIX}StepFunctionsStack",
    kms_key=kms_stack.kms_key,
    bedrock_inference_profile_arn=bedrock_inference_profile_arn,
    dynamodb_stack=dynamodb_stack,
    env=environment,
)

# Lambda Stack for S3 event handling
lambda_stack = LambdaStack(
    app,
    f"{APP_STACK_PREFIX}LambdaStack",
    kms_key=kms_stack.kms_key,
    state_machine=step_functions_stack.state_machine,
    env=environment,
)

# Add dependencies
dynamodb_stack.add_dependency(kms_stack)
step_functions_stack.add_dependency(kms_stack)
step_functions_stack.add_dependency(dynamodb_stack)
lambda_stack.add_dependency(step_functions_stack)

# Add S3 event notifications after Lambda is created
s3_interview_stack.add_event_notifications(lambda_stack.s3_ingest_handler)

app.synth()
