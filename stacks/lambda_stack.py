from aws_cdk import (
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_s3_notifications as s3n,
    Stack,
    Duration,
)
from constructs import Construct


class LambdaStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        kms_key,
        state_machine,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Ingest Handler Lambda function
        self.s3_ingest_handler = _lambda.Function(
            self,
            "S3IngestHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("src/functions/s3_ingest_handler"),
            handler="main.handler",
            timeout=Duration.minutes(5),
            environment={
                "STATE_MACHINE_ARN": state_machine.state_machine_arn,
                "KMS_KEY_ID": kms_key.key_id,
            }
        )

        # Grant permissions to start Step Functions execution
        state_machine.grant_start_execution(self.s3_ingest_handler)

        # Grant KMS permissions
        kms_key.grant_encrypt_decrypt(self.s3_ingest_handler)

        # Grant S3 read permissions (will be granted for all S3 buckets)
        self.s3_ingest_handler.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject"
                ],
                resources=["arn:aws:s3:::*/*"]
            )
        )
