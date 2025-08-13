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
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # IAM role for Step Functions
        self.state_machine_role = iam.Role(
            self,
            "InterviewPipelineStateMachineRole",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaRole")
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

        # Grant permissions to Lambda functions
        kms_key.grant_encrypt_decrypt(self.transcribe_processor_function)
        kms_key.grant_encrypt_decrypt(self.transcribe_status_checker_function)

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
                    "s3:GetObject"
                ],
                resources=["arn:aws:s3:::*/*"]
            )
        )

        # Grant Transcribe permissions
        transcribe_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "transcribe:StartTranscriptionJob",
                "transcribe:GetTranscriptionJob",
                "transcribe:ListTranscriptionJobs"
            ],
            resources=["*"]
        )

        self.transcribe_processor_function.add_to_role_policy(transcribe_policy)
        self.transcribe_status_checker_function.add_to_role_policy(transcribe_policy)

        # Grant DynamoDB permissions
        dynamodb_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:UpdateItem"
            ],
            resources=["arn:aws:dynamodb:*:*:table/interview_transcriptions"]
        )

        self.transcribe_processor_function.add_to_role_policy(dynamodb_policy)
        self.transcribe_status_checker_function.add_to_role_policy(dynamodb_policy)

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

        # Choice state to check if transcription is complete
        transcription_complete = sfn.Choice(self, "IsTranscriptionComplete")

        # Success and failure states
        success_state = sfn.Succeed(
            self,
            "TranscriptionSuccess",
            comment="Interview transcription completed successfully"
        )

        failure_state = sfn.Fail(
            self,
            "TranscriptionFailed",
            comment="Interview transcription failed",
            cause="Transcription job failed or timed out"
        )

        # Define the workflow
        definition = start_transcription_task.next(
            wait_for_transcription.next(
                check_transcription_status_task.next(
                    transcription_complete
                    .when(
                        sfn.Condition.string_equals("$.status_result.Payload.transcribe_status", "COMPLETED"),
                        success_state
                    )
                    .when(
                        sfn.Condition.string_equals("$.status_result.Payload.transcribe_status", "FAILED"),
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
