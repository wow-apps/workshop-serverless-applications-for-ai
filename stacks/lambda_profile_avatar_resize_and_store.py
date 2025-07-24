from aws_cdk import (
    aws_lambda as _lambda,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_iam as iam,
    Stack
)
from constructs import Construct
import aws_cdk as cdk


class ProfileAvatarResizeAndStoreLambdaStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, upload_bucket: s3.IBucket, public_bucket: s3.IBucket, kms_key, **kwargs) -> None:
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
                "PUBLIC_BUCKET": public_bucket.bucket_name,
                "KMS_KEY_ARN": kms_key.key_arn,
            },
        )

        # Grant Lambda permissions to use KMS key
        kms_key.grant_encrypt_decrypt(lambda_fn)

        # Grant S3 access to Lambda for upload bucket
        lambda_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
            resources=[
                upload_bucket.bucket_arn,
                f"{upload_bucket.bucket_arn}/*"
            ]
        ))

        # Grant S3 access to Lambda for public bucket (write only)
        lambda_fn.add_to_role_policy(iam.PolicyStatement(
            actions=["s3:PutObject"],
            resources=[
                public_bucket.bucket_arn,
                f"{public_bucket.bucket_arn}/*"
            ]
        ))

        # Add S3 event notification to trigger Lambda on new object creation
        notification = s3n.LambdaDestination(lambda_fn)
        upload_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            notification
        )
