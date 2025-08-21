from aws_cdk import (
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as _lambda,
    aws_iam as iam,
    Stack,
    Duration,
)
from constructs import Construct


class StepFunctionsStack(Stack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            kms_key,
            bedrock_inference_profile_arn: str,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # IAM role for Step Functions
        self.state_machine_role = iam.Role(
            self,
            "InterviewPipelineStateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaRole")
            ]
        )

        # Lambda function for transcription processing
        self.transcribe_processor_function = _lambda.Function(
            self,
            "TranscribeProcessorFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("src/functions/transcribe_processor"),
            handler="main.handler",
            timeout=Duration.minutes(15),
            environment={
                "KMS_KEY_ID": kms_key.key_id,
            }
        )

        # Lambda function for checking transcription status
        self.transcribe_status_checker_function = _lambda.Function(
            self,
            "TranscribeStatusCheckerFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("src/functions/transcribe_processor"),
            handler="main.check_transcription_status",
            timeout=Duration.minutes(5),
            environment={
                "KMS_KEY_ID": kms_key.key_id,
            }
        )

        # Lambda function for Q&A extraction using Bedrock Claude Sonnet (single-pass)
        self.qa_extractor_function = _lambda.Function(
            self,
            "QAExtractorFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("src/functions/qa_extractor"),
            handler="main.handler",
            timeout=Duration.minutes(15),  # Increased timeout for large transcripts
            environment={
                "KMS_KEY_ID": kms_key.key_id,
                "BEDROCK_INFERENCE_PROFILE_ARN": bedrock_inference_profile_arn,
            }
        )


        # Grant permissions to Lambda functions
        kms_key.grant_encrypt_decrypt(self.transcribe_processor_function)
        kms_key.grant_encrypt_decrypt(self.transcribe_status_checker_function)
        kms_key.grant_encrypt_decrypt(self.qa_extractor_function)

        # Grant S3 permissions
        self.transcribe_processor_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject"
                ],
                resources=["arn:aws:s3:::*/*"]
            )
        )

        self.transcribe_status_checker_function.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject"
                ],
                resources=["arn:aws:s3:::*/*"]
            )
        )

        # Grant Transcribe permissions including custom vocabulary
        transcribe_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "transcribe:StartTranscriptionJob",
                "transcribe:GetTranscriptionJob",
                "transcribe:ListTranscriptionJobs",
                # Custom vocabulary permissions for Russian language optimization
                "transcribe:CreateVocabulary",
                "transcribe:GetVocabulary",
                "transcribe:ListVocabularies",
                "transcribe:UpdateVocabulary",
                "transcribe:DeleteVocabulary"
            ],
            resources=["*"]
        )

        self.transcribe_processor_function.add_to_role_policy(
            transcribe_policy)
        self.transcribe_status_checker_function.add_to_role_policy(
            transcribe_policy)

        # Grant DynamoDB permissions
        dynamodb_transcriptions_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:UpdateItem"
            ],
            resources=["arn:aws:dynamodb:*:*:table/interview_transcriptions"]
        )

        dynamodb_qa_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:Query"
            ],
            resources=[
                "arn:aws:dynamodb:*:*:table/interview_transcriptions",
                "arn:aws:dynamodb:*:*:table/interview_qa"
            ]
        )

        # Grant Bedrock permissions for Q&A extraction
        # Need permissions for:
        # 1. The inference profile (can be cross-region)
        # 2. The underlying foundation model in any region (inference profiles route across regions)
        bedrock_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:InvokeModel"
            ],
            resources=[
                # Inference profile
                bedrock_inference_profile_arn,
                # Foundation model in any region (needed for cross-region inference)
                "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-20250514-v1:0"
            ]
        )


        self.transcribe_processor_function.add_to_role_policy(
            dynamodb_transcriptions_policy)
        self.transcribe_status_checker_function.add_to_role_policy(
            dynamodb_transcriptions_policy)
        self.qa_extractor_function.add_to_role_policy(dynamodb_qa_policy)
        self.qa_extractor_function.add_to_role_policy(bedrock_policy)


        # Step Functions tasks
        start_transcription_task = tasks.LambdaInvoke(
            self,
            "StartTranscription",
            lambda_function=self.transcribe_processor_function,
            result_path="$.transcription_result"
        )

        wait_for_transcription = sfn.Wait(
            self,
            "WaitForTranscription",
            time=sfn.WaitTime.duration(Duration.seconds(30))
        )

        check_transcription_status_task = tasks.LambdaInvoke(
            self,
            "CheckTranscriptionStatus",
            lambda_function=self.transcribe_status_checker_function,
            input_path="$.transcription_result.Payload",
            result_path="$.status_result"
        )

        # Q&A extraction task (single-pass with Claude Sonnet)
        qa_extraction_task = tasks.LambdaInvoke(
            self,
            "ExtractQAPairs",
            lambda_function=self.qa_extractor_function,
            input_path="$.status_result.Payload",
            result_path="$.qa_result"
        )

        # Choice state to check if transcription is complete
        transcription_complete = sfn.Choice(self, "IsTranscriptionComplete")

        # Success and failure states
        success_state = sfn.Succeed(
            self,
            "PipelineSuccess",
            comment="Interview processing pipeline completed successfully"
        )

        failure_state = sfn.Fail(
            self,
            "PipelineFailed",
            comment="Interview processing pipeline failed",
            cause="Transcription job failed or timed out"
        )

        # Define the simplified workflow with single-pass Q&A extraction
        definition = start_transcription_task.next(
            wait_for_transcription.next(
                check_transcription_status_task.next(
                    transcription_complete
                    .when(
                        sfn.Condition.string_equals(
                            "$.status_result.Payload.transcribe_status", "COMPLETED"),
                        # Direct Q&A extraction with Claude Sonnet (single-pass)
                        qa_extraction_task.next(success_state)
                    )
                    .when(
                        sfn.Condition.string_equals(
                            "$.status_result.Payload.transcribe_status", "FAILED"),
                        failure_state
                    )
                    .otherwise(wait_for_transcription)
                )
            )
        )

        # Create the Step Functions state machine
        self.state_machine = sfn.StateMachine(
            self,
            "InterviewPipelineStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            role=self.state_machine_role,
            timeout=Duration.hours(2)
        )
