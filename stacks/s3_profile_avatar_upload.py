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
