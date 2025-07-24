from aws_cdk import (
    aws_s3 as s3,
    Stack, RemovalPolicy,
)
from constructs import Construct


class ProfileAvatarUploadBucketStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        lambda_fn=None,  # Accept Lambda function as optional parameter
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        bucket = s3.Bucket(
            self,
            "ProfileAvatarUploadBucket",
            bucket_name="workshop-profile-avatar-upload",
            public_read_access=False,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        self.upload_bucket = bucket

        # If Lambda function is provided, set up S3 event notification
        if lambda_fn is not None:
            from aws_cdk import aws_s3_notifications as s3n

            notification = s3n.LambdaDestination(lambda_fn)
            bucket.add_event_notification(
                s3.EventType.OBJECT_CREATED,
                notification
            )
