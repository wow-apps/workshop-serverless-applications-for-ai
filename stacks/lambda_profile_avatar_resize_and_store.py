from aws_cdk import (
    aws_lambda as _lambda,
    aws_iam as iam,
    Stack
)
from constructs import Construct
import aws_cdk as cdk


class ProfileAvatarResizeAndStoreLambdaStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, kms_key, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        pillow_layer = _lambda.LayerVersion.from_layer_version_arn(
            self,
            "PillowLayer",
            "arn:aws:lambda:us-east-1:770693421928:layer:Klayers-p312-pillow:2"
        )

        # Lambda function definition
        lambda_fn = _lambda.Function(
            self,
            "ProfileAvatarResizeAndStoreLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="__init__.handler",
            code=_lambda.Code.from_asset("src/functions/profile_avatar_resize_and_store"),
            timeout=cdk.Duration.seconds(30),
            memory_size=128,
            layers=[pillow_layer],
            environment={
                # Buckets are now set by event notification, not environment
                "KMS_KEY_ARN": kms_key.key_arn,
            },
        )

        # Grant Lambda permissions to use KMS key
        kms_key.grant_encrypt_decrypt(lambda_fn)

        self.lambda_fn = lambda_fn
        # Removed all bucket references from Lambda stack
